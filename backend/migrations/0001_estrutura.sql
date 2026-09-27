-- =====================================================================
-- Hospital Rio Grande · Compras — 0001: estrutura base
-- Schemas, tipos, tabelas, índices e dados de referência.
-- Requer PostgreSQL >= 15 (views com security_invoker).
--
-- Fluxo: Solicitação → Aprovação → Cotação → Fornecedor → Pedido → Recebimento → Conclusão
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
create type rg.papel_usuario as enum (
  'admin', 'comprador', 'solicitante', 'gestor', 'financeiro', 'recebimento', 'diretoria', 'auditoria'
);
create type rg.status_usuario     as enum ('pendente', 'aprovado', 'rejeitado', 'suspenso');
create type rg.tipo_solicitacao   as enum ('material', 'equipamento', 'servico');
create type rg.urgencia           as enum ('normal', 'urgente', 'imediato');
create type rg.status_solicitacao as enum (
  'aguardando_gestor',     -- 1. aprovação do gestor do setor
  'aguardando_diretoria',  -- 1b. aprovação da Diretoria (acima da alçada ou aberta por gestor)
  'devolvida',             -- devolvida ao solicitante para ajustes
  'reprovada',             -- encerrada: reprovada na aprovação
  'aprovada',              -- 2. aprovada, aguardando o comprador
  'em_cotacao',            -- 3. cotação com fornecedores
  'aguardando_pedido',     -- 4. fornecedor definido, aguardando emissão do pedido
  'em_pedido',             -- 5. pedido de compra emitido
  'recebida_parcial',      -- 6. recebimento parcial
  'concluida',             -- 7. encerrada: recebida e conferida
  'cancelada'              -- encerrada: cancelada
);
create type rg.status_pedido as enum (
  'aguardando_financeiro', 'aguardando_diretoria', 'aprovado', 'enviado',
  'entregue_parcial', 'entregue', 'reprovado', 'cancelado'
);
create type rg.situacao_recebimento as enum ('conforme', 'divergente', 'recusado');
create type rg.tipo_documento     as enum ('orcamento', 'proposta', 'nota_fiscal', 'laudo', 'foto', 'outro');
create type rg.origem_anexo       as enum ('solicitante', 'comprador', 'recebimento');
create type rg.nivel_aprovacao    as enum ('gestor', 'diretoria', 'financeiro');
create type rg.decisao_aprovacao  as enum ('aprovado', 'reprovado', 'devolvido');
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

-- Prazo de atendimento (SLA) de Compras: da abertura até a emissão do pedido.
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
as $$ select p in ('reprovada', 'concluida', 'cancelada') $$;

-- ---------------------------------------------------------------------
-- Setores e configurações
-- ---------------------------------------------------------------------
create table rg.setores (
  codigo        text primary key check (codigo ~ '^[a-z][a-z_]{1,39}$'),
  nome          text not null unique check (char_length(nome) between 2 and 80),
  cor           text not null check (cor ~ '^#[0-9A-Fa-f]{6}$'),
  centro_custo  text check (centro_custo is null or char_length(centro_custo) <= 20),
  operacional   boolean not null default true,  -- pode abrir solicitações de compra
  ativo         boolean not null default true,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);

insert into rg.setores (codigo, nome, cor, centro_custo, operacional) values
  ('centro_cirurgico',     'Centro Cirúrgico',               '#0E7C86', '1.01.001', true),
  ('uti_adulto',           'UTI Adulto',                     '#C2410C', '1.01.002', true),
  ('uti_neonatal',         'UTI Neonatal',                   '#DB2777', '1.01.003', true),
  ('maternidade',          'Maternidade',                    '#9333EA', '1.01.004', true),
  ('pronto_socorro',       'Pronto Socorro',                 '#DC2626', '1.01.005', true),
  ('internacao',           'Internação Clínica',             '#0369A1', '1.01.006', true),
  ('imagem',               'Diagnóstico por Imagem',         '#4F46E5', '1.02.001', true),
  ('laboratorio',          'Laboratório de Análises',        '#0891B2', '1.02.002', true),
  ('farmacia',             'Farmácia Hospitalar',            '#16A34A', '1.03.001', true),
  ('cme',                  'Central de Material Esterilizado','#65A30D', '1.03.002', true),
  ('nutricao',             'Nutrição e Dietética',           '#CA8A04', '1.04.001', true),
  ('engenharia_clinica',   'Engenharia Clínica',             '#1D4ED8', '2.01.001', true),
  ('manutencao',           'Manutenção Predial',             '#A16207', '2.01.002', true),
  ('hotelaria',            'Hotelaria e Higienização',       '#7C3AED', '2.02.001', true),
  ('tecnologia',           'Tecnologia da Informação',       '#334155', '2.03.001', true),
  ('administracao',        'Administração Geral',            '#475569', '3.01.001', true),
  ('suprimentos',          'Compras e Suprimentos',          '#57534E', '3.02.001', false),
  ('financeiro',           'Financeiro',                     '#0F766E', '3.03.001', false),
  ('diretoria',            'Diretoria',                      '#1E3A5F', '3.04.001', false),
  ('controladoria',        'Controladoria e Auditoria',      '#6B7280', '3.05.001', false);

create table rg.configuracoes (
  chave          text primary key check (chave ~ '^[a-z_]{3,40}$'),
  valor          numeric(14,2) not null check (valor >= 0),
  descricao      text not null,
  atualizado_por uuid,
  atualizado_em  timestamptz not null default now()
);

insert into rg.configuracoes (chave, valor, descricao) values
  ('alcada_diretoria', 25000, 'Valor a partir do qual a Diretoria também aprova (solicitação e pedido de compra), em R$'),
  ('minimo_cotacoes',  3,     'Quantidade mínima de propostas por cotação; abaixo disso a escolha exige justificativa'),
  ('dias_alerta_entrega', 2,  'Dias de antecedência para alertar entregas próximas do prazo');

-- ---------------------------------------------------------------------
-- Usuários, sessões e histórico de senhas
-- ---------------------------------------------------------------------
create table rg.usuarios (
  id                       uuid primary key default gen_random_uuid(),
  email                    text not null check (email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  nome                     text not null check (char_length(nome) between 3 and 120),
  setor_codigo             text not null references rg.setores (codigo),
  cargo                    text check (cargo is null or char_length(cargo) <= 80),
  papel                    rg.papel_usuario not null default 'solicitante',
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

alter table rg.configuracoes add constraint configuracoes_usuario_fk foreign key (atualizado_por) references rg.usuarios (id);

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
-- Catálogo: categorias e materiais
-- ---------------------------------------------------------------------
create table rg.categorias (
  id            uuid primary key default gen_random_uuid(),
  nome          text not null check (char_length(nome) between 2 and 80),
  descricao     text check (descricao is null or char_length(descricao) <= 400),
  cor           text not null default '#475569' check (cor ~ '^#[0-9A-Fa-f]{6}$'),
  ativo         boolean not null default true,
  criado_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);
create unique index categorias_nome_uk on rg.categorias (lower(nome));

create sequence rg.material_codigo_seq;

create table rg.materiais (
  id                uuid primary key default gen_random_uuid(),
  codigo            text not null unique,
  nome              text not null check (char_length(nome) between 3 and 160),
  descricao         text check (descricao is null or char_length(descricao) <= 1000),
  categoria_id      uuid not null references rg.categorias (id),
  unidade           text not null check (unidade ~ '^[A-Z]{1,4}$'),
  preco_referencia  numeric(14,2) check (preco_referencia is null or preco_referencia >= 0),
  ultimo_preco      numeric(14,2),
  ultima_compra_em  timestamptz,
  ativo             boolean not null default true,
  criado_por        uuid references rg.usuarios (id),
  criado_em         timestamptz not null default now(),
  atualizado_em     timestamptz not null default now()
);
create index materiais_categoria_idx on rg.materiais (categoria_id);
create index materiais_nome_idx on rg.materiais (lower(nome));

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
  cidade         text check (cidade is null or char_length(cidade) <= 80),
  uf             text check (uf is null or uf ~ '^[A-Z]{2}$'),
  observacoes    text check (observacoes is null or char_length(observacoes) <= 1000),
  ativo          boolean not null default true,
  criado_por     uuid references rg.usuarios (id),
  criado_em      timestamptz not null default now(),
  atualizado_em  timestamptz not null default now()
);
create index fornecedores_nome_idx on rg.fornecedores (lower(razao_social));

-- ---------------------------------------------------------------------
-- Solicitações de compra e seus itens
-- ---------------------------------------------------------------------
create sequence rg.solicitacao_codigo_seq;

create table rg.solicitacoes (
  id                         uuid primary key default gen_random_uuid(),
  codigo                     text not null unique,
  tipo                       rg.tipo_solicitacao not null,
  titulo                     text not null check (char_length(titulo) between 5 and 160),
  descricao                  text check (descricao is null or char_length(descricao) <= 5000),
  justificativa              text not null check (char_length(btrim(justificativa)) >= 20 and char_length(justificativa) <= 5000),
  setor_codigo               text not null references rg.setores (codigo),
  urgencia                   rg.urgencia not null default 'normal',
  status                     rg.status_solicitacao not null default 'aguardando_gestor',
  local_entrega              text check (local_entrega is null or char_length(local_entrega) <= 160),
  data_necessidade           date,
  valor_final                numeric(14,2) check (valor_final is null or valor_final >= 0),
  solicitante_id             uuid not null references rg.usuarios (id),
  aberta_por_gestor          boolean not null default false,
  comprador_id               uuid references rg.usuarios (id),
  cotacao_vencedora_id       uuid,
  justificativa_escolha      text check (justificativa_escolha is null or char_length(justificativa_escolha) <= 2000),
  motivo_devolucao           text check (motivo_devolucao is null or char_length(motivo_devolucao) <= 2000),
  motivo_reprovacao          text check (motivo_reprovacao is null or char_length(motivo_reprovacao) <= 2000),
  motivo_cancelamento        text check (motivo_cancelamento is null or char_length(motivo_cancelamento) <= 2000),
  aprovado_gestor_por        uuid references rg.usuarios (id),
  aprovado_gestor_em         timestamptz,
  aprovado_diretoria_por     uuid references rg.usuarios (id),
  aprovado_diretoria_em      timestamptz,
  aprovado_em                timestamptz,
  rodada                     int not null default 1,
  versao                     int not null default 1,
  sla_prazo_limite           timestamptz not null,
  sla_concluido_em           timestamptz,
  sla_alerta_notificado_em   timestamptz,
  sla_estouro_notificado_em  timestamptz,
  cotacao_iniciada_em        timestamptz,
  fornecedor_definido_em     timestamptz,
  pedido_emitido_em          timestamptz,
  finalizado_em              timestamptz,
  criado_em                  timestamptz not null default now(),
  atualizado_em              timestamptz not null default now()
);
create index solicitacoes_status_idx   on rg.solicitacoes (status);
create index solicitacoes_setor_idx    on rg.solicitacoes (setor_codigo, criado_em desc);
create index solicitacoes_criado_idx   on rg.solicitacoes (criado_em desc);
create index solicitacoes_solic_idx    on rg.solicitacoes (solicitante_id);
create index solicitacoes_comprador_idx on rg.solicitacoes (comprador_id);
create index solicitacoes_sla_idx      on rg.solicitacoes (sla_prazo_limite) where sla_concluido_em is null;
create index solicitacoes_busca_idx    on rg.solicitacoes using gin (to_tsvector('portuguese', titulo || ' ' || coalesce(descricao, '')));

create table rg.solicitacao_itens (
  id                       uuid primary key default gen_random_uuid(),
  solicitacao_id           uuid not null references rg.solicitacoes (id) on delete cascade,
  ordem                    int not null default 1,
  material_id              uuid references rg.materiais (id),
  descricao                text not null check (char_length(descricao) between 2 and 300),
  unidade                  text not null check (unidade ~ '^[A-Z]{1,4}$'),
  quantidade               numeric(12,3) not null check (quantidade > 0 and quantidade <= 1000000),
  valor_unitario_estimado  numeric(14,2) not null default 0 check (valor_unitario_estimado >= 0),
  observacao               text check (observacao is null or char_length(observacao) <= 500),
  criado_em                timestamptz not null default now()
);
create index solicitacao_itens_solic_idx on rg.solicitacao_itens (solicitacao_id, ordem);
create index solicitacao_itens_material_idx on rg.solicitacao_itens (material_id);

-- ---------------------------------------------------------------------
-- Cotações: propostas de fornecedores (preenchidas manualmente)
-- ---------------------------------------------------------------------
create table rg.cotacoes (
  id                   uuid primary key default gen_random_uuid(),
  solicitacao_id       uuid not null references rg.solicitacoes (id),
  fornecedor_id        uuid not null references rg.fornecedores (id),
  anexo_id             uuid,
  numero_proposta      text check (numero_proposta is null or char_length(numero_proposta) <= 60),
  data_proposta        date,
  validade_proposta    date,
  prazo_entrega_dias   int not null check (prazo_entrega_dias between 0 and 3650),
  condicoes_pagamento  text check (condicoes_pagamento is null or char_length(condicoes_pagamento) <= 300),
  frete                numeric(14,2) not null default 0 check (frete >= 0),
  desconto             numeric(14,2) not null default 0 check (desconto >= 0),
  valor_itens          numeric(14,2) not null default 0 check (valor_itens >= 0),
  valor_total          numeric(14,2) not null default 0 check (valor_total >= 0),
  observacoes          text check (observacoes is null or char_length(observacoes) <= 2000),
  selecionada          boolean not null default false,
  criado_por           uuid not null references rg.usuarios (id),
  criado_em            timestamptz not null default now(),
  atualizado_em        timestamptz not null default now(),
  constraint cotacoes_fornecedor_uk unique (solicitacao_id, fornecedor_id)
);
create unique index cotacoes_vencedora_uk on rg.cotacoes (solicitacao_id) where selecionada;
create index cotacoes_fornecedor_idx on rg.cotacoes (fornecedor_id);

create table rg.cotacao_itens (
  id                   uuid primary key default gen_random_uuid(),
  cotacao_id           uuid not null references rg.cotacoes (id) on delete cascade,
  solicitacao_item_id  uuid not null references rg.solicitacao_itens (id),
  quantidade           numeric(12,3) not null check (quantidade > 0),
  valor_unitario       numeric(14,2) not null check (valor_unitario >= 0),
  marca                text check (marca is null or char_length(marca) <= 120),
  observacao           text check (observacao is null or char_length(observacao) <= 300),
  constraint cotacao_itens_uk unique (cotacao_id, solicitacao_item_id)
);

alter table rg.solicitacoes
  add constraint solicitacoes_cotacao_vencedora_fk foreign key (cotacao_vencedora_id) references rg.cotacoes (id);

-- ---------------------------------------------------------------------
-- Pedidos de compra
-- ---------------------------------------------------------------------
create sequence rg.pedido_codigo_seq;

create table rg.pedidos (
  id                        uuid primary key default gen_random_uuid(),
  codigo                    text not null unique,
  solicitacao_id            uuid not null references rg.solicitacoes (id),
  cotacao_id                uuid not null references rg.cotacoes (id),
  fornecedor_id             uuid not null references rg.fornecedores (id),
  status                    rg.status_pedido not null default 'aguardando_financeiro',
  valor_itens               numeric(14,2) not null default 0 check (valor_itens >= 0),
  frete                     numeric(14,2) not null default 0 check (frete >= 0),
  desconto                  numeric(14,2) not null default 0 check (desconto >= 0),
  valor_total               numeric(14,2) not null default 0 check (valor_total >= 0),
  condicoes_pagamento       text check (condicoes_pagamento is null or char_length(condicoes_pagamento) <= 300),
  prazo_entrega_dias        int not null default 0 check (prazo_entrega_dias between 0 and 3650),
  data_prevista_entrega     date,
  local_entrega             text check (local_entrega is null or char_length(local_entrega) <= 160),
  observacoes               text check (observacoes is null or char_length(observacoes) <= 2000),
  comprador_id              uuid not null references rg.usuarios (id),
  exige_diretoria           boolean not null default false,
  aprovado_financeiro_por   uuid references rg.usuarios (id),
  aprovado_financeiro_em    timestamptz,
  parecer_financeiro        text check (parecer_financeiro is null or char_length(parecer_financeiro) <= 2000),
  aprovado_diretoria_por    uuid references rg.usuarios (id),
  aprovado_diretoria_em     timestamptz,
  parecer_diretoria         text check (parecer_diretoria is null or char_length(parecer_diretoria) <= 2000),
  enviado_por               uuid references rg.usuarios (id),
  enviado_em                timestamptz,
  motivo_reprovacao         text check (motivo_reprovacao is null or char_length(motivo_reprovacao) <= 2000),
  motivo_cancelamento       text check (motivo_cancelamento is null or char_length(motivo_cancelamento) <= 2000),
  encerrado_com_pendencia   boolean not null default false,
  justificativa_encerramento text check (justificativa_encerramento is null or char_length(justificativa_encerramento) <= 2000),
  atraso_notificado_em      timestamptz,
  concluido_em              timestamptz,
  versao                    int not null default 1,
  criado_em                 timestamptz not null default now(),
  atualizado_em             timestamptz not null default now()
);
create unique index pedidos_ativo_uk on rg.pedidos (solicitacao_id) where status not in ('reprovado', 'cancelado');
create index pedidos_status_idx on rg.pedidos (status);
create index pedidos_fornecedor_idx on rg.pedidos (fornecedor_id);
create index pedidos_criado_idx on rg.pedidos (criado_em desc);

create table rg.pedido_itens (
  id                   uuid primary key default gen_random_uuid(),
  pedido_id            uuid not null references rg.pedidos (id),
  solicitacao_item_id  uuid not null references rg.solicitacao_itens (id),
  material_id          uuid references rg.materiais (id),
  ordem                int not null default 1,
  descricao            text not null,
  unidade              text not null,
  marca                text,
  quantidade           numeric(12,3) not null check (quantidade > 0),
  valor_unitario       numeric(14,2) not null check (valor_unitario >= 0),
  quantidade_recebida  numeric(12,3) not null default 0 check (quantidade_recebida >= 0),
  constraint pedido_itens_recebido_ck check (quantidade_recebida <= quantidade)
);
create index pedido_itens_pedido_idx on rg.pedido_itens (pedido_id, ordem);

-- ---------------------------------------------------------------------
-- Recebimento e conferência
-- ---------------------------------------------------------------------
create sequence rg.recebimento_codigo_seq;

create table rg.recebimentos (
  id                uuid primary key default gen_random_uuid(),
  codigo            text not null unique,
  pedido_id         uuid not null references rg.pedidos (id),
  solicitacao_id    uuid not null references rg.solicitacoes (id),
  nota_fiscal       text not null check (char_length(nota_fiscal) between 1 and 60),
  data_emissao_nf   date,
  valor_nf          numeric(14,2) check (valor_nf is null or valor_nf >= 0),
  situacao          rg.situacao_recebimento not null default 'conforme',
  observacoes       text check (observacoes is null or char_length(observacoes) <= 2000),
  processado        boolean not null default false,
  recebido_por      uuid not null references rg.usuarios (id),
  recebido_em       timestamptz not null default now(),
  criado_em         timestamptz not null default now()
);
create index recebimentos_pedido_idx on rg.recebimentos (pedido_id, recebido_em);
create index recebimentos_solic_idx on rg.recebimentos (solicitacao_id);

create table rg.recebimento_itens (
  id                  uuid primary key default gen_random_uuid(),
  recebimento_id      uuid not null references rg.recebimentos (id),
  pedido_item_id      uuid not null references rg.pedido_itens (id),
  quantidade_recebida numeric(12,3) not null check (quantidade_recebida >= 0),
  quantidade_aceita   numeric(12,3) not null check (quantidade_aceita >= 0),
  motivo_divergencia  text check (motivo_divergencia is null or char_length(motivo_divergencia) <= 500),
  constraint recebimento_itens_aceita_ck check (quantidade_aceita <= quantidade_recebida),
  constraint recebimento_itens_divergencia_ck check (
    quantidade_aceita = quantidade_recebida or char_length(btrim(coalesce(motivo_divergencia, ''))) >= 5),
  constraint recebimento_itens_uk unique (recebimento_id, pedido_item_id)
);

-- ---------------------------------------------------------------------
-- Anexos (orçamentos, propostas, notas fiscais, fotos) — sem leitura automática
-- ---------------------------------------------------------------------
create table rg.anexos (
  id                 uuid primary key default gen_random_uuid(),
  solicitacao_id     uuid not null references rg.solicitacoes (id),
  recebimento_id     uuid references rg.recebimentos (id),
  origem             rg.origem_anexo not null,
  tipo_documento     rg.tipo_documento not null default 'orcamento',
  nome_original      text not null check (char_length(nome_original) between 1 and 200),
  mime               text not null,
  tamanho            int not null check (tamanho > 0 and tamanho <= 10485760),
  sha256             text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  caminho            text not null,
  rodada             int not null default 1,
  enviado_por        uuid not null references rg.usuarios (id),
  removido_em        timestamptz,
  removido_por       uuid references rg.usuarios (id),
  criado_em          timestamptz not null default now(),
  constraint anexos_recebimento_ck check ((origem = 'recebimento') or recebimento_id is null)
);
create index anexos_solicitacao_idx on rg.anexos (solicitacao_id);
create index anexos_recebimento_idx on rg.anexos (recebimento_id) where recebimento_id is not null;

alter table rg.cotacoes add constraint cotacoes_anexo_fk foreign key (anexo_id) references rg.anexos (id);

-- ---------------------------------------------------------------------
-- Aprovações (registro de cada decisão, alimentado por triggers)
-- ---------------------------------------------------------------------
create table rg.aprovacoes (
  id              bigint generated always as identity primary key,
  solicitacao_id  uuid not null references rg.solicitacoes (id),
  pedido_id       uuid references rg.pedidos (id),
  nivel           rg.nivel_aprovacao not null,
  decisao         rg.decisao_aprovacao not null,
  usuario_id      uuid references rg.usuarios (id),
  parecer         text,
  valor           numeric(14,2),
  criado_em       timestamptz not null default now()
);
create index aprovacoes_solic_idx on rg.aprovacoes (solicitacao_id, criado_em);
create index aprovacoes_usuario_idx on rg.aprovacoes (usuario_id, criado_em desc);
create index aprovacoes_criado_idx on rg.aprovacoes (criado_em desc);

-- ---------------------------------------------------------------------
-- Assinaturas eletrônicas (imutáveis)
-- ---------------------------------------------------------------------
create table rg.assinaturas (
  id                  uuid primary key default gen_random_uuid(),
  solicitacao_id      uuid not null references rg.solicitacoes (id),
  pedido_id           uuid references rg.pedidos (id),
  recebimento_id      uuid references rg.recebimentos (id),
  usuario_id          uuid not null references rg.usuarios (id),
  papel               rg.papel_usuario not null,
  acao                text not null,
  status_solicitacao  text not null,
  status_pedido       text,
  ip                  text not null,
  user_agent          text,
  assinado_em         timestamptz not null,
  conteudo_hash       text not null check (conteudo_hash ~ '^[0-9a-f]{64}$'),
  hash_autenticidade  text not null unique check (hash_autenticidade ~ '^[0-9a-f]{64}$'),
  algoritmo           text not null default 'HMAC-SHA-256',
  txid                bigint not null default txid_current(),
  criado_em           timestamptz not null default now()
);
create index assinaturas_solicitacao_idx on rg.assinaturas (solicitacao_id, assinado_em);
create index assinaturas_txid_idx on rg.assinaturas (txid);

-- ---------------------------------------------------------------------
-- Histórico do fluxo e notificações
-- ---------------------------------------------------------------------
create table rg.solicitacao_historico (
  id              bigint generated always as identity primary key,
  solicitacao_id  uuid not null references rg.solicitacoes (id),
  pedido_id       uuid references rg.pedidos (id),
  autor_id        uuid references rg.usuarios (id),
  acao            text not null,
  status_de       text,
  status_para     text,
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
