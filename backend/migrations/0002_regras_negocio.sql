-- =====================================================================
-- Hospital Rio Grande · Compras — 0002: contexto de segurança, regras de negócio e triggers
-- As regras valem mesmo para SQL direto no papel da aplicação (defesa em profundidade).
-- =====================================================================

-- ---------------------------------------------------------------------
-- Contexto da requisição (definido pela API a cada transação via set_config)
--   app.user_id    uuid do usuário autenticado
--   app.ip         IP de origem
--   app.contexto   'sistema' para rotinas internas (login, jobs)
--   app.observacao texto livre registrado no histórico do fluxo
-- ---------------------------------------------------------------------
create function rg.usuario_atual_id() returns uuid
language sql stable
as $$ select nullif(current_setting('app.user_id', true), '')::uuid $$;

create function rg.eh_sistema() returns boolean
language sql stable
as $$ select coalesce(current_setting('app.contexto', true), '') = 'sistema' $$;

create function rg.papel_atual() returns rg.papel_usuario
language sql stable security definer
set search_path = rg, pg_temp
as $$
  select papel from rg.usuarios
   where id = rg.usuario_atual_id() and status = 'aprovado'
$$;

create function rg.setor_atual() returns text
language sql stable security definer
set search_path = rg, pg_temp
as $$
  select setor_codigo from rg.usuarios
   where id = rg.usuario_atual_id() and status = 'aprovado'
$$;

create function rg.config_num(p_chave text) returns numeric
language sql stable security definer
set search_path = rg, pg_temp
as $$ select valor from rg.configuracoes where chave = p_chave $$;

create function rg.observacao_atual() returns text
language sql stable
as $$ select nullif(btrim(coalesce(current_setting('app.observacao', true), '')), '') $$;

-- Valor estimado = soma dos itens (sempre derivado, nunca informado pelo cliente).
create function rg.valor_estimado(p_solicitacao uuid) returns numeric
language sql stable security definer
set search_path = rg, pg_temp
as $$
  select coalesce(sum(round(quantidade * valor_unitario_estimado, 2)), 0)::numeric(14,2)
    from rg.solicitacao_itens where solicitacao_id = p_solicitacao
$$;

create function rg.sla_situacao(p_status rg.status_solicitacao, p_prazo timestamptz, p_concluido timestamptz)
returns text
language sql stable
as $$
  select case
    when p_concluido is not null then
      case when p_concluido <= p_prazo then 'cumprido' else 'cumprido_com_atraso' end
    when rg.status_terminal(p_status) then 'cumprido'
    when now() > p_prazo then 'estourado'
    when p_prazo - now() < interval '24 hours' then 'alerta'
    else 'dentro_prazo'
  end
$$;

create function rg.hoje() returns date
language sql stable
as $$ select (now() at time zone 'America/Sao_Paulo')::date $$;

-- ---------------------------------------------------------------------
-- Notificações (sempre via função; a aplicação não insere diretamente)
-- ---------------------------------------------------------------------
create function rg.notificar(p_dest uuid, p_titulo text, p_mensagem text,
                             p_tipo rg.tipo_notificacao default 'info', p_link text default null)
returns void
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  if p_dest is null or p_dest is not distinct from rg.usuario_atual_id() then
    return;  -- não notifica o próprio autor da ação
  end if;
  insert into rg.notificacoes (destinatario_id, tipo, titulo, mensagem, link)
  values (p_dest, p_tipo, p_titulo, p_mensagem, p_link);
end $$;

create function rg.notificar_papel(p_papel rg.papel_usuario, p_titulo text, p_mensagem text,
                                   p_tipo rg.tipo_notificacao default 'info', p_link text default null)
returns void
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare r record;
begin
  for r in select id from rg.usuarios where papel = p_papel and status = 'aprovado' loop
    perform rg.notificar(r.id, p_titulo, p_mensagem, p_tipo, p_link);
  end loop;
end $$;

create function rg.notificar_setor(p_papel rg.papel_usuario, p_setor text, p_titulo text, p_mensagem text,
                                   p_tipo rg.tipo_notificacao default 'info', p_link text default null)
returns void
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare r record;
begin
  for r in select id from rg.usuarios where papel = p_papel and setor_codigo = p_setor and status = 'aprovado' loop
    perform rg.notificar(r.id, p_titulo, p_mensagem, p_tipo, p_link);
  end loop;
end $$;

-- ---------------------------------------------------------------------
-- Triggers genéricos
-- ---------------------------------------------------------------------
create function rg.tg_atualizado_em() returns trigger
language plpgsql
as $$
begin
  new.atualizado_em := now();
  return new;
end $$;

create trigger setores_atualizado      before update on rg.setores      for each row execute function rg.tg_atualizado_em();
create trigger usuarios_atualizado     before update on rg.usuarios     for each row execute function rg.tg_atualizado_em();
create trigger categorias_atualizado   before update on rg.categorias   for each row execute function rg.tg_atualizado_em();
create trigger materiais_atualizado    before update on rg.materiais    for each row execute function rg.tg_atualizado_em();
create trigger fornecedores_atualizado before update on rg.fornecedores for each row execute function rg.tg_atualizado_em();
create trigger solicitacoes_atualizado before update on rg.solicitacoes for each row execute function rg.tg_atualizado_em();
create trigger cotacoes_atualizado     before update on rg.cotacoes     for each row execute function rg.tg_atualizado_em();
create trigger pedidos_atualizado      before update on rg.pedidos      for each row execute function rg.tg_atualizado_em();

create function rg.tg_configuracao_atualizar() returns trigger
language plpgsql
as $$
begin
  new.atualizado_em := now();
  new.atualizado_por := rg.usuario_atual_id();
  return new;
end $$;
create trigger configuracoes_atualizar before update on rg.configuracoes for each row execute function rg.tg_configuracao_atualizar();

-- Auditoria genérica: registra antes/depois de cada alteração.
create function audit.tg_registrar() returns trigger
language plpgsql security definer
set search_path = audit, rg, pg_temp
as $$
declare
  v_excluir text[] := array['senha_hash', 'telefone_cript', 'token_hash', 'csrf_token'];
  v_ruido   text[] := array['atualizado_em', 'ultimo_acesso_em'];
  v_antes   jsonb;
  v_depois  jsonb;
  v_campos  text[];
begin
  if tg_op in ('UPDATE', 'DELETE') then v_antes := to_jsonb(old) - v_excluir; end if;
  if tg_op in ('INSERT', 'UPDATE') then v_depois := to_jsonb(new) - v_excluir; end if;

  if tg_op = 'UPDATE' then
    select array_agg(d.key order by d.key) into v_campos
      from jsonb_each(to_jsonb(new)) d
     where d.value is distinct from to_jsonb(old) -> d.key;
    if v_campos is null or v_campos <@ v_ruido then
      return null;
    end if;
  end if;

  insert into audit.eventos (usuario_id, ip, tabela, registro_id, operacao, campos_alterados, dados_antes, dados_depois)
  values (rg.usuario_atual_id(), nullif(current_setting('app.ip', true), ''),
          tg_table_schema || '.' || tg_table_name,
          coalesce(v_depois ->> 'id', v_antes ->> 'id', v_depois ->> 'chave', v_antes ->> 'chave', v_depois ->> 'codigo'),
          tg_op, v_campos, v_antes, v_depois);
  return null;
end $$;

create trigger audit_setores       after insert or update or delete on rg.setores           for each row execute function audit.tg_registrar();
create trigger audit_configuracoes after insert or update or delete on rg.configuracoes     for each row execute function audit.tg_registrar();
create trigger audit_usuarios      after insert or update or delete on rg.usuarios          for each row execute function audit.tg_registrar();
create trigger audit_categorias    after insert or update or delete on rg.categorias        for each row execute function audit.tg_registrar();
create trigger audit_materiais     after insert or update or delete on rg.materiais         for each row execute function audit.tg_registrar();
create trigger audit_fornecedores  after insert or update or delete on rg.fornecedores      for each row execute function audit.tg_registrar();
create trigger audit_solicitacoes  after insert or update or delete on rg.solicitacoes      for each row execute function audit.tg_registrar();
create trigger audit_sol_itens     after insert or update or delete on rg.solicitacao_itens for each row execute function audit.tg_registrar();
create trigger audit_cotacoes      after insert or update or delete on rg.cotacoes          for each row execute function audit.tg_registrar();
create trigger audit_cot_itens     after insert or update or delete on rg.cotacao_itens     for each row execute function audit.tg_registrar();
create trigger audit_pedidos       after insert or update or delete on rg.pedidos           for each row execute function audit.tg_registrar();
create trigger audit_recebimentos  after insert or update on rg.recebimentos                for each row execute function audit.tg_registrar();
create trigger audit_rec_itens     after insert on rg.recebimento_itens                     for each row execute function audit.tg_registrar();
create trigger audit_anexos        after insert or update or delete on rg.anexos            for each row execute function audit.tg_registrar();
create trigger audit_assinaturas   after insert on rg.assinaturas                           for each row execute function audit.tg_registrar();

-- Eventos de aplicação (login, download, exportações etc.)
create function audit.registrar_evento(p_operacao text, p_tabela text, p_registro text, p_detalhes jsonb default null)
returns void
language sql security definer
set search_path = audit, rg, pg_temp
as $$
  insert into audit.eventos (usuario_id, ip, tabela, registro_id, operacao, dados_depois)
  values (rg.usuario_atual_id(), nullif(current_setting('app.ip', true), ''), p_tabela, p_registro, p_operacao, p_detalhes);
$$;

-- Registros de auditoria, assinaturas, aprovações e histórico são imutáveis.
create function rg.tg_imutavel() returns trigger
language plpgsql
as $$
begin
  raise exception 'Registro imutável: % não permite %', tg_table_name, tg_op using errcode = 'P0001';
end $$;

create trigger eventos_imutavel     before update or delete on audit.eventos             for each row execute function rg.tg_imutavel();
create trigger assinaturas_imutavel before update or delete on rg.assinaturas            for each row execute function rg.tg_imutavel();
create trigger historico_imutavel   before update or delete on rg.solicitacao_historico  for each row execute function rg.tg_imutavel();
create trigger aprovacoes_imutavel  before update or delete on rg.aprovacoes             for each row execute function rg.tg_imutavel();
create trigger rec_itens_imutavel   before update or delete on rg.recebimento_itens      for each row execute function rg.tg_imutavel();

-- Emissão de eventos em tempo real (LISTEN rg_eventos na API → WebSocket).
create function rg.tg_emitir_evento() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_row     jsonb := case when tg_op = 'DELETE' then to_jsonb(old) else to_jsonb(new) end;
  v_sid     uuid;
  v_setor   text;
  v_status  text;
  v_aprov   boolean;
begin
  if tg_table_name = 'solicitacoes' then
    v_sid := (v_row ->> 'id')::uuid;
  elsif v_row ? 'solicitacao_id' then
    v_sid := (v_row ->> 'solicitacao_id')::uuid;
  end if;
  if v_sid is not null then
    select setor_codigo, status::text, aprovado_em is not null into v_setor, v_status, v_aprov
      from rg.solicitacoes where id = v_sid;
  end if;
  perform pg_notify('rg_eventos', jsonb_build_object(
    'tabela', tg_table_name,
    'op', lower(tg_op),
    'id', v_row ->> 'id',
    'solicitacao_id', v_sid,
    'setor', v_setor,
    'status', v_status,
    'aprovada', coalesce(v_aprov, false),
    'destinatario', v_row ->> 'destinatario_id',
    'usuario', case when tg_table_name = 'usuarios' then v_row ->> 'id' end
  )::text);
  return null;
end $$;

create trigger evt_solicitacoes after insert or update on rg.solicitacoes        for each row execute function rg.tg_emitir_evento();
create trigger evt_cotacoes     after insert or update or delete on rg.cotacoes  for each row execute function rg.tg_emitir_evento();
create trigger evt_pedidos      after insert or update on rg.pedidos             for each row execute function rg.tg_emitir_evento();
create trigger evt_recebimentos after insert on rg.recebimentos                  for each row execute function rg.tg_emitir_evento();
create trigger evt_anexos       after insert or update on rg.anexos              for each row execute function rg.tg_emitir_evento();
create trigger evt_notificacoes after insert on rg.notificacoes                  for each row execute function rg.tg_emitir_evento();
create trigger evt_usuarios     after insert or update of status, papel, setor_codigo on rg.usuarios for each row execute function rg.tg_emitir_evento();

-- ---------------------------------------------------------------------
-- Usuários: proteção de campos privilegiados e notificação de cadastro
-- ---------------------------------------------------------------------
create function rg.tg_usuario_proteger() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  if rg.eh_sistema() or rg.papel_atual() = 'admin' then
    if tg_op = 'UPDATE' and new.id = rg.usuario_atual_id()
       and (new.papel is distinct from old.papel or new.status is distinct from old.status) then
      raise exception 'Administradores não podem alterar o próprio perfil de acesso ou situação' using errcode = 'P0001';
    end if;
    return new;
  end if;

  if tg_op = 'INSERT' then
    raise exception 'Cadastro de usuário não permitido neste contexto' using errcode = '42501';
  end if;

  if new.papel is distinct from old.papel
     or new.status is distinct from old.status
     or new.setor_codigo is distinct from old.setor_codigo
     or new.email is distinct from old.email
     or new.analisado_por is distinct from old.analisado_por
     or new.tentativas_falhas is distinct from old.tentativas_falhas
     or new.bloqueado_ate is distinct from old.bloqueado_ate
     or new.anonimizado_em is distinct from old.anonimizado_em then
    raise exception 'Alteração de campo privilegiado não permitida' using errcode = '42501';
  end if;
  return new;
end $$;

create trigger usuarios_proteger before insert or update on rg.usuarios
  for each row execute function rg.tg_usuario_proteger();

create function rg.tg_usuario_eventos() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  if tg_op = 'INSERT' and new.status = 'pendente' then
    perform rg.notificar_papel('admin', 'Novo cadastro aguardando aprovação',
      new.nome || ' (' || new.email || ') solicitou acesso.', 'alerta', '/usuarios?status=pendente');
  elsif tg_op = 'UPDATE' and new.status is distinct from old.status
        and new.status = 'aprovado' and old.status = 'pendente' then
    perform rg.notificar(new.id, 'Acesso aprovado', 'Seu cadastro foi aprovado. Bem-vindo(a) ao Compras RG.', 'sucesso', '/');
  end if;
  return null;
end $$;

create trigger usuarios_eventos after insert or update of status on rg.usuarios
  for each row execute function rg.tg_usuario_eventos();

create function rg.tg_senhas_historico_podar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  delete from rg.senhas_historico
   where usuario_id = new.usuario_id
     and id not in (select id from rg.senhas_historico where usuario_id = new.usuario_id
                    order by criado_em desc, id desc limit 5);
  return null;
end $$;

create trigger senhas_historico_podar after insert on rg.senhas_historico
  for each row execute function rg.tg_senhas_historico_podar();

-- ---------------------------------------------------------------------
-- Catálogo: código sequencial de materiais
-- ---------------------------------------------------------------------
create function rg.tg_material_inserir() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  new.codigo := 'MAT-' || lpad(nextval('rg.material_codigo_seq')::text, 5, '0');
  new.ultimo_preco := null;
  new.ultima_compra_em := null;
  return new;
end $$;

create trigger materiais_inserir before insert on rg.materiais
  for each row execute function rg.tg_material_inserir();

create function rg.tg_material_validar() returns trigger
language plpgsql
as $$
begin
  if new.codigo <> old.codigo then
    raise exception 'O código do material não pode ser alterado' using errcode = 'P0001';
  end if;
  return new;
end $$;

create trigger materiais_validar before update on rg.materiais
  for each row execute function rg.tg_material_validar();

-- =====================================================================
-- SOLICITAÇÕES
-- =====================================================================
create function rg.tg_solicitacao_inserir() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_setor rg.setores;
  v_papel rg.papel_usuario := rg.papel_atual();
begin
  if v_papel is null or v_papel not in ('solicitante', 'gestor') then
    raise exception 'Somente solicitantes e gestores de setor abrem solicitações de compra' using errcode = '42501';
  end if;
  select * into v_setor from rg.setores where codigo = new.setor_codigo;
  if not v_setor.operacional or not v_setor.ativo then
    raise exception 'O setor % não pode abrir solicitações de compra', new.setor_codigo using errcode = 'P0001';
  end if;
  new.aberta_por_gestor := v_papel = 'gestor';
  new.status := case when v_papel = 'gestor' then 'aguardando_diretoria' else 'aguardando_gestor' end;
  new.criado_em := now();
  new.atualizado_em := now();
  new.codigo := 'SC-' || to_char(new.criado_em at time zone 'America/Sao_Paulo', 'YYYY') || '-'
                || lpad(nextval('rg.solicitacao_codigo_seq')::text, 5, '0');
  new.sla_prazo_limite := new.criado_em + rg.sla_intervalo(new.urgencia);
  new.rodada := 1;
  new.versao := 1;
  new.valor_final := null;
  new.comprador_id := null;
  new.cotacao_vencedora_id := null;
  new.justificativa_escolha := null;
  new.motivo_devolucao := null;
  new.motivo_reprovacao := null;
  new.motivo_cancelamento := null;
  new.aprovado_gestor_por := null;
  new.aprovado_gestor_em := null;
  new.aprovado_diretoria_por := null;
  new.aprovado_diretoria_em := null;
  new.aprovado_em := null;
  new.sla_concluido_em := null;
  new.cotacao_iniciada_em := null;
  new.fornecedor_definido_em := null;
  new.pedido_emitido_em := null;
  new.finalizado_em := null;
  return new;
end $$;

create trigger solicitacoes_inserir before insert on rg.solicitacoes
  for each row execute function rg.tg_solicitacao_inserir();

-- Máquina de estados da solicitação.
create function rg.tg_solicitacao_validar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_papel    rg.papel_usuario := rg.papel_atual();
  v_uid      uuid := rg.usuario_atual_id();
  v_setor    text := rg.setor_atual();
  v_do_setor boolean;
  v_ops      text[] := array['sla_alerta_notificado_em', 'sla_estouro_notificado_em', 'atualizado_em'];
  v_conteudo text[] := array['titulo', 'descricao', 'justificativa', 'tipo', 'urgencia', 'local_entrega', 'data_necessidade'];
  v_cot      rg.cotacoes;
  v_n        int;
  v_itens    int;
  v_menor    numeric;
  v_pedido   rg.status_pedido;
begin
  -- Alterações exclusivamente operacionais (marcadores de alerta de SLA)
  if (to_jsonb(new) - v_ops) = (to_jsonb(old) - v_ops) then
    return new;
  end if;

  if new.id <> old.id or new.codigo <> old.codigo or new.solicitante_id <> old.solicitante_id
     or new.setor_codigo <> old.setor_codigo or new.criado_em <> old.criado_em
     or new.aberta_por_gestor <> old.aberta_por_gestor then
    raise exception 'Campos estruturais da solicitação não podem ser alterados' using errcode = 'P0001';
  end if;
  if rg.status_terminal(old.status) then
    raise exception 'A solicitação % já foi encerrada', old.codigo using errcode = 'P0001';
  end if;
  if v_papel is null then
    raise exception 'Usuário sem permissão para alterar solicitações' using errcode = '42501';
  end if;
  if v_papel = 'auditoria' then
    raise exception 'O perfil Auditoria possui acesso somente leitura' using errcode = '42501';
  end if;
  v_do_setor := v_papel in ('solicitante', 'gestor') and v_setor = old.setor_codigo;

  -- Conteúdo: somente o setor, quando a solicitação foi devolvida para ajustes
  if exists (select 1 from unnest(v_conteudo) k where to_jsonb(new) -> k is distinct from to_jsonb(old) -> k)
     and not (v_do_setor and old.status = 'devolvida') then
    raise exception 'A solicitação só pode ser editada pelo setor quando devolvida para ajustes' using errcode = 'P0001';
  end if;

  if new.urgencia is distinct from old.urgencia then
    new.sla_prazo_limite := old.criado_em + rg.sla_intervalo(new.urgencia);
    new.sla_alerta_notificado_em := null;
    new.sla_estouro_notificado_em := null;
  else
    new.sla_prazo_limite := old.sla_prazo_limite;
  end if;

  -- Campos de controle são definidos exclusivamente pela máquina de estados
  new.rodada := old.rodada;
  new.aprovado_gestor_por := old.aprovado_gestor_por;
  new.aprovado_gestor_em := old.aprovado_gestor_em;
  new.aprovado_diretoria_por := old.aprovado_diretoria_por;
  new.aprovado_diretoria_em := old.aprovado_diretoria_em;
  new.aprovado_em := old.aprovado_em;
  new.cotacao_iniciada_em := old.cotacao_iniciada_em;
  new.fornecedor_definido_em := old.fornecedor_definido_em;
  new.pedido_emitido_em := old.pedido_emitido_em;
  new.finalizado_em := old.finalizado_em;
  new.sla_concluido_em := old.sla_concluido_em;
  new.valor_final := old.valor_final;
  if new.status is not distinct from old.status then
    new.comprador_id := old.comprador_id;
    new.cotacao_vencedora_id := old.cotacao_vencedora_id;
    new.justificativa_escolha := old.justificativa_escolha;
    new.motivo_devolucao := old.motivo_devolucao;
    new.motivo_reprovacao := old.motivo_reprovacao;
    new.motivo_cancelamento := old.motivo_cancelamento;
  end if;

  if new.status is distinct from old.status then
    if new.status <> 'devolvida' then new.motivo_devolucao := old.motivo_devolucao; end if;
    if new.status <> 'reprovada' then new.motivo_reprovacao := old.motivo_reprovacao; end if;
    if new.status <> 'cancelada' then new.motivo_cancelamento := old.motivo_cancelamento; end if;
    if new.status <> 'aguardando_pedido' then
      new.cotacao_vencedora_id := old.cotacao_vencedora_id;
      new.justificativa_escolha := old.justificativa_escolha;
    end if;
    if new.status <> 'em_cotacao' then new.comprador_id := old.comprador_id; end if;

    case
      -- 1. Aprovação do gestor do setor
      when old.status = 'aguardando_gestor' and new.status in ('aprovada', 'aguardando_diretoria', 'reprovada', 'devolvida') then
        if not (v_papel = 'gestor' and v_setor = old.setor_codigo) then
          raise exception 'Somente o gestor do setor aprova esta solicitação' using errcode = '42501';
        end if;
        if v_uid = old.solicitante_id then
          raise exception 'Segregação de funções: o gestor não pode aprovar a própria solicitação' using errcode = 'P0001';
        end if;
        if new.status in ('aprovada', 'aguardando_diretoria') then
          new.aprovado_gestor_por := v_uid;
          new.aprovado_gestor_em := now();
          new.status := case when rg.valor_estimado(old.id) >= coalesce(rg.config_num('alcada_diretoria'), 0)
                             then 'aguardando_diretoria' else 'aprovada' end;
        end if;

      -- 1b. Aprovação da Diretoria
      when old.status = 'aguardando_diretoria' and new.status in ('aprovada', 'reprovada', 'devolvida') then
        if v_papel <> 'diretoria' then
          raise exception 'Somente a Diretoria aprova solicitações acima da alçada' using errcode = '42501';
        end if;
        if new.status = 'aprovada' then
          new.aprovado_diretoria_por := v_uid;
          new.aprovado_diretoria_em := now();
        end if;

      -- Reenvio após ajustes
      when old.status = 'devolvida' and new.status in ('aguardando_gestor', 'aguardando_diretoria') then
        if not v_do_setor then
          raise exception 'Somente o setor solicitante pode reenviar a solicitação' using errcode = '42501';
        end if;
        new.status := case when old.aberta_por_gestor then 'aguardando_diretoria' else 'aguardando_gestor' end;
        new.rodada := old.rodada + 1;
        new.aprovado_gestor_por := null;
        new.aprovado_gestor_em := null;
        new.aprovado_diretoria_por := null;
        new.aprovado_diretoria_em := null;

      -- Cancelamento antes da aprovação
      when old.status in ('aguardando_gestor', 'aguardando_diretoria', 'devolvida') and new.status = 'cancelada' then
        if not (v_do_setor or v_papel = 'admin') then
          raise exception 'Somente o setor solicitante ou a administração pode cancelar' using errcode = '42501';
        end if;

      -- 2 → 3. Comprador assume a cotação
      when old.status = 'aprovada' and new.status = 'em_cotacao' then
        if v_papel <> 'comprador' then
          raise exception 'Somente o comprador inicia a cotação' using errcode = '42501';
        end if;
        new.comprador_id := v_uid;
        new.cotacao_iniciada_em := now();

      -- Cancelamento pelo setor de Compras
      when old.status in ('aprovada', 'em_cotacao', 'aguardando_pedido') and new.status = 'cancelada' then
        if v_papel not in ('comprador', 'admin') then
          raise exception 'Após a aprovação, somente Compras ou a administração pode cancelar' using errcode = '42501';
        end if;

      -- 3 → 4. Definição do fornecedor (proposta vencedora)
      when old.status = 'em_cotacao' and new.status = 'aguardando_pedido' then
        if v_papel <> 'comprador' then
          raise exception 'Somente o comprador define o fornecedor' using errcode = '42501';
        end if;
        select * into v_cot from rg.cotacoes where id = new.cotacao_vencedora_id;
        if v_cot.id is null or v_cot.solicitacao_id <> old.id or not v_cot.selecionada then
          raise exception 'Selecione a proposta vencedora' using errcode = 'P0001';
        end if;
        select count(*) into v_itens from rg.solicitacao_itens where solicitacao_id = old.id;
        if (select count(*) from rg.cotacao_itens where cotacao_id = v_cot.id) < v_itens then
          raise exception 'A proposta vencedora precisa cotar todos os itens da solicitação' using errcode = 'P0001';
        end if;
        select count(*) into v_n from rg.cotacoes where solicitacao_id = old.id;
        select min(c.valor_total) into v_menor from rg.cotacoes c
         where c.solicitacao_id = old.id
           and (select count(*) from rg.cotacao_itens ci where ci.cotacao_id = c.id) >= v_itens;
        if (v_n < coalesce(rg.config_num('minimo_cotacoes'), 1) or v_cot.valor_total > v_menor)
           and char_length(btrim(coalesce(new.justificativa_escolha, ''))) < 10 then
          raise exception 'Justifique a escolha (mínimo 10 caracteres): menos propostas que o mínimo ou proposta que não é a de menor valor'
            using errcode = 'P0001';
        end if;
        new.valor_final := v_cot.valor_total;
        new.fornecedor_definido_em := now();

      -- Reabertura da cotação pelo comprador
      when old.status = 'aguardando_pedido' and new.status = 'em_cotacao' then
        if v_papel <> 'comprador' then
          raise exception 'Somente o comprador reabre a cotação' using errcode = '42501';
        end if;
        new.cotacao_vencedora_id := null;
        new.justificativa_escolha := null;
        new.valor_final := null;
        new.fornecedor_definido_em := null;

      -- 4 → 5. Pedido de compra emitido (disparado pela inclusão do pedido)
      when old.status = 'aguardando_pedido' and new.status = 'em_pedido' then
        if v_papel <> 'comprador' then
          raise exception 'Somente o comprador emite o pedido de compra' using errcode = '42501';
        end if;
        if not exists (select 1 from rg.pedidos where solicitacao_id = old.id and status not in ('reprovado', 'cancelado')) then
          raise exception 'Emita o pedido de compra antes de avançar' using errcode = 'P0001';
        end if;
        new.pedido_emitido_em := now();
        new.sla_concluido_em := coalesce(old.sla_concluido_em, now());

      -- Pedido reprovado ou cancelado: a cotação é reaberta
      when old.status = 'em_pedido' and new.status = 'em_cotacao' then
        if v_papel not in ('financeiro', 'diretoria', 'comprador', 'admin') then
          raise exception 'Operação não permitida para o seu perfil' using errcode = '42501';
        end if;
        if exists (select 1 from rg.pedidos where solicitacao_id = old.id and status not in ('reprovado', 'cancelado')) then
          raise exception 'Existe pedido de compra ativo para esta solicitação' using errcode = 'P0001';
        end if;
        new.cotacao_vencedora_id := null;
        new.justificativa_escolha := null;
        new.valor_final := null;
        new.fornecedor_definido_em := null;
        new.pedido_emitido_em := null;
        new.sla_concluido_em := null;

      -- 6/7. Recebimento (disparado pelo processamento do recebimento)
      when old.status in ('em_pedido', 'recebida_parcial') and new.status in ('recebida_parcial', 'concluida') then
        if v_papel not in ('recebimento', 'comprador') then
          raise exception 'Somente o Recebimento registra entregas' using errcode = '42501';
        end if;
        select status into v_pedido from rg.pedidos
         where solicitacao_id = old.id and status not in ('reprovado', 'cancelado');
        if (new.status = 'concluida' and v_pedido is distinct from 'entregue')
           or (new.status = 'recebida_parcial' and v_pedido is distinct from 'entregue_parcial') then
          raise exception 'Situação do recebimento incompatível com o pedido de compra' using errcode = 'P0001';
        end if;

      else
        raise exception 'Transição inválida: % → %', old.status, new.status using errcode = 'P0001';
    end case;

    if new.status = 'aprovada' then
      new.aprovado_em := now();
    end if;
    if new.status = 'reprovada' and char_length(btrim(coalesce(new.motivo_reprovacao, ''))) < 10 then
      raise exception 'Informe o motivo da reprovação (mínimo 10 caracteres)' using errcode = 'P0001';
    end if;
    if new.status = 'devolvida' and char_length(btrim(coalesce(new.motivo_devolucao, ''))) < 10 then
      raise exception 'Informe o que precisa ser ajustado (mínimo 10 caracteres)' using errcode = 'P0001';
    end if;
    if new.status = 'cancelada' and char_length(btrim(coalesce(new.motivo_cancelamento, ''))) < 10 then
      raise exception 'Informe o motivo do cancelamento (mínimo 10 caracteres)' using errcode = 'P0001';
    end if;
    if new.status in ('reprovada', 'cancelada') then
      new.sla_concluido_em := coalesce(new.sla_concluido_em, now());
    end if;
    if rg.status_terminal(new.status) then
      new.finalizado_em := now();
    end if;
  end if;

  new.versao := old.versao + 1;
  return new;
end $$;

create trigger solicitacoes_validar before update on rg.solicitacoes
  for each row execute function rg.tg_solicitacao_validar();

-- Histórico, registro de aprovações e notificações após cada movimentação
create function rg.tg_solicitacao_movimentar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_obs   text := rg.observacao_atual();
  v_link  text := '/solicitacoes/' || new.id;
  v_ref   text := new.codigo || ' — ' || new.titulo;
  v_nivel rg.nivel_aprovacao;
  v_dec   rg.decisao_aprovacao;
begin
  if tg_op = 'INSERT' then
    insert into rg.solicitacao_historico (solicitacao_id, autor_id, acao, status_de, status_para, observacao)
    values (new.id, rg.usuario_atual_id(), 'criacao', null, new.status::text,
            coalesce(v_obs, case when new.aberta_por_gestor then 'Aberta pelo gestor do setor: aprovação direta da Diretoria' end));
    if new.status = 'aguardando_gestor' then
      perform rg.notificar_setor('gestor', new.setor_codigo, 'Solicitação aguardando sua aprovação', v_ref, 'info', v_link);
    else
      perform rg.notificar_papel('diretoria', 'Solicitação aguardando aprovação da Diretoria', v_ref, 'info', v_link);
    end if;
    return null;
  end if;

  if new.status is not distinct from old.status then
    if (new.titulo, new.descricao, new.justificativa, new.tipo, new.urgencia, new.local_entrega, new.data_necessidade)
       is distinct from (old.titulo, old.descricao, old.justificativa, old.tipo, old.urgencia, old.local_entrega, old.data_necessidade) then
      insert into rg.solicitacao_historico (solicitacao_id, autor_id, acao, status_de, status_para, observacao)
      values (new.id, rg.usuario_atual_id(), 'edicao', old.status::text, new.status::text, coalesce(v_obs, 'Conteúdo ajustado pelo setor'));
    end if;
    return null;
  end if;

  insert into rg.solicitacao_historico (solicitacao_id, autor_id, acao, status_de, status_para, observacao)
  values (new.id, rg.usuario_atual_id(), 'mudanca_status', old.status::text, new.status::text,
          coalesce(v_obs, case new.status
            when 'reprovada' then new.motivo_reprovacao
            when 'devolvida' then new.motivo_devolucao
            when 'cancelada' then new.motivo_cancelamento
            when 'aguardando_pedido' then new.justificativa_escolha
          end));

  -- Registro formal das decisões de aprovação
  if old.status in ('aguardando_gestor', 'aguardando_diretoria')
     and new.status in ('aprovada', 'aguardando_diretoria', 'reprovada', 'devolvida') then
    v_nivel := case old.status when 'aguardando_gestor' then 'gestor' else 'diretoria' end;
    v_dec := case new.status when 'reprovada' then 'reprovado' when 'devolvida' then 'devolvido' else 'aprovado' end;
    insert into rg.aprovacoes (solicitacao_id, nivel, decisao, usuario_id, parecer, valor)
    values (new.id, v_nivel, v_dec, rg.usuario_atual_id(),
            coalesce(v_obs, new.motivo_reprovacao, new.motivo_devolucao), rg.valor_estimado(new.id));
  end if;

  case new.status
    when 'aguardando_diretoria' then
      perform rg.notificar(new.solicitante_id, 'Aprovada pelo gestor', v_ref || ' segue para aprovação da Diretoria.', 'info', v_link);
      perform rg.notificar_papel('diretoria', 'Solicitação aguardando aprovação da Diretoria', v_ref, 'info', v_link);
    when 'aprovada' then
      perform rg.notificar(new.solicitante_id, 'Solicitação aprovada', v_ref || ' foi encaminhada ao setor de Compras.', 'sucesso', v_link);
      perform rg.notificar_papel('comprador', 'Nova solicitação aprovada para cotação', v_ref, 'info', v_link);
    when 'devolvida' then
      perform rg.notificar(new.solicitante_id, 'Solicitação devolvida para ajustes', v_ref || ': ' || new.motivo_devolucao, 'alerta', v_link);
    when 'reprovada' then
      perform rg.notificar(new.solicitante_id, 'Solicitação reprovada', v_ref || ': ' || new.motivo_reprovacao, 'erro', v_link);
    when 'aguardando_gestor' then
      perform rg.notificar_setor('gestor', new.setor_codigo, 'Solicitação reenviada após ajustes', v_ref, 'info', v_link);
    when 'em_cotacao' then
      if old.status = 'aprovada' then
        perform rg.notificar(new.solicitante_id, 'Cotação iniciada', v_ref || ' está em cotação com fornecedores.', 'info', v_link);
      else
        perform rg.notificar(new.comprador_id, 'Cotação reaberta', v_ref || ': defina novamente o fornecedor.', 'alerta', v_link);
      end if;
    when 'aguardando_pedido' then
      perform rg.notificar(new.solicitante_id, 'Fornecedor definido', v_ref || ' aguarda a emissão do pedido de compra.', 'info', v_link);
    when 'em_pedido' then
      perform rg.notificar(new.solicitante_id, 'Pedido de compra emitido', v_ref, 'info', v_link);
    when 'recebida_parcial' then
      perform rg.notificar(new.solicitante_id, 'Recebimento parcial', v_ref || ' teve parte dos itens entregue.', 'info', v_link);
    when 'concluida' then
      perform rg.notificar(new.solicitante_id, 'Solicitação concluída', v_ref || ': itens recebidos e conferidos.', 'sucesso', v_link);
      perform rg.notificar(new.comprador_id, 'Solicitação concluída', v_ref, 'sucesso', v_link);
    when 'cancelada' then
      perform rg.notificar(new.solicitante_id, 'Solicitação cancelada', v_ref || ': ' || new.motivo_cancelamento, 'alerta', v_link);
      perform rg.notificar(new.comprador_id, 'Solicitação cancelada', v_ref, 'alerta', v_link);
    else
      null;
  end case;

  -- Ao reabrir a cotação, nenhuma proposta permanece selecionada
  if new.status = 'em_cotacao' and old.status in ('aguardando_pedido', 'em_pedido') then
    update rg.cotacoes set selecionada = false where solicitacao_id = new.id and selecionada;
  end if;
  return null;
end $$;

create trigger solicitacoes_movimentar after insert or update on rg.solicitacoes
  for each row execute function rg.tg_solicitacao_movimentar();

-- Toda submissão e decisão exige assinatura eletrônica registrada na mesma transação.
create function rg.tg_solicitacao_exigir_assinatura() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare v_status rg.status_solicitacao;
begin
  select status into v_status from rg.solicitacoes where id = new.id;
  if tg_op = 'UPDATE' and v_status is not distinct from old.status then
    return null;
  end if;
  if v_status in ('aguardando_gestor', 'aguardando_diretoria')
     and not exists (select 1 from rg.solicitacao_itens where solicitacao_id = new.id) then
    raise exception 'Inclua ao menos um item na solicitação' using errcode = 'P0001';
  end if;
  if v_status in ('cancelada', 'em_cotacao') then
    return null;
  end if;
  if not exists (
      select 1 from rg.assinaturas a
       where a.solicitacao_id = new.id and a.status_solicitacao = v_status::text and a.txid = txid_current()) then
    raise exception 'A movimentação para % exige a assinatura eletrônica do responsável', v_status using errcode = 'P0001';
  end if;
  return null;
end $$;

create constraint trigger solicitacoes_exigir_assinatura
  after insert or update of status on rg.solicitacoes
  deferrable initially deferred
  for each row execute function rg.tg_solicitacao_exigir_assinatura();

-- ---------------------------------------------------------------------
-- Itens da solicitação: editáveis na abertura (mesma transação) ou quando devolvida
-- ---------------------------------------------------------------------
create function rg.tg_solicitacao_item_validar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_sid uuid := coalesce(new.solicitacao_id, old.solicitacao_id);
  v_s   rg.solicitacoes;
begin
  select * into v_s from rg.solicitacoes where id = v_sid;
  if tg_op = 'UPDATE' and new.solicitacao_id <> old.solicitacao_id then
    raise exception 'O item não pode mudar de solicitação' using errcode = 'P0001';
  end if;
  if not (rg.papel_atual() in ('solicitante', 'gestor') and rg.setor_atual() = v_s.setor_codigo
          and (v_s.status = 'devolvida' or (v_s.criado_em = now() and v_s.status in ('aguardando_gestor', 'aguardando_diretoria')))) then
    raise exception 'Os itens só podem ser alterados pelo setor na abertura ou quando a solicitação for devolvida'
      using errcode = 'P0001';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  if new.material_id is not null and not exists (select 1 from rg.materiais where id = new.material_id and ativo) then
    raise exception 'Material inexistente ou inativo' using errcode = 'P0001';
  end if;
  return new;
end $$;

create trigger solicitacao_itens_validar before insert or update or delete on rg.solicitacao_itens
  for each row execute function rg.tg_solicitacao_item_validar();

-- =====================================================================
-- COTAÇÕES (propostas preenchidas manualmente pelo comprador)
-- =====================================================================
create function rg.tg_cotacao_validar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_sid    uuid := coalesce(new.solicitacao_id, old.solicitacao_id);
  v_status rg.status_solicitacao;
begin
  select status into v_status from rg.solicitacoes where id = v_sid;
  -- Desmarcar a proposta vencedora ao reabrir a cotação é permitido ao fluxo
  if tg_op = 'UPDATE' and old.selecionada and not new.selecionada
     and (to_jsonb(new) - array['selecionada', 'atualizado_em']) = (to_jsonb(old) - array['selecionada', 'atualizado_em']) then
    return new;
  end if;
  if rg.papel_atual() is distinct from 'comprador' or v_status <> 'em_cotacao' then
    raise exception 'Propostas só podem ser registradas pelo comprador durante a cotação' using errcode = 'P0001';
  end if;
  if tg_op = 'DELETE' then
    if old.selecionada then
      raise exception 'A proposta vencedora não pode ser removida' using errcode = 'P0001';
    end if;
    return old;
  end if;
  if tg_op = 'UPDATE' and (new.solicitacao_id <> old.solicitacao_id or new.fornecedor_id <> old.fornecedor_id
                           or new.criado_por <> old.criado_por) then
    raise exception 'Fornecedor e solicitação da proposta não podem ser alterados' using errcode = 'P0001';
  end if;
  if not exists (select 1 from rg.fornecedores where id = new.fornecedor_id and ativo) then
    raise exception 'Fornecedor inativo ou inexistente' using errcode = 'P0001';
  end if;
  if new.anexo_id is not null and not exists (
      select 1 from rg.anexos where id = new.anexo_id and solicitacao_id = new.solicitacao_id and removido_em is null) then
    raise exception 'O documento da proposta não pertence a esta solicitação' using errcode = 'P0001';
  end if;
  new.valor_itens := coalesce((select sum(round(quantidade * valor_unitario, 2)) from rg.cotacao_itens
                                where cotacao_id = new.id), 0);
  if new.valor_itens > 0 and new.valor_itens + new.frete - new.desconto < 0 then
    raise exception 'O desconto não pode superar o valor da proposta' using errcode = 'P0001';
  end if;
  new.valor_total := greatest(new.valor_itens + new.frete - new.desconto, 0);
  return new;
end $$;

create trigger cotacoes_validar before insert or update or delete on rg.cotacoes
  for each row execute function rg.tg_cotacao_validar();

create function rg.tg_cotacao_item_validar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_cot rg.cotacoes;
  v_status rg.status_solicitacao;
begin
  select * into v_cot from rg.cotacoes where id = coalesce(new.cotacao_id, old.cotacao_id);
  select status into v_status from rg.solicitacoes where id = v_cot.solicitacao_id;
  if rg.papel_atual() is distinct from 'comprador' or v_status <> 'em_cotacao' then
    raise exception 'Itens de proposta só podem ser registrados pelo comprador durante a cotação' using errcode = 'P0001';
  end if;
  if tg_op = 'DELETE' then
    return old;
  end if;
  if not exists (select 1 from rg.solicitacao_itens where id = new.solicitacao_item_id and solicitacao_id = v_cot.solicitacao_id) then
    raise exception 'O item cotado não pertence a esta solicitação' using errcode = 'P0001';
  end if;
  return new;
end $$;

create trigger cotacao_itens_validar before insert or update or delete on rg.cotacao_itens
  for each row execute function rg.tg_cotacao_item_validar();

-- Recalcula os totais da proposta a cada item lançado
create function rg.tg_cotacao_item_totalizar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  update rg.cotacoes set atualizado_em = now() where id = coalesce(new.cotacao_id, old.cotacao_id);
  return null;
end $$;

create trigger cotacao_itens_totalizar after insert or update or delete on rg.cotacao_itens
  for each row execute function rg.tg_cotacao_item_totalizar();

-- =====================================================================
-- PEDIDOS DE COMPRA
-- =====================================================================
create function rg.tg_pedido_inserir() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_s   rg.solicitacoes;
  v_cot rg.cotacoes;
begin
  if rg.papel_atual() is distinct from 'comprador' then
    raise exception 'Somente o comprador emite pedidos de compra' using errcode = '42501';
  end if;
  select * into v_s from rg.solicitacoes where id = new.solicitacao_id;
  if v_s.status is distinct from 'aguardando_pedido' or v_s.cotacao_vencedora_id is null then
    raise exception 'Defina o fornecedor antes de emitir o pedido de compra' using errcode = 'P0001';
  end if;
  select * into v_cot from rg.cotacoes where id = v_s.cotacao_vencedora_id;
  -- Os valores do pedido vêm sempre da proposta vencedora
  new.cotacao_id := v_cot.id;
  new.fornecedor_id := v_cot.fornecedor_id;
  new.valor_itens := v_cot.valor_itens;
  new.frete := v_cot.frete;
  new.desconto := v_cot.desconto;
  new.valor_total := v_cot.valor_total;
  new.prazo_entrega_dias := v_cot.prazo_entrega_dias;
  new.condicoes_pagamento := coalesce(nullif(btrim(coalesce(new.condicoes_pagamento, '')), ''), v_cot.condicoes_pagamento);
  new.local_entrega := coalesce(nullif(btrim(coalesce(new.local_entrega, '')), ''), v_s.local_entrega);
  new.status := 'aguardando_financeiro';
  new.comprador_id := rg.usuario_atual_id();
  new.exige_diretoria := v_cot.valor_total >= coalesce(rg.config_num('alcada_diretoria'), 0)
                         and v_s.aprovado_diretoria_em is null;
  new.codigo := 'PC-' || to_char(now() at time zone 'America/Sao_Paulo', 'YYYY') || '-'
                || lpad(nextval('rg.pedido_codigo_seq')::text, 5, '0');
  new.aprovado_financeiro_por := null; new.aprovado_financeiro_em := null; new.parecer_financeiro := null;
  new.aprovado_diretoria_por := null; new.aprovado_diretoria_em := null; new.parecer_diretoria := null;
  new.enviado_por := null; new.enviado_em := null; new.data_prevista_entrega := null;
  new.motivo_reprovacao := null; new.motivo_cancelamento := null;
  new.encerrado_com_pendencia := false; new.justificativa_encerramento := null;
  new.atraso_notificado_em := null; new.concluido_em := null;
  new.versao := 1;
  new.criado_em := now();
  new.atualizado_em := now();
  return new;
end $$;

create trigger pedidos_inserir before insert on rg.pedidos
  for each row execute function rg.tg_pedido_inserir();

create function rg.tg_pedido_apos_inserir() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  insert into rg.pedido_itens (pedido_id, solicitacao_item_id, material_id, ordem, descricao, unidade, marca,
                               quantidade, valor_unitario)
  select new.id, si.id, si.material_id, si.ordem, si.descricao, si.unidade, ci.marca, ci.quantidade, ci.valor_unitario
    from rg.cotacao_itens ci
    join rg.solicitacao_itens si on si.id = ci.solicitacao_item_id
   where ci.cotacao_id = new.cotacao_id;

  update rg.solicitacoes set status = 'em_pedido' where id = new.solicitacao_id;

  insert into rg.solicitacao_historico (solicitacao_id, pedido_id, autor_id, acao, status_de, status_para, observacao)
  values (new.solicitacao_id, new.id, rg.usuario_atual_id(), 'pedido_emitido', null, new.status::text,
          'Pedido ' || new.codigo || ' emitido · ' || to_char(new.valor_total, 'FM"R$ "999G999G990D00'));
  perform rg.notificar_papel('financeiro', 'Pedido aguardando aprovação financeira',
    new.codigo || ' · ' || to_char(new.valor_total, 'FM"R$ "999G999G990D00'), 'info', '/pedidos/' || new.id);
  return null;
end $$;

create trigger pedidos_apos_inserir after insert on rg.pedidos
  for each row execute function rg.tg_pedido_apos_inserir();

create function rg.tg_pedido_validar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_papel rg.papel_usuario := rg.papel_atual();
  v_uid   uuid := rg.usuario_atual_id();
  v_ops   text[] := array['atraso_notificado_em', 'atualizado_em'];
  v_edit  text[] := array['observacoes', 'data_prevista_entrega', 'condicoes_pagamento', 'local_entrega'];
  v_pendente boolean;
  v_recebido boolean;
begin
  if (to_jsonb(new) - v_ops) = (to_jsonb(old) - v_ops) then
    return new;
  end if;
  if new.codigo <> old.codigo or new.solicitacao_id <> old.solicitacao_id or new.cotacao_id <> old.cotacao_id
     or new.fornecedor_id <> old.fornecedor_id or new.comprador_id <> old.comprador_id
     or (new.valor_itens, new.frete, new.desconto, new.valor_total, new.prazo_entrega_dias, new.exige_diretoria)
        is distinct from (old.valor_itens, old.frete, old.desconto, old.valor_total, old.prazo_entrega_dias, old.exige_diretoria)
     or new.criado_em <> old.criado_em then
    raise exception 'Valores e dados estruturais do pedido não podem ser alterados' using errcode = 'P0001';
  end if;
  if old.status in ('entregue', 'reprovado', 'cancelado') then
    raise exception 'O pedido % já foi encerrado', old.codigo using errcode = 'P0001';
  end if;
  if v_papel is null or v_papel = 'auditoria' then
    raise exception 'Operação não permitida para o seu perfil' using errcode = '42501';
  end if;

  -- Controle definido pela máquina de estados
  new.aprovado_financeiro_por := old.aprovado_financeiro_por; new.aprovado_financeiro_em := old.aprovado_financeiro_em;
  new.aprovado_diretoria_por := old.aprovado_diretoria_por;   new.aprovado_diretoria_em := old.aprovado_diretoria_em;
  new.enviado_por := old.enviado_por; new.enviado_em := old.enviado_em;
  new.concluido_em := old.concluido_em;
  new.encerrado_com_pendencia := old.encerrado_com_pendencia;

  if new.status is not distinct from old.status then
    if (to_jsonb(new) - (v_ops || v_edit || array['versao'])) <> (to_jsonb(old) - (v_ops || v_edit || array['versao'])) then
      raise exception 'Alteração não permitida no pedido' using errcode = 'P0001';
    end if;
    if v_papel <> 'comprador' then
      raise exception 'Somente o comprador atualiza os dados do pedido' using errcode = '42501';
    end if;
    if (new.condicoes_pagamento, new.local_entrega) is distinct from (old.condicoes_pagamento, old.local_entrega)
       and old.status not in ('aguardando_financeiro', 'aguardando_diretoria') then
      raise exception 'Condições e local de entrega só podem ser alterados antes da aprovação' using errcode = 'P0001';
    end if;
    if new.data_prevista_entrega is distinct from old.data_prevista_entrega
       and old.status not in ('enviado', 'entregue_parcial') then
      raise exception 'A previsão de entrega é definida no envio ao fornecedor' using errcode = 'P0001';
    end if;
    new.versao := old.versao + 1;
    return new;
  end if;

  if new.status <> 'reprovado' then new.motivo_reprovacao := old.motivo_reprovacao; end if;
  if new.status <> 'cancelado' then new.motivo_cancelamento := old.motivo_cancelamento; end if;
  if not (old.status = 'aguardando_financeiro') then new.parecer_financeiro := old.parecer_financeiro; end if;
  if not (old.status = 'aguardando_diretoria') then new.parecer_diretoria := old.parecer_diretoria; end if;

  case
    when old.status = 'aguardando_financeiro' and new.status in ('aprovado', 'aguardando_diretoria', 'reprovado') then
      if v_papel <> 'financeiro' then
        raise exception 'Somente o Financeiro aprova pedidos nesta etapa' using errcode = '42501';
      end if;
      if new.status <> 'reprovado' then
        new.aprovado_financeiro_por := v_uid;
        new.aprovado_financeiro_em := now();
        new.status := case when old.exige_diretoria then 'aguardando_diretoria' else 'aprovado' end;
      end if;

    when old.status = 'aguardando_diretoria' and new.status in ('aprovado', 'reprovado') then
      if v_papel <> 'diretoria' then
        raise exception 'Somente a Diretoria aprova pedidos acima da alçada' using errcode = '42501';
      end if;
      if new.status = 'aprovado' then
        new.aprovado_diretoria_por := v_uid;
        new.aprovado_diretoria_em := now();
      end if;

    when old.status = 'aprovado' and new.status = 'enviado' then
      if v_papel <> 'comprador' then
        raise exception 'Somente o comprador envia o pedido ao fornecedor' using errcode = '42501';
      end if;
      new.enviado_por := v_uid;
      new.enviado_em := now();
      new.data_prevista_entrega := coalesce(new.data_prevista_entrega, rg.hoje() + old.prazo_entrega_dias);

    when old.status in ('aguardando_financeiro', 'aguardando_diretoria', 'aprovado', 'enviado') and new.status = 'cancelado' then
      if v_papel not in ('comprador', 'admin') then
        raise exception 'Somente Compras ou a administração cancela pedidos' using errcode = '42501';
      end if;
      if exists (select 1 from rg.pedido_itens where pedido_id = old.id and quantidade_recebida > 0) then
        raise exception 'Pedido com itens já recebidos não pode ser cancelado' using errcode = 'P0001';
      end if;
      if char_length(btrim(coalesce(new.motivo_cancelamento, ''))) < 10 then
        raise exception 'Informe o motivo do cancelamento (mínimo 10 caracteres)' using errcode = 'P0001';
      end if;

    when old.status in ('enviado', 'entregue_parcial') and new.status in ('entregue_parcial', 'entregue') then
      select exists (select 1 from rg.pedido_itens where pedido_id = old.id and quantidade_recebida < quantidade),
             exists (select 1 from rg.pedido_itens where pedido_id = old.id and quantidade_recebida > 0)
        into v_pendente, v_recebido;
      if v_papel = 'recebimento' then
        if (new.status = 'entregue' and v_pendente) or (new.status = 'entregue_parcial' and (not v_pendente or not v_recebido)) then
          raise exception 'Situação incompatível com as quantidades recebidas' using errcode = 'P0001';
        end if;
      elsif v_papel = 'comprador' and old.status = 'entregue_parcial' and new.status = 'entregue' then
        if char_length(btrim(coalesce(new.justificativa_encerramento, ''))) < 10 then
          raise exception 'Justifique o encerramento com pendência (mínimo 10 caracteres)' using errcode = 'P0001';
        end if;
        new.encerrado_com_pendencia := v_pendente;
      else
        raise exception 'Somente o Recebimento registra entregas' using errcode = '42501';
      end if;
      if new.status = 'entregue' then
        new.concluido_em := now();
      end if;

    else
      raise exception 'Transição inválida do pedido: % → %', old.status, new.status using errcode = 'P0001';
  end case;

  if new.status = 'reprovado' and char_length(btrim(coalesce(new.motivo_reprovacao, ''))) < 10 then
    raise exception 'Informe o motivo da reprovação (mínimo 10 caracteres)' using errcode = 'P0001';
  end if;
  new.versao := old.versao + 1;
  return new;
end $$;

create trigger pedidos_validar before update on rg.pedidos
  for each row execute function rg.tg_pedido_validar();

create function rg.tg_pedido_movimentar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_obs  text := rg.observacao_atual();
  v_link text := '/pedidos/' || new.id;
  v_ref  text := new.codigo;
  v_s    rg.solicitacoes;
begin
  if new.status is not distinct from old.status then
    return null;
  end if;
  select * into v_s from rg.solicitacoes where id = new.solicitacao_id;
  v_ref := new.codigo || ' (' || v_s.codigo || ')';

  insert into rg.solicitacao_historico (solicitacao_id, pedido_id, autor_id, acao, status_de, status_para, observacao)
  values (new.solicitacao_id, new.id, rg.usuario_atual_id(), 'pedido_status', old.status::text, new.status::text,
          coalesce(v_obs, case new.status
            when 'reprovado' then new.motivo_reprovacao
            when 'cancelado' then new.motivo_cancelamento
            when 'entregue' then new.justificativa_encerramento
          end));

  if old.status in ('aguardando_financeiro', 'aguardando_diretoria') and new.status in ('aprovado', 'aguardando_diretoria', 'reprovado') then
    insert into rg.aprovacoes (solicitacao_id, pedido_id, nivel, decisao, usuario_id, parecer, valor)
    values (new.solicitacao_id, new.id,
            case old.status when 'aguardando_financeiro' then 'financeiro'::rg.nivel_aprovacao else 'diretoria' end,
            case new.status when 'reprovado' then 'reprovado'::rg.decisao_aprovacao else 'aprovado' end,
            rg.usuario_atual_id(),
            coalesce(v_obs, case when new.status = 'reprovado' then new.motivo_reprovacao
                                 when old.status = 'aguardando_financeiro' then new.parecer_financeiro
                                 else new.parecer_diretoria end),
            new.valor_total);
  end if;

  case new.status
    when 'aguardando_diretoria' then
      perform rg.notificar_papel('diretoria', 'Pedido aguardando aprovação da Diretoria', v_ref, 'info', v_link);
    when 'aprovado' then
      perform rg.notificar(new.comprador_id, 'Pedido aprovado', v_ref || ': envie ao fornecedor.', 'sucesso', v_link);
    when 'reprovado' then
      perform rg.notificar(new.comprador_id, 'Pedido reprovado', v_ref || ': ' || new.motivo_reprovacao, 'erro', v_link);
      update rg.solicitacoes set status = 'em_cotacao' where id = new.solicitacao_id and status = 'em_pedido';
    when 'cancelado' then
      update rg.solicitacoes set status = 'em_cotacao' where id = new.solicitacao_id and status = 'em_pedido';
    when 'enviado' then
      perform rg.notificar_papel('recebimento', 'Entrega prevista',
        v_ref || ' · previsão ' || to_char(new.data_prevista_entrega, 'DD/MM/YYYY'), 'info', v_link);
      update rg.materiais m set ultimo_preco = pi.valor_unitario, ultima_compra_em = now()
        from rg.pedido_itens pi where pi.pedido_id = new.id and pi.material_id = m.id;
    when 'entregue_parcial' then
      update rg.solicitacoes set status = 'recebida_parcial' where id = new.solicitacao_id and status = 'em_pedido';
    when 'entregue' then
      update rg.solicitacoes set status = 'concluida' where id = new.solicitacao_id and status in ('em_pedido', 'recebida_parcial');
      perform rg.notificar(new.comprador_id, 'Pedido entregue', v_ref || ' foi recebido e conferido.', 'sucesso', v_link);
    else
      null;
  end case;
  return null;
end $$;

create trigger pedidos_movimentar after update on rg.pedidos
  for each row execute function rg.tg_pedido_movimentar();

create function rg.tg_pedido_exigir_assinatura() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare v_status rg.status_pedido;
begin
  select status into v_status from rg.pedidos where id = new.id;
  if tg_op = 'UPDATE' and v_status is not distinct from old.status then
    return null;
  end if;
  if v_status = 'cancelado' then
    return null;
  end if;
  if not exists (select 1 from rg.pedido_itens where pedido_id = new.id) then
    raise exception 'O pedido de compra precisa conter itens' using errcode = 'P0001';
  end if;
  if not exists (
      select 1 from rg.assinaturas a
       where a.pedido_id = new.id and a.status_pedido = v_status::text and a.txid = txid_current()) then
    raise exception 'A movimentação do pedido para % exige assinatura eletrônica', v_status using errcode = 'P0001';
  end if;
  return null;
end $$;

create constraint trigger pedidos_exigir_assinatura
  after insert or update of status on rg.pedidos
  deferrable initially deferred
  for each row execute function rg.tg_pedido_exigir_assinatura();

-- =====================================================================
-- RECEBIMENTO E CONFERÊNCIA
-- =====================================================================
create function rg.tg_recebimento_inserir() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare v_p rg.pedidos;
begin
  if rg.papel_atual() is distinct from 'recebimento' then
    raise exception 'Somente o setor de Recebimento registra entregas' using errcode = '42501';
  end if;
  select * into v_p from rg.pedidos where id = new.pedido_id;
  if v_p.status is null or v_p.status not in ('enviado', 'entregue_parcial') then
    raise exception 'O pedido precisa estar enviado ao fornecedor para registrar a entrega' using errcode = 'P0001';
  end if;
  new.solicitacao_id := v_p.solicitacao_id;
  new.recebido_por := rg.usuario_atual_id();
  new.recebido_em := now();
  new.criado_em := now();
  new.processado := false;
  new.situacao := 'conforme';
  new.codigo := 'RC-' || to_char(now() at time zone 'America/Sao_Paulo', 'YYYY') || '-'
                || lpad(nextval('rg.recebimento_codigo_seq')::text, 5, '0');
  return new;
end $$;

create trigger recebimentos_inserir before insert on rg.recebimentos
  for each row execute function rg.tg_recebimento_inserir();

create function rg.tg_recebimento_item_inserir() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_r  rg.recebimentos;
  v_pi rg.pedido_itens;
begin
  select * into v_r from rg.recebimentos where id = new.recebimento_id;
  if v_r.processado or v_r.recebido_por is distinct from rg.usuario_atual_id() then
    raise exception 'Recebimento já finalizado ou registrado por outro usuário' using errcode = 'P0001';
  end if;
  select * into v_pi from rg.pedido_itens where id = new.pedido_item_id for update;
  if v_pi.pedido_id is distinct from v_r.pedido_id then
    raise exception 'O item não pertence ao pedido recebido' using errcode = 'P0001';
  end if;
  if v_pi.quantidade_recebida + new.quantidade_aceita > v_pi.quantidade then
    raise exception 'Quantidade aceita de "%" excede o saldo pendente do pedido', v_pi.descricao using errcode = 'P0001';
  end if;
  update rg.pedido_itens set quantidade_recebida = quantidade_recebida + new.quantidade_aceita where id = v_pi.id;
  return new;
end $$;

create trigger recebimento_itens_inserir before insert on rg.recebimento_itens
  for each row execute function rg.tg_recebimento_item_inserir();

-- Consolida o recebimento: situação da conferência, status do pedido e da solicitação.
create function rg.processar_recebimento(p_recebimento uuid) returns rg.situacao_recebimento
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_r        rg.recebimentos;
  v_p        rg.pedidos;
  v_sit      rg.situacao_recebimento;
  v_total    numeric;
  v_aceito   numeric;
  v_diverg   boolean;
  v_pendente boolean;
  v_recebido boolean;
  v_novo     rg.status_pedido;
begin
  select * into v_r from rg.recebimentos where id = p_recebimento for update;
  if v_r.id is null or v_r.processado or v_r.recebido_por is distinct from rg.usuario_atual_id() then
    raise exception 'Recebimento inexistente, já processado ou de outro usuário' using errcode = 'P0001';
  end if;
  select coalesce(sum(quantidade_recebida), 0), coalesce(sum(quantidade_aceita), 0),
         coalesce(bool_or(quantidade_aceita < quantidade_recebida), false)
    into v_total, v_aceito, v_diverg
    from rg.recebimento_itens where recebimento_id = p_recebimento;
  if v_total = 0 then
    raise exception 'Informe a quantidade recebida de ao menos um item' using errcode = 'P0001';
  end if;
  v_sit := case when v_aceito = 0 then 'recusado' when v_diverg then 'divergente' else 'conforme' end;
  update rg.recebimentos set processado = true, situacao = v_sit where id = p_recebimento;

  select * into v_p from rg.pedidos where id = v_r.pedido_id for update;
  select exists (select 1 from rg.pedido_itens where pedido_id = v_p.id and quantidade_recebida < quantidade),
         exists (select 1 from rg.pedido_itens where pedido_id = v_p.id and quantidade_recebida > 0)
    into v_pendente, v_recebido;
  v_novo := case when not v_pendente then 'entregue' when v_recebido then 'entregue_parcial' else v_p.status end;

  insert into rg.solicitacao_historico (solicitacao_id, pedido_id, autor_id, acao, status_de, status_para, observacao)
  values (v_r.solicitacao_id, v_p.id, rg.usuario_atual_id(), 'recebimento', null, v_sit::text,
          v_r.codigo || ' · NF ' || v_r.nota_fiscal || coalesce(' · ' || v_r.observacoes, ''));

  if v_novo is distinct from v_p.status then
    update rg.pedidos set status = v_novo where id = v_p.id;
  end if;
  if v_sit <> 'conforme' then
    perform rg.notificar(v_p.comprador_id, 'Recebimento com divergência',
      v_p.codigo || ' · NF ' || v_r.nota_fiscal || ': ' || coalesce(v_r.observacoes, 'verifique a conferência'),
      'alerta', '/pedidos/' || v_p.id);
  end if;
  return v_sit;
end $$;

create function rg.tg_recebimento_exigir_processamento() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  if not exists (select 1 from rg.recebimentos where id = new.id and processado) then
    raise exception 'Recebimento não finalizado' using errcode = 'P0001';
  end if;
  if not exists (select 1 from rg.assinaturas where recebimento_id = new.id and txid = txid_current()) then
    raise exception 'O recebimento exige assinatura eletrônica do conferente' using errcode = 'P0001';
  end if;
  return null;
end $$;

create constraint trigger recebimentos_exigir_processamento
  after insert on rg.recebimentos
  deferrable initially deferred
  for each row execute function rg.tg_recebimento_exigir_processamento();

-- =====================================================================
-- ANEXOS (anexar ou fotografar; o preenchimento dos dados é sempre manual)
-- =====================================================================
create function rg.tg_anexo_validar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_s     rg.solicitacoes;
  v_papel rg.papel_usuario := rg.papel_atual();
  v_ok    boolean;
begin
  select * into v_s from rg.solicitacoes where id = new.solicitacao_id;
  if tg_op = 'UPDATE' then
    if (new.sha256, new.caminho, new.solicitacao_id, new.origem, new.enviado_por, new.nome_original, new.mime, new.tamanho,
        new.recebimento_id, new.criado_em)
       is distinct from (old.sha256, old.caminho, old.solicitacao_id, old.origem, old.enviado_por, old.nome_original, old.mime,
                         old.tamanho, old.recebimento_id, old.criado_em) then
      raise exception 'Metadados de integridade do anexo não podem ser alterados' using errcode = 'P0001';
    end if;
    if old.removido_em is not null then
      raise exception 'Anexo já removido' using errcode = 'P0001';
    end if;
    if exists (select 1 from rg.cotacoes where anexo_id = old.id) then
      raise exception 'O documento está vinculado a uma proposta' using errcode = 'P0001';
    end if;
    if old.origem = 'recebimento' then
      raise exception 'Documentos de recebimento não podem ser removidos' using errcode = 'P0001';
    end if;
    new.removido_por := rg.usuario_atual_id();
  else
    new.enviado_por := rg.usuario_atual_id();
    new.rodada := v_s.rodada;
    new.criado_em := now();
    new.removido_em := null;
    new.removido_por := null;
  end if;

  v_ok := case new.origem
    when 'solicitante' then v_papel in ('solicitante', 'gestor') and rg.setor_atual() = v_s.setor_codigo
                            and v_s.status in ('aguardando_gestor', 'aguardando_diretoria', 'devolvida')
    when 'comprador' then v_papel = 'comprador'
                          and v_s.status in ('aprovada', 'em_cotacao', 'aguardando_pedido', 'em_pedido', 'recebida_parcial')
    when 'recebimento' then v_papel = 'recebimento' and v_s.status in ('em_pedido', 'recebida_parcial')
                            and (new.recebimento_id is null or exists (
                                  select 1 from rg.recebimentos r where r.id = new.recebimento_id and r.solicitacao_id = v_s.id))
  end;
  if not coalesce(v_ok, false) then
    raise exception 'Seu perfil não pode anexar ou remover documentos nesta etapa' using errcode = 'P0001';
  end if;

  if tg_op = 'INSERT' and new.origem = 'solicitante' then
    perform 1 from rg.solicitacoes where id = new.solicitacao_id for update;
    if (select count(*) from rg.anexos where solicitacao_id = new.solicitacao_id and origem = 'solicitante'
         and removido_em is null) >= 5 then
      raise exception 'Limite de 5 documentos do solicitante por solicitação atingido' using errcode = 'P0001';
    end if;
  end if;
  return new;
end $$;

create trigger anexos_validar before insert or update on rg.anexos
  for each row execute function rg.tg_anexo_validar();

-- =====================================================================
-- ALERTAS PERIÓDICOS (SLA e atraso de entrega), executados pela API
-- =====================================================================
create function rg.notificar_responsavel(r rg.solicitacoes, p_titulo text, p_tipo rg.tipo_notificacao)
returns void
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_link text := '/solicitacoes/' || r.id;
  v_ref  text := r.codigo || ' — ' || r.titulo;
begin
  case r.status
    when 'aguardando_gestor' then perform rg.notificar_setor('gestor', r.setor_codigo, p_titulo, v_ref, p_tipo, v_link);
    when 'aguardando_diretoria' then perform rg.notificar_papel('diretoria', p_titulo, v_ref, p_tipo, v_link);
    when 'devolvida' then perform rg.notificar(r.solicitante_id, p_titulo, v_ref, p_tipo, v_link);
    when 'aprovada' then perform rg.notificar_papel('comprador', p_titulo, v_ref, p_tipo, v_link);
    else
      if r.comprador_id is not null then
        perform rg.notificar(r.comprador_id, p_titulo, v_ref, p_tipo, v_link);
      else
        perform rg.notificar_papel('comprador', p_titulo, v_ref, p_tipo, v_link);
      end if;
  end case;
end $$;

create function rg.processar_alertas() returns int
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  r     rg.solicitacoes;
  rp    rg.pedidos;
  v_qtd int := 0;
begin
  if not rg.eh_sistema() then
    raise exception 'Rotina exclusiva do agendador do sistema' using errcode = '42501';
  end if;
  for r in
    select * from rg.solicitacoes
     where not rg.status_terminal(status) and sla_concluido_em is null
       and sla_estouro_notificado_em is null and now() > sla_prazo_limite
     for update skip locked
  loop
    perform rg.notificar_responsavel(r, 'Prazo de atendimento estourado', 'erro');
    update rg.solicitacoes set sla_estouro_notificado_em = now(),
           sla_alerta_notificado_em = coalesce(sla_alerta_notificado_em, now())
     where id = r.id;
    v_qtd := v_qtd + 1;
  end loop;

  for r in
    select * from rg.solicitacoes
     where not rg.status_terminal(status) and sla_concluido_em is null
       and sla_alerta_notificado_em is null and now() <= sla_prazo_limite
       and sla_prazo_limite - now() < interval '24 hours'
     for update skip locked
  loop
    perform rg.notificar_responsavel(r, 'Prazo de atendimento vence em menos de 24 h', 'alerta');
    update rg.solicitacoes set sla_alerta_notificado_em = now() where id = r.id;
    v_qtd := v_qtd + 1;
  end loop;

  for rp in
    select * from rg.pedidos
     where status in ('enviado', 'entregue_parcial') and data_prevista_entrega < rg.hoje()
       and atraso_notificado_em is null
     for update skip locked
  loop
    perform rg.notificar(rp.comprador_id, 'Entrega em atraso', rp.codigo || ' · previsão ' ||
      to_char(rp.data_prevista_entrega, 'DD/MM/YYYY'), 'erro', '/pedidos/' || rp.id);
    perform rg.notificar_papel('recebimento', 'Entrega em atraso', rp.codigo, 'alerta', '/pedidos/' || rp.id);
    update rg.pedidos set atraso_notificado_em = now() where id = rp.id;
    v_qtd := v_qtd + 1;
  end loop;
  return v_qtd;
end $$;

-- =====================================================================
-- VIEWS DE LEITURA
-- =====================================================================

-- Dados não sensíveis de usuários para exibição de nomes (executa como dono).
create view rg.v_usuarios_publico as
  select id, nome, papel, setor_codigo, status, cargo from rg.usuarios;

create view rg.v_solicitacoes with (security_invoker = true) as
  select s.*,
         rg.valor_estimado(s.id) as valor_estimado,
         rg.sla_situacao(s.status, s.sla_prazo_limite, s.sla_concluido_em) as sla_situacao,
         round((extract(epoch from (s.sla_prazo_limite - coalesce(s.sla_concluido_em, now()))) / 3600.0)::numeric, 1) as sla_horas_restantes,
         st.nome as setor_nome,
         st.cor  as setor_cor,
         us.nome as solicitante_nome,
         uc.nome as comprador_nome,
         (select count(*) from rg.solicitacao_itens i where i.solicitacao_id = s.id) as itens_qtd,
         (select count(*) from rg.cotacoes c where c.solicitacao_id = s.id) as cotacoes_qtd,
         f.razao_social as fornecedor_nome,
         f.nome_fantasia as fornecedor_fantasia,
         p.id as pedido_id,
         p.codigo as pedido_codigo,
         p.status as pedido_status,
         p.data_prevista_entrega as pedido_previsao
    from rg.solicitacoes s
    join rg.setores st on st.codigo = s.setor_codigo
    left join rg.v_usuarios_publico us on us.id = s.solicitante_id
    left join rg.v_usuarios_publico uc on uc.id = s.comprador_id
    left join rg.cotacoes cv on cv.id = s.cotacao_vencedora_id
    left join rg.fornecedores f on f.id = cv.fornecedor_id
    left join lateral (
      select p1.id, p1.codigo, p1.status, p1.data_prevista_entrega from rg.pedidos p1
       where p1.solicitacao_id = s.id order by (p1.status in ('reprovado', 'cancelado')), p1.criado_em desc limit 1
    ) p on true;

create view rg.v_pedidos with (security_invoker = true) as
  select p.*,
         s.codigo as solicitacao_codigo,
         s.titulo as solicitacao_titulo,
         s.setor_codigo,
         s.urgencia,
         st.nome as setor_nome,
         st.cor as setor_cor,
         f.razao_social as fornecedor_nome,
         f.nome_fantasia as fornecedor_fantasia,
         f.cnpj as fornecedor_cnpj,
         uc.nome as comprador_nome,
         us.nome as solicitante_nome,
         (select count(*) from rg.pedido_itens i where i.pedido_id = p.id) as itens_qtd,
         (select coalesce(round(100 * sum(least(i.quantidade_recebida, i.quantidade)) / nullif(sum(i.quantidade), 0)), 0)
            from rg.pedido_itens i where i.pedido_id = p.id) as percentual_recebido,
         (p.status in ('enviado', 'entregue_parcial') and p.data_prevista_entrega < rg.hoje()) as atrasado,
         case when p.status in ('enviado', 'entregue_parcial') and p.data_prevista_entrega < rg.hoje()
              then rg.hoje() - p.data_prevista_entrega else 0 end as dias_atraso
    from rg.pedidos p
    join rg.solicitacoes s on s.id = p.solicitacao_id
    join rg.setores st on st.codigo = s.setor_codigo
    join rg.fornecedores f on f.id = p.fornecedor_id
    left join rg.v_usuarios_publico uc on uc.id = p.comprador_id
    left join rg.v_usuarios_publico us on us.id = s.solicitante_id;

create view rg.v_recebimentos with (security_invoker = true) as
  select r.*,
         p.codigo as pedido_codigo,
         p.status as pedido_status,
         s.codigo as solicitacao_codigo,
         s.titulo as solicitacao_titulo,
         st.nome as setor_nome,
         st.cor as setor_cor,
         f.razao_social as fornecedor_nome,
         f.nome_fantasia as fornecedor_fantasia,
         u.nome as recebido_por_nome
    from rg.recebimentos r
    join rg.pedidos p on p.id = r.pedido_id
    join rg.solicitacoes s on s.id = r.solicitacao_id
    join rg.setores st on st.codigo = s.setor_codigo
    join rg.fornecedores f on f.id = p.fornecedor_id
    left join rg.v_usuarios_publico u on u.id = r.recebido_por;
