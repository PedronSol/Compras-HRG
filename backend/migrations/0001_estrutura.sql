-- =====================================================================
-- RG Hospital — 0001: estrutura base (schemas, tipos, tabelas, índices)
-- Requer PostgreSQL >= 15 (views com security_invoker).
-- =====================================================================

create schema if not exists rg;
create schema if not exists audit;

-- Papel de banco usado pela aplicação. O usuário de login da API deve ser
-- membro dele (GRANT rg_app TO rg_api) e NÃO pode ser dono das tabelas,
-- para que o Row Level Security seja sempre aplicado.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'rg_app') then
    create role rg_app nologin;
  end if;
end $$;

-- ---------------------------------------------------------------------
-- Tipos enumerados
-- ---------------------------------------------------------------------
create type rg.papel_usuario      as enum ('admin', 'gestor', 'compras');
create type rg.status_usuario     as enum ('pendente', 'aprovado', 'rejeitado', 'suspenso');
create type rg.tipo_solicitacao   as enum ('compra', 'orcamento', 'contratacao_servico');
create type rg.urgencia           as enum ('normal', 'urgente', 'imediato');
create type rg.status_solicitacao as enum (
  'aguardando_adm', 'necessita_nova_cotacao', 'rejeitado_adm', 'aprovado_adm',
  'em_cotacao', 'aprovado', 'rejeitado_compras', 'cancelado'
);
create type rg.tipo_documento     as enum ('orcamento', 'nota_fiscal', 'laudo', 'cotacao', 'outro');
create type rg.origem_anexo       as enum ('solicitante', 'compras', 'servico');
create type rg.ocr_status         as enum ('pendente', 'processando', 'concluido', 'falhou', 'nao_suportado');
create type rg.tipo_assinatura    as enum ('gestor', 'adm', 'compras');
create type rg.categoria_servico  as enum ('manutencao_preventiva', 'calibracao', 'higienizacao', 'ronda', 'predial');
create type rg.periodicidade      as enum ('unica', 'diaria', 'semanal', 'quinzenal', 'mensal', 'trimestral', 'semestral', 'anual');
create type rg.situacao_servico   as enum ('agendado', 'em_andamento', 'concluido', 'cancelado');
create type rg.tipo_notificacao   as enum ('info', 'sucesso', 'alerta', 'erro');

-- ---------------------------------------------------------------------
-- Funções utilitárias puras
-- ---------------------------------------------------------------------

-- Valida CNPJ numérico e alfanumérico (IN RFB nº 2.229/2024, vigente desde 07/2026).
create function rg.cnpj_valido(p text) returns boolean
language plpgsql immutable
set search_path = pg_catalog
as $$
declare
  d  text := upper(regexp_replace(coalesce(p, ''), '[^0-9A-Za-z]', '', 'g'));
  w1 int[] := array[5,4,3,2,9,8,7,6,5,4,3,2];
  w2 int[] := array[6,5,4,3,2,9,8,7,6,5,4,3,2];
  s  int;
  r  int;
  i  int;
begin
  if d !~ '^[0-9A-Z]{12}[0-9]{2}$' or d ~ '^(.)\1{13}$' then
    return false;
  end if;
  s := 0;
  for i in 1..12 loop s := s + (ascii(substr(d, i, 1)) - 48) * w1[i]; end loop;
  r := s % 11; r := case when r < 2 then 0 else 11 - r end;
  if r <> substr(d, 13, 1)::int then return false; end if;
  s := 0;
  for i in 1..13 loop s := s + (ascii(substr(d, i, 1)) - 48) * w2[i]; end loop;
  r := s % 11; r := case when r < 2 then 0 else 11 - r end;
  return r = substr(d, 14, 1)::int;
end $$;

create function rg.sla_intervalo(p rg.urgencia) returns interval
language sql immutable
as $$
  select case p
    when 'imediato' then interval '3 days'
    when 'urgente'  then interval '7 days'
    else                 interval '14 days'
  end
$$;

create function rg.status_terminal(p rg.status_solicitacao) returns boolean
language sql immutable
as $$ select p in ('aprovado', 'rejeitado_adm', 'rejeitado_compras', 'cancelado') $$;

-- ---------------------------------------------------------------------
-- Setores
-- ---------------------------------------------------------------------
create table rg.setores (
  codigo       text primary key check (codigo ~ '^[a-z][a-z_]{1,39}$'),
  nome         text not null unique check (char_length(nome) between 2 and 80),
  cor          text not null check (cor ~ '^#[0-9A-Fa-f]{6}$'),
  operacional  boolean not null default true,  -- pode abrir solicitações e serviços
  ativo        boolean not null default true,
  criado_em    timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

insert into rg.setores (codigo, nome, cor, operacional) values
  ('centro_cirurgico',     'Centro Cirúrgico',        '#0E7C86', true),
  ('uti_adulto',           'UTI Adulto',              '#C2410C', true),
  ('uti_neonatal',         'UTI Neonatal',            '#DB2777', true),
  ('maternidade',          'Maternidade',             '#9333EA', true),
  ('imagem',               'Imagem',                  '#4F46E5', true),
  ('laboratorio',          'Laboratório',             '#0891B2', true),
  ('pronto_socorro',       'Pronto Socorro',          '#DC2626', true),
  ('farmacia_central',     'Farmácia Central',        '#16A34A', true),
  ('engenharia_clinica',   'Engenharia Clínica',      '#1D4ED8', true),
  ('hotelaria_manutencao', 'Hotelaria / Manutenção',  '#A16207', true),
  ('administracao',        'Administração Geral',     '#475569', false),
  ('suprimentos',          'Compras / Suprimentos',   '#57534E', false);

-- ---------------------------------------------------------------------
-- Usuários, sessões e histórico de senhas
-- ---------------------------------------------------------------------
create table rg.usuarios (
  id                       uuid primary key default gen_random_uuid(),
  email                    text not null check (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  nome                     text not null check (char_length(nome) between 3 and 120),
  setor_codigo             text not null references rg.setores (codigo),
  cargo                    text check (cargo is null or char_length(cargo) <= 80),
  papel                    rg.papel_usuario not null default 'gestor',
  status                   rg.status_usuario not null default 'pendente',
  telefone_cript           text,                         -- Fernet (AES-128-CBC + HMAC-SHA256)
  senha_hash               text not null,                -- Argon2id
  senha_alterada_em        timestamptz not null default now(),
  troca_senha_obrigatoria  boolean not null default false,
  tentativas_falhas        int not null default 0,
  bloqueado_ate            timestamptz,
  ultimo_login_em          timestamptz,
  consentimento_lgpd_em    timestamptz,
  consentimento_versao     text,
  analisado_por            uuid references rg.usuarios (id),
  analisado_em             timestamptz,
  motivo_rejeicao          text,
  anonimizado_em           timestamptz,
  criado_em                timestamptz not null default now(),
  atualizado_em            timestamptz not null default now()
);
create unique index usuarios_email_uk on rg.usuarios (lower(email));
create index usuarios_status_idx on rg.usuarios (status);
create index usuarios_papel_setor_idx on rg.usuarios (papel, setor_codigo) where status = 'aprovado';

create table rg.senhas_historico (
  id          bigint generated always as identity primary key,
  usuario_id  uuid not null references rg.usuarios (id) on delete cascade,
  senha_hash  text not null,
  criado_em   timestamptz not null default now()
);
create index senhas_historico_usuario_idx on rg.senhas_historico (usuario_id, criado_em desc);

create table rg.sessoes (
  id               uuid primary key default gen_random_uuid(),
  usuario_id       uuid not null references rg.usuarios (id) on delete cascade,
  token_hash       text not null unique,       -- SHA-256 do token do cookie
  csrf_token       text not null,
  ip               text,
  user_agent       text,
  criado_em        timestamptz not null default now(),
  ultimo_acesso_em timestamptz not null default now(),
  expira_em        timestamptz not null,
  revogada_em      timestamptz
);
create index sessoes_usuario_idx on rg.sessoes (usuario_id) where revogada_em is null;

-- ---------------------------------------------------------------------
-- Fornecedores
-- ---------------------------------------------------------------------
create table rg.fornecedores (
  id             uuid primary key default gen_random_uuid(),
  razao_social   text not null check (char_length(razao_social) between 2 and 160),
  nome_fantasia  text check (nome_fantasia is null or char_length(nome_fantasia) <= 160),
  cnpj           text not null unique check (rg.cnpj_valido(cnpj) and cnpj = upper(regexp_replace(cnpj, '[^0-9A-Za-z]', '', 'g'))),
  email          text check (email is null or email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  telefone       text check (telefone is null or char_length(telefone) <= 30),
  contato        text check (contato is null or char_length(contato) <= 120),
  ativo          boolean not null default true,
  criado_por     uuid references rg.usuarios (id),
  criado_em      timestamptz not null default now(),
  atualizado_em  timestamptz not null default now()
);
create index fornecedores_nome_idx on rg.fornecedores (lower(razao_social));

-- ---------------------------------------------------------------------
-- Solicitações
-- ---------------------------------------------------------------------
create sequence rg.solicitacao_codigo_seq;

create table rg.solicitacoes (
  id                         uuid primary key default gen_random_uuid(),
  codigo                     text not null unique,
  tipo                       rg.tipo_solicitacao not null,
  titulo                     text not null check (char_length(titulo) between 5 and 160),
  descricao                  text not null check (char_length(descricao) between 10 and 5000),
  justificativa              text not null check (char_length(btrim(justificativa)) >= 20 and char_length(justificativa) <= 5000),
  setor_codigo               text not null references rg.setores (codigo),
  urgencia                   rg.urgencia not null default 'normal',
  status                     rg.status_solicitacao not null default 'aguardando_adm',
  valor_estimado             numeric(14,2) check (valor_estimado is null or valor_estimado >= 0),
  valor_final_aprovado       numeric(14,2) check (valor_final_aprovado is null or valor_final_aprovado > 0),
  gestor_id                  uuid not null references rg.usuarios (id),
  comprador_id               uuid references rg.usuarios (id),
  justificativa_adm          text check (justificativa_adm is null or char_length(justificativa_adm) <= 2000),
  justificativa_urgencia     text check (justificativa_urgencia is null or char_length(justificativa_urgencia) <= 2000),
  motivo_nova_cotacao        text check (motivo_nova_cotacao is null or char_length(motivo_nova_cotacao) <= 2000),
  justificativa_compras      text check (justificativa_compras is null or char_length(justificativa_compras) <= 2000),
  motivo_cancelamento        text check (motivo_cancelamento is null or char_length(motivo_cancelamento) <= 2000),
  cotacao_vencedora_id       uuid,
  rodada_cotacao             int not null default 1,
  versao                     int not null default 1,
  sla_prazo_limite           timestamptz not null,
  sla_concluido_em           timestamptz,
  sla_alerta_notificado_em   timestamptz,
  sla_estouro_notificado_em  timestamptz,
  decidido_adm_em            timestamptz,
  cotacao_iniciada_em        timestamptz,
  finalizado_em              timestamptz,
  criado_em                  timestamptz not null default now(),
  atualizado_em              timestamptz not null default now()
);
create index solicitacoes_status_idx   on rg.solicitacoes (status);
create index solicitacoes_setor_idx    on rg.solicitacoes (setor_codigo, criado_em desc);
create index solicitacoes_criado_idx   on rg.solicitacoes (criado_em desc);
create index solicitacoes_gestor_idx   on rg.solicitacoes (gestor_id);
create index solicitacoes_sla_idx      on rg.solicitacoes (sla_prazo_limite) where sla_concluido_em is null;
create index solicitacoes_busca_idx    on rg.solicitacoes using gin (to_tsvector('portuguese', titulo || ' ' || descricao));

-- ---------------------------------------------------------------------
-- Serviços programados
-- ---------------------------------------------------------------------
create sequence rg.servico_codigo_seq;

create table rg.servicos_programados (
  id                     uuid primary key default gen_random_uuid(),
  codigo                 text not null unique,
  titulo                 text not null check (char_length(titulo) between 5 and 160),
  descricao              text check (descricao is null or char_length(descricao) <= 5000),
  setor_codigo           text not null references rg.setores (codigo),
  categoria              rg.categoria_servico not null,
  local                  text check (local is null or char_length(local) <= 160),
  data_programada        date not null,
  hora_inicio            time not null,
  hora_termino           time not null,
  responsavel_executor   text not null check (char_length(responsavel_executor) between 3 and 120),
  empresa_terceirizada   text check (empresa_terceirizada is null or char_length(empresa_terceirizada) <= 160),
  periodicidade          rg.periodicidade not null default 'unica',
  situacao               rg.situacao_servico not null default 'agendado',
  serie_id               uuid not null default gen_random_uuid(),
  servico_origem_id      uuid references rg.servicos_programados (id),
  observacoes_conclusao  text check (observacoes_conclusao is null or char_length(observacoes_conclusao) <= 5000),
  motivo_cancelamento    text check (motivo_cancelamento is null or char_length(motivo_cancelamento) <= 2000),
  iniciado_em            timestamptz,
  concluido_em           timestamptz,
  concluido_por          uuid references rg.usuarios (id),
  criado_por             uuid not null references rg.usuarios (id),
  criado_em              timestamptz not null default now(),
  atualizado_em          timestamptz not null default now(),
  constraint servicos_horario_ck check (hora_termino > hora_inicio),
  constraint servicos_conclusao_ck check (situacao <> 'concluido' or (concluido_em is not null and char_length(coalesce(observacoes_conclusao, '')) >= 5)),
  constraint servicos_cancelamento_ck check (situacao <> 'cancelado' or char_length(coalesce(motivo_cancelamento, '')) >= 5)
);
create index servicos_data_idx   on rg.servicos_programados (data_programada, hora_inicio);
create index servicos_setor_idx  on rg.servicos_programados (setor_codigo, data_programada);
create index servicos_serie_idx  on rg.servicos_programados (serie_id);
create unique index servicos_recorrencia_uk on rg.servicos_programados (servico_origem_id) where servico_origem_id is not null;

-- ---------------------------------------------------------------------
-- Anexos (solicitações e serviços) com OCR
-- ---------------------------------------------------------------------
create table rg.anexos (
  id                 uuid primary key default gen_random_uuid(),
  solicitacao_id     uuid references rg.solicitacoes (id),
  servico_id         uuid references rg.servicos_programados (id),
  origem             rg.origem_anexo not null,
  tipo_documento     rg.tipo_documento not null default 'orcamento',
  nome_original      text not null check (char_length(nome_original) between 1 and 200),
  mime               text not null,
  tamanho            int not null check (tamanho > 0 and tamanho <= 10485760),
  sha256             text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  caminho            text not null,
  rodada_cotacao     int not null default 1,
  enviado_por        uuid not null references rg.usuarios (id),
  ocr_status         rg.ocr_status not null default 'pendente',
  ocr_motor          text,
  ocr_texto          text,
  dados_ocr          jsonb,
  ocr_erro           text,
  ocr_processado_em  timestamptz,
  removido_em        timestamptz,
  removido_por       uuid references rg.usuarios (id),
  criado_em          timestamptz not null default now(),
  constraint anexos_alvo_ck check (num_nonnulls(solicitacao_id, servico_id) = 1),
  constraint anexos_origem_ck check (
    (origem = 'servico') = (servico_id is not null)
  )
);
create index anexos_solicitacao_idx on rg.anexos (solicitacao_id) where solicitacao_id is not null;
create index anexos_servico_idx on rg.anexos (servico_id) where servico_id is not null;

-- ---------------------------------------------------------------------
-- Cotações (lançadas por Compras)
-- ---------------------------------------------------------------------
create table rg.cotacoes (
  id                   uuid primary key default gen_random_uuid(),
  solicitacao_id       uuid not null references rg.solicitacoes (id),
  fornecedor_id        uuid not null references rg.fornecedores (id),
  anexo_id             uuid references rg.anexos (id),
  valor                numeric(14,2) not null check (valor > 0),
  prazo_entrega_dias   int not null check (prazo_entrega_dias between 0 and 3650),
  condicoes_pagamento  text check (condicoes_pagamento is null or char_length(condicoes_pagamento) <= 300),
  validade_proposta    date,
  observacoes          text check (observacoes is null or char_length(observacoes) <= 2000),
  selecionada          boolean not null default false,
  criado_por           uuid not null references rg.usuarios (id),
  criado_em            timestamptz not null default now(),
  atualizado_em        timestamptz not null default now(),
  constraint cotacoes_fornecedor_uk unique (solicitacao_id, fornecedor_id)
);
create unique index cotacoes_vencedora_uk on rg.cotacoes (solicitacao_id) where selecionada;

alter table rg.solicitacoes
  add constraint solicitacoes_cotacao_vencedora_fk foreign key (cotacao_vencedora_id) references rg.cotacoes (id);

-- ---------------------------------------------------------------------
-- Assinaturas digitais (imutáveis)
-- ---------------------------------------------------------------------
create table rg.assinaturas (
  id                  uuid primary key default gen_random_uuid(),
  solicitacao_id      uuid not null references rg.solicitacoes (id),
  usuario_id          uuid not null references rg.usuarios (id),
  tipo                rg.tipo_assinatura not null,
  acao                text not null,
  status_resultante   rg.status_solicitacao not null,
  ip                  text not null,
  user_agent          text,
  assinado_em         timestamptz not null,
  conteudo_hash       text not null check (conteudo_hash ~ '^[0-9a-f]{64}$'),
  hash_autenticidade  text not null unique check (hash_autenticidade ~ '^[0-9a-f]{64}$'),
  algoritmo           text not null default 'SHA-256',
  txid                bigint not null default txid_current(),
  criado_em           timestamptz not null default now()
);
create index assinaturas_solicitacao_idx on rg.assinaturas (solicitacao_id, assinado_em);

-- ---------------------------------------------------------------------
-- Histórico do workflow e notificações
-- ---------------------------------------------------------------------
create table rg.solicitacao_historico (
  id              bigint generated always as identity primary key,
  solicitacao_id  uuid not null references rg.solicitacoes (id),
  autor_id        uuid references rg.usuarios (id),
  acao            text not null,
  status_de       rg.status_solicitacao,
  status_para     rg.status_solicitacao,
  observacao      text,
  criado_em       timestamptz not null default now()
);
create index historico_solicitacao_idx on rg.solicitacao_historico (solicitacao_id, criado_em);

create table rg.notificacoes (
  id               uuid primary key default gen_random_uuid(),
  destinatario_id  uuid not null references rg.usuarios (id) on delete cascade,
  tipo             rg.tipo_notificacao not null default 'info',
  titulo           text not null,
  mensagem         text not null,
  link             text,
  lida             boolean not null default false,
  lida_em          timestamptz,
  criado_em        timestamptz not null default now()
);
create index notificacoes_dest_idx on rg.notificacoes (destinatario_id, criado_em desc);
create index notificacoes_nao_lidas_idx on rg.notificacoes (destinatario_id) where not lida;

-- ---------------------------------------------------------------------
-- Auditoria (append-only)
-- ---------------------------------------------------------------------
create table audit.eventos (
  id                bigint generated always as identity primary key,
  ocorrido_em       timestamptz not null default now(),
  usuario_id        uuid,
  ip                text,
  tabela            text not null,
  registro_id       text,
  operacao          text not null,
  campos_alterados  text[],
  dados_antes       jsonb,
  dados_depois      jsonb
);
create index eventos_ocorrido_idx on audit.eventos (ocorrido_em desc);
create index eventos_tabela_registro_idx on audit.eventos (tabela, registro_id);
create index eventos_usuario_idx on audit.eventos (usuario_id, ocorrido_em desc);
