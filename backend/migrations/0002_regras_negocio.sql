-- =====================================================================
-- RG Hospital — 0002: contexto de segurança, regras de negócio, triggers
-- =====================================================================

-- ---------------------------------------------------------------------
-- Contexto da requisição (definido pela API a cada transação via set_config)
--   app.user_id   uuid do usuário autenticado
--   app.ip        IP de origem
--   app.contexto  'sistema' para rotinas internas (login, jobs, OCR)
--   app.observacao texto livre registrado no histórico do workflow
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

create function rg.sla_situacao(p_status rg.status_solicitacao, p_prazo timestamptz, p_concluido timestamptz)
returns text
language sql stable
as $$
  select case
    when rg.status_terminal(p_status) then
      case when p_concluido <= p_prazo then 'cumprido' else 'cumprido_com_atraso' end
    when now() > p_prazo then 'estourado'
    when p_prazo - now() < interval '24 hours' then 'alerta'
    else 'dentro_prazo'
  end
$$;

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

create trigger setores_atualizado before update on rg.setores for each row execute function rg.tg_atualizado_em();
create trigger usuarios_atualizado before update on rg.usuarios for each row execute function rg.tg_atualizado_em();
create trigger fornecedores_atualizado before update on rg.fornecedores for each row execute function rg.tg_atualizado_em();
create trigger solicitacoes_atualizado before update on rg.solicitacoes for each row execute function rg.tg_atualizado_em();
create trigger servicos_atualizado before update on rg.servicos_programados for each row execute function rg.tg_atualizado_em();
create trigger cotacoes_atualizado before update on rg.cotacoes for each row execute function rg.tg_atualizado_em();

-- Auditoria genérica: registra antes/depois de cada alteração.
create function audit.tg_registrar() returns trigger
language plpgsql security definer
set search_path = audit, rg, pg_temp
as $$
declare
  v_excluir text[] := array['senha_hash', 'telefone_cript', 'ocr_texto', 'token_hash', 'csrf_token'];
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
          coalesce(v_depois ->> 'id', v_antes ->> 'id'),
          tg_op, v_campos, v_antes, v_depois);
  return null;
end $$;

create trigger audit_setores      after insert or update or delete on rg.setores              for each row execute function audit.tg_registrar();
create trigger audit_usuarios     after insert or update or delete on rg.usuarios             for each row execute function audit.tg_registrar();
create trigger audit_fornecedores after insert or update or delete on rg.fornecedores         for each row execute function audit.tg_registrar();
create trigger audit_solicitacoes after insert or update or delete on rg.solicitacoes         for each row execute function audit.tg_registrar();
create trigger audit_servicos     after insert or update or delete on rg.servicos_programados for each row execute function audit.tg_registrar();
create trigger audit_anexos       after insert or update or delete on rg.anexos               for each row execute function audit.tg_registrar();
create trigger audit_cotacoes     after insert or update or delete on rg.cotacoes             for each row execute function audit.tg_registrar();
create trigger audit_assinaturas  after insert on rg.assinaturas                               for each row execute function audit.tg_registrar();

-- Eventos de aplicação (login, download, exportações etc.)
create function audit.registrar_evento(p_operacao text, p_tabela text, p_registro text, p_detalhes jsonb default null)
returns void
language sql security definer
set search_path = audit, rg, pg_temp
as $$
  insert into audit.eventos (usuario_id, ip, tabela, registro_id, operacao, dados_depois)
  values (rg.usuario_atual_id(), nullif(current_setting('app.ip', true), ''), p_tabela, p_registro, p_operacao, p_detalhes);
$$;

-- Registros de auditoria e assinaturas são imutáveis.
create function rg.tg_imutavel() returns trigger
language plpgsql
as $$
begin
  raise exception 'Registro imutável: % não permite %', tg_table_name, tg_op using errcode = 'P0001';
end $$;

create trigger eventos_imutavel before update or delete on audit.eventos for each row execute function rg.tg_imutavel();
create trigger assinaturas_imutavel before update or delete on rg.assinaturas for each row execute function rg.tg_imutavel();
create trigger historico_imutavel before update or delete on rg.solicitacao_historico for each row execute function rg.tg_imutavel();

-- Emissão de eventos em tempo real (LISTEN rg_eventos na API → WebSocket).
create function rg.tg_emitir_evento() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_row    jsonb := case when tg_op = 'DELETE' then to_jsonb(old) else to_jsonb(new) end;
  v_setor  text;
  v_status text;
  v_payload jsonb;
begin
  if tg_table_name = 'solicitacoes' then
    v_setor := v_row ->> 'setor_codigo';
    v_status := v_row ->> 'status';
  elsif tg_table_name in ('cotacoes', 'anexos') and v_row ->> 'solicitacao_id' is not null then
    select setor_codigo, status::text into v_setor, v_status
      from rg.solicitacoes where id = (v_row ->> 'solicitacao_id')::uuid;
  elsif tg_table_name = 'anexos' then
    select setor_codigo into v_setor from rg.servicos_programados where id = (v_row ->> 'servico_id')::uuid;
  elsif tg_table_name = 'servicos_programados' then
    v_setor := v_row ->> 'setor_codigo';
  end if;

  v_payload := jsonb_build_object(
    'tabela', tg_table_name,
    'op', lower(tg_op),
    'id', v_row ->> 'id',
    'solicitacao_id', v_row ->> 'solicitacao_id',
    'servico_id', v_row ->> 'servico_id',
    'setor', v_setor,
    'status', v_status,
    'destinatario', v_row ->> 'destinatario_id',
    'usuario', case when tg_table_name = 'usuarios' then v_row ->> 'id' end
  );
  perform pg_notify('rg_eventos', v_payload::text);
  return null;
end $$;

create trigger evt_solicitacoes after insert or update on rg.solicitacoes         for each row execute function rg.tg_emitir_evento();
create trigger evt_cotacoes     after insert or update or delete on rg.cotacoes   for each row execute function rg.tg_emitir_evento();
create trigger evt_anexos       after insert or update on rg.anexos               for each row execute function rg.tg_emitir_evento();
create trigger evt_servicos     after insert or update on rg.servicos_programados for each row execute function rg.tg_emitir_evento();
create trigger evt_notificacoes after insert on rg.notificacoes                   for each row execute function rg.tg_emitir_evento();
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
      raise exception 'Administradores não podem alterar o próprio papel ou situação' using errcode = 'P0001';
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
      new.nome || ' (' || new.email || ') solicitou acesso como ' || new.papel || '.',
      'alerta', '/usuarios?status=pendente');
  elsif tg_op = 'UPDATE' and new.status is distinct from old.status then
    if new.status = 'aprovado' and old.status = 'pendente' then
      perform rg.notificar(new.id, 'Acesso aprovado', 'Seu cadastro foi aprovado. Bem-vindo(a) ao RG Hospital.', 'sucesso', '/');
    end if;
  end if;
  return null;
end $$;

create trigger usuarios_eventos after insert or update of status on rg.usuarios
  for each row execute function rg.tg_usuario_eventos();

-- Mantém apenas as 5 últimas senhas no histórico.
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
-- Solicitações: código, SLA e máquina de estados
-- ---------------------------------------------------------------------
create function rg.tg_solicitacao_inserir() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare v_setor rg.setores;
begin
  select * into v_setor from rg.setores where codigo = new.setor_codigo;
  if not v_setor.operacional or not v_setor.ativo then
    raise exception 'Setor % não pode abrir solicitações', new.setor_codigo using errcode = 'P0001';
  end if;
  new.status := 'aguardando_adm';
  new.criado_em := now();
  new.atualizado_em := now();
  new.codigo := 'SOL-' || to_char(new.criado_em at time zone 'America/Sao_Paulo', 'YYYY') || '-'
                || lpad(nextval('rg.solicitacao_codigo_seq')::text, 6, '0');
  new.sla_prazo_limite := new.criado_em + rg.sla_intervalo(new.urgencia);
  new.rodada_cotacao := 1;
  new.versao := 1;
  new.valor_final_aprovado := null;
  new.cotacao_vencedora_id := null;
  new.comprador_id := null;
  new.justificativa_adm := null;
  new.justificativa_urgencia := null;
  new.motivo_nova_cotacao := null;
  new.justificativa_compras := null;
  new.motivo_cancelamento := null;
  new.sla_concluido_em := null;
  return new;
end $$;

create trigger solicitacoes_inserir before insert on rg.solicitacoes
  for each row execute function rg.tg_solicitacao_inserir();

create function rg.tg_solicitacao_validar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_papel     rg.papel_usuario := rg.papel_atual();
  v_uid       uuid := rg.usuario_atual_id();
  v_setor     text := rg.setor_atual();
  v_conteudo  boolean;
  v_adm       boolean;
  v_compras   boolean;
  v_cot       rg.cotacoes;
begin
  -- Alterações exclusivamente operacionais (marcadores de alerta de SLA)
  if (to_jsonb(new) - array['sla_alerta_notificado_em', 'sla_estouro_notificado_em', 'atualizado_em'])
     = (to_jsonb(old) - array['sla_alerta_notificado_em', 'sla_estouro_notificado_em', 'atualizado_em']) then
    return new;
  end if;

  if new.id <> old.id or new.codigo <> old.codigo or new.gestor_id <> old.gestor_id
     or new.setor_codigo <> old.setor_codigo or new.criado_em <> old.criado_em
     or new.sla_prazo_limite is distinct from old.sla_prazo_limite and new.urgencia = old.urgencia then
    raise exception 'Campos estruturais da solicitação não podem ser alterados' using errcode = 'P0001';
  end if;

  if rg.status_terminal(old.status) then
    raise exception 'Solicitação % já foi encerrada (%)', old.codigo, old.status using errcode = 'P0001';
  end if;

  if v_papel is null then
    raise exception 'Usuário sem permissão para alterar solicitações' using errcode = '42501';
  end if;

  -- Conteúdo da solicitação: somente gestor do setor, quando devolvida para nova cotação
  v_conteudo := (new.titulo, new.descricao, new.justificativa, new.tipo, new.valor_estimado)
                is distinct from (old.titulo, old.descricao, old.justificativa, old.tipo, old.valor_estimado);
  if v_conteudo and not (v_papel = 'gestor' and v_setor = old.setor_codigo
                         and old.status = 'necessita_nova_cotacao') then
    raise exception 'O conteúdo só pode ser editado pelo gestor do setor quando a solicitação for devolvida para nova cotação'
      using errcode = 'P0001';
  end if;

  -- Urgência: exclusiva da Administração, com justificativa
  if new.urgencia is distinct from old.urgencia then
    if v_papel <> 'admin' or old.status not in ('aguardando_adm', 'necessita_nova_cotacao') then
      raise exception 'Somente a Administração pode alterar a urgência antes da liberação para Compras'
        using errcode = 'P0001';
    end if;
    if new.justificativa_urgencia is not distinct from old.justificativa_urgencia
       or char_length(btrim(coalesce(new.justificativa_urgencia, ''))) < 10 then
      raise exception 'Informe a justificativa (mínimo 10 caracteres) para alterar a urgência' using errcode = 'P0001';
    end if;
    new.sla_prazo_limite := old.criado_em + rg.sla_intervalo(new.urgencia);
    new.sla_alerta_notificado_em := null;
    new.sla_estouro_notificado_em := null;
  elsif new.justificativa_urgencia is distinct from old.justificativa_urgencia then
    raise exception 'Justificativa de urgência só pode ser registrada junto com a alteração' using errcode = 'P0001';
  end if;

  -- Campos da Administração
  v_adm := (new.justificativa_adm, new.motivo_nova_cotacao)
           is distinct from (old.justificativa_adm, old.motivo_nova_cotacao);
  if v_adm and not (v_papel = 'admin' and old.status = 'aguardando_adm') then
    raise exception 'Parecer administrativo só pode ser registrado pela Administração durante a análise' using errcode = 'P0001';
  end if;

  -- Campos de Compras (após liberação do ADM, somente Compras altera)
  v_compras := (new.valor_final_aprovado, new.cotacao_vencedora_id, new.justificativa_compras, new.comprador_id)
               is distinct from (old.valor_final_aprovado, old.cotacao_vencedora_id, old.justificativa_compras, old.comprador_id);
  if v_compras and not (v_papel = 'compras' and old.status in ('aprovado_adm', 'em_cotacao')) then
    raise exception 'Somente o setor de Compras pode registrar dados de cotação e homologação' using errcode = 'P0001';
  end if;
  if old.status in ('aprovado_adm', 'em_cotacao') and v_papel <> 'compras' then
    raise exception 'Após a liberação da Administração, somente Compras pode alterar a solicitação' using errcode = 'P0001';
  end if;

  if new.motivo_cancelamento is distinct from old.motivo_cancelamento and new.status <> 'cancelado' then
    raise exception 'Motivo de cancelamento só pode ser registrado no cancelamento' using errcode = 'P0001';
  end if;

  -- Transições de status
  if new.status is distinct from old.status then
    case
      when old.status = 'aguardando_adm' and new.status in ('aprovado_adm', 'rejeitado_adm', 'necessita_nova_cotacao') then
        if v_papel <> 'admin' then
          raise exception 'Somente a Administração decide sobre solicitações em análise' using errcode = '42501';
        end if;
        if new.status = 'rejeitado_adm' and char_length(btrim(coalesce(new.justificativa_adm, ''))) < 10 then
          raise exception 'Justificativa administrativa obrigatória (mínimo 10 caracteres)' using errcode = 'P0001';
        end if;
        if new.status = 'necessita_nova_cotacao' and char_length(btrim(coalesce(new.motivo_nova_cotacao, ''))) < 10 then
          raise exception 'Informe ao gestor o motivo da nova cotação (mínimo 10 caracteres)' using errcode = 'P0001';
        end if;
        new.decidido_adm_em := now();

      when old.status in ('aguardando_adm', 'necessita_nova_cotacao') and new.status = 'cancelado' then
        if not (v_papel = 'gestor' and v_setor = old.setor_codigo) then
          raise exception 'Somente o gestor do setor pode cancelar a solicitação' using errcode = '42501';
        end if;
        if char_length(btrim(coalesce(new.motivo_cancelamento, ''))) < 10 then
          raise exception 'Informe o motivo do cancelamento (mínimo 10 caracteres)' using errcode = 'P0001';
        end if;

      when old.status = 'necessita_nova_cotacao' and new.status = 'aguardando_adm' then
        if not (v_papel = 'gestor' and v_setor = old.setor_codigo) then
          raise exception 'Somente o gestor do setor pode reenviar a solicitação' using errcode = '42501';
        end if;
        new.rodada_cotacao := old.rodada_cotacao + 1;
        new.decidido_adm_em := null;

      when old.status = 'aprovado_adm' and new.status = 'em_cotacao' then
        if v_papel <> 'compras' then
          raise exception 'Somente Compras pode iniciar a cotação' using errcode = '42501';
        end if;
        new.comprador_id := v_uid;
        new.cotacao_iniciada_em := now();

      when old.status = 'em_cotacao' and new.status in ('aprovado', 'rejeitado_compras') then
        if v_papel <> 'compras' then
          raise exception 'Somente Compras pode homologar a solicitação' using errcode = '42501';
        end if;
        if new.status = 'aprovado' then
          select * into v_cot from rg.cotacoes where id = new.cotacao_vencedora_id;
          if v_cot.id is null or v_cot.solicitacao_id <> new.id or not v_cot.selecionada then
            raise exception 'Selecione a cotação vencedora antes da homologação' using errcode = 'P0001';
          end if;
          if new.valor_final_aprovado is null or new.valor_final_aprovado <= 0 then
            raise exception 'Informe o valor final homologado' using errcode = 'P0001';
          end if;
        elsif char_length(btrim(coalesce(new.justificativa_compras, ''))) < 10 then
          raise exception 'Justificativa de Compras obrigatória (mínimo 10 caracteres)' using errcode = 'P0001';
        end if;

      else
        raise exception 'Transição de status inválida: % → %', old.status, new.status using errcode = 'P0001';
    end case;

    if rg.status_terminal(new.status) then
      new.sla_concluido_em := now();
      new.finalizado_em := now();
    end if;
  end if;

  new.versao := old.versao + 1;
  return new;
end $$;

create trigger solicitacoes_validar before update on rg.solicitacoes
  for each row execute function rg.tg_solicitacao_validar();

-- Histórico + notificações após cada movimentação
create function rg.tg_solicitacao_movimentar() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  v_obs  text := nullif(btrim(coalesce(current_setting('app.observacao', true), '')), '');
  v_link text := '/solicitacoes/' || new.id;
  v_ref  text := new.codigo || ' — ' || new.titulo;
begin
  if tg_op = 'INSERT' then
    insert into rg.solicitacao_historico (solicitacao_id, autor_id, acao, status_de, status_para, observacao)
    values (new.id, rg.usuario_atual_id(), 'criacao', null, new.status, v_obs);
    perform rg.notificar_papel('admin', 'Nova solicitação para análise', v_ref, 'info', v_link);
    return null;
  end if;

  if new.urgencia is distinct from old.urgencia then
    insert into rg.solicitacao_historico (solicitacao_id, autor_id, acao, status_de, status_para, observacao)
    values (new.id, rg.usuario_atual_id(), 'alteracao_urgencia', old.status, new.status,
            'Urgência: ' || old.urgencia || ' → ' || new.urgencia || '. ' || new.justificativa_urgencia);
    perform rg.notificar(new.gestor_id, 'Urgência alterada pela Administração',
      v_ref || ' agora é ' || upper(new.urgencia::text) || '.', 'alerta', v_link);
  end if;

  if new.status is not distinct from old.status then
    if (new.titulo, new.descricao, new.justificativa, new.tipo, new.valor_estimado)
       is distinct from (old.titulo, old.descricao, old.justificativa, old.tipo, old.valor_estimado) then
      insert into rg.solicitacao_historico (solicitacao_id, autor_id, acao, status_de, status_para, observacao)
      values (new.id, rg.usuario_atual_id(), 'edicao', old.status, new.status, v_obs);
    end if;
    return null;
  end if;

  insert into rg.solicitacao_historico (solicitacao_id, autor_id, acao, status_de, status_para, observacao)
  values (new.id, rg.usuario_atual_id(), 'mudanca_status', old.status, new.status,
          coalesce(v_obs, case new.status
            when 'rejeitado_adm' then new.justificativa_adm
            when 'necessita_nova_cotacao' then new.motivo_nova_cotacao
            when 'rejeitado_compras' then new.justificativa_compras
            when 'cancelado' then new.motivo_cancelamento
            when 'aprovado_adm' then new.justificativa_adm
          end));

  case new.status
    when 'aprovado_adm' then
      perform rg.notificar(new.gestor_id, 'Solicitação aprovada pela Administração', v_ref || ' foi liberada para Compras.', 'sucesso', v_link);
      perform rg.notificar_papel('compras', 'Nova solicitação liberada para cotação', v_ref, 'info', v_link);
    when 'rejeitado_adm' then
      perform rg.notificar(new.gestor_id, 'Solicitação rejeitada pela Administração', v_ref || ': ' || new.justificativa_adm, 'erro', v_link);
    when 'necessita_nova_cotacao' then
      perform rg.notificar(new.gestor_id, 'Nova cotação solicitada', v_ref || ': ' || new.motivo_nova_cotacao, 'alerta', v_link);
    when 'aguardando_adm' then
      perform rg.notificar_papel('admin', 'Solicitação reenviada com nova cotação', v_ref, 'info', v_link);
    when 'em_cotacao' then
      perform rg.notificar(new.gestor_id, 'Cotação iniciada por Compras', v_ref, 'info', v_link);
    when 'aprovado' then
      perform rg.notificar(new.gestor_id, 'Solicitação homologada', v_ref || ' aprovada por R$ ' ||
        to_char(new.valor_final_aprovado, 'FM999G999G990D00'), 'sucesso', v_link);
      perform rg.notificar_papel('admin', 'Solicitação homologada por Compras', v_ref, 'sucesso', v_link);
    when 'rejeitado_compras' then
      perform rg.notificar(new.gestor_id, 'Solicitação rejeitada por Compras', v_ref || ': ' || new.justificativa_compras, 'erro', v_link);
      perform rg.notificar_papel('admin', 'Solicitação rejeitada por Compras', v_ref, 'alerta', v_link);
    when 'cancelado' then
      perform rg.notificar_papel('admin', 'Solicitação cancelada pelo gestor', v_ref, 'info', v_link);
    else
      null;
  end case;
  return null;
end $$;

create trigger solicitacoes_movimentar after insert or update on rg.solicitacoes
  for each row execute function rg.tg_solicitacao_movimentar();

-- Toda submissão e decisão exige assinatura digital registrada na mesma transação.
create function rg.tg_solicitacao_exigir_assinatura() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  if tg_op = 'UPDATE' and new.status is not distinct from old.status then
    return null;
  end if;
  if new.status = 'cancelado' or new.status = 'em_cotacao' then
    return null;
  end if;
  if not exists (
      select 1 from rg.assinaturas a
       where a.solicitacao_id = new.id
         and a.status_resultante = new.status
         and a.txid = txid_current()) then
    raise exception 'A movimentação para % exige assinatura digital do responsável', new.status using errcode = 'P0001';
  end if;
  return null;
end $$;

create constraint trigger solicitacoes_exigir_assinatura
  after insert or update of status on rg.solicitacoes
  deferrable initially deferred
  for each row execute function rg.tg_solicitacao_exigir_assinatura();

-- ---------------------------------------------------------------------
-- Anexos: limite de 3 documentos ativos do solicitante por solicitação
-- ---------------------------------------------------------------------
create function rg.tg_anexos_limite() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
begin
  if new.origem = 'solicitante' and new.removido_em is null then
    perform 1 from rg.solicitacoes where id = new.solicitacao_id for update;
    if (select count(*) from rg.anexos
         where solicitacao_id = new.solicitacao_id and origem = 'solicitante'
           and removido_em is null and id <> new.id) >= 3 then
      raise exception 'Limite de 3 anexos ativos por solicitação atingido' using errcode = 'P0001';
    end if;
  end if;
  if tg_op = 'UPDATE' and (new.sha256, new.caminho, new.solicitacao_id, new.servico_id, new.origem, new.enviado_por)
      is distinct from (old.sha256, old.caminho, old.solicitacao_id, old.servico_id, old.origem, old.enviado_por) then
    raise exception 'Metadados de integridade do anexo não podem ser alterados' using errcode = 'P0001';
  end if;
  return new;
end $$;

create trigger anexos_limite before insert or update on rg.anexos
  for each row execute function rg.tg_anexos_limite();

-- ---------------------------------------------------------------------
-- Serviços programados: código sequencial
-- ---------------------------------------------------------------------
create function rg.tg_servico_inserir() returns trigger
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare v_setor rg.setores;
begin
  select * into v_setor from rg.setores where codigo = new.setor_codigo;
  if not v_setor.ativo then
    raise exception 'Setor % inativo', new.setor_codigo using errcode = 'P0001';
  end if;
  new.codigo := 'SRV-' || to_char(now() at time zone 'America/Sao_Paulo', 'YYYY') || '-'
                || lpad(nextval('rg.servico_codigo_seq')::text, 6, '0');
  return new;
end $$;

create trigger servicos_inserir before insert on rg.servicos_programados
  for each row execute function rg.tg_servico_inserir();

create function rg.tg_servico_validar() returns trigger
language plpgsql
as $$
begin
  if new.codigo <> old.codigo or new.serie_id <> old.serie_id or new.criado_por <> old.criado_por then
    raise exception 'Campos estruturais do serviço não podem ser alterados' using errcode = 'P0001';
  end if;
  if old.situacao in ('concluido', 'cancelado') then
    raise exception 'Serviço % já está encerrado', old.codigo using errcode = 'P0001';
  end if;
  if new.situacao is distinct from old.situacao and not (
       (old.situacao = 'agendado' and new.situacao in ('em_andamento', 'concluido', 'cancelado'))
    or (old.situacao = 'em_andamento' and new.situacao in ('concluido', 'cancelado'))) then
    raise exception 'Transição inválida do serviço: % → %', old.situacao, new.situacao using errcode = 'P0001';
  end if;
  return new;
end $$;

create trigger servicos_validar before update on rg.servicos_programados
  for each row execute function rg.tg_servico_validar();

-- ---------------------------------------------------------------------
-- Alertas de SLA (executado periodicamente pela API)
-- ---------------------------------------------------------------------
create function rg.processar_alertas_sla() returns int
language plpgsql security definer
set search_path = rg, pg_temp
as $$
declare
  r      record;
  v_qtd  int := 0;
  v_link text;
  v_ref  text;
begin
  for r in
    select * from rg.solicitacoes
     where not rg.status_terminal(status)
       and sla_estouro_notificado_em is null
       and now() > sla_prazo_limite
     for update skip locked
  loop
    v_link := '/solicitacoes/' || r.id;
    v_ref := r.codigo || ' — ' || r.titulo;
    perform rg.notificar_papel('admin', 'SLA estourado', v_ref || ' ultrapassou o prazo.', 'erro', v_link);
    if r.status in ('aprovado_adm', 'em_cotacao') then
      perform rg.notificar_papel('compras', 'SLA estourado', v_ref || ' ultrapassou o prazo.', 'erro', v_link);
    end if;
    perform rg.notificar(r.gestor_id, 'SLA estourado', v_ref || ' ultrapassou o prazo.', 'erro', v_link);
    update rg.solicitacoes set sla_estouro_notificado_em = now(), sla_alerta_notificado_em = coalesce(sla_alerta_notificado_em, now())
     where id = r.id;
    v_qtd := v_qtd + 1;
  end loop;

  for r in
    select * from rg.solicitacoes
     where not rg.status_terminal(status)
       and sla_alerta_notificado_em is null
       and now() <= sla_prazo_limite
       and sla_prazo_limite - now() < interval '24 hours'
     for update skip locked
  loop
    v_link := '/solicitacoes/' || r.id;
    v_ref := r.codigo || ' — ' || r.titulo;
    case
      when r.status = 'aguardando_adm' then
        perform rg.notificar_papel('admin', 'SLA em alerta (< 24h)', v_ref, 'alerta', v_link);
      when r.status in ('aprovado_adm', 'em_cotacao') then
        perform rg.notificar_papel('compras', 'SLA em alerta (< 24h)', v_ref, 'alerta', v_link);
      else
        perform rg.notificar(r.gestor_id, 'SLA em alerta (< 24h)', v_ref, 'alerta', v_link);
    end case;
    update rg.solicitacoes set sla_alerta_notificado_em = now() where id = r.id;
    v_qtd := v_qtd + 1;
  end loop;
  return v_qtd;
end $$;

-- ---------------------------------------------------------------------
-- Views de leitura
-- ---------------------------------------------------------------------

-- Dados não sensíveis de usuários para exibição de nomes (executa como dono).
create view rg.v_usuarios_publico as
  select id, nome, papel, setor_codigo, status from rg.usuarios;

create view rg.v_solicitacoes with (security_invoker = true) as
  select s.*,
         rg.sla_situacao(s.status, s.sla_prazo_limite, s.sla_concluido_em) as sla_situacao,
         round((extract(epoch from (s.sla_prazo_limite - coalesce(s.sla_concluido_em, now()))) / 3600.0)::numeric, 1) as sla_horas_restantes,
         st.nome as setor_nome,
         st.cor  as setor_cor,
         g.nome  as gestor_nome,
         c.nome  as comprador_nome
    from rg.solicitacoes s
    join rg.setores st on st.codigo = s.setor_codigo
    left join rg.v_usuarios_publico g on g.id = s.gestor_id
    left join rg.v_usuarios_publico c on c.id = s.comprador_id;

create view rg.v_servicos with (security_invoker = true) as
  select sp.*,
         st.nome as setor_nome,
         st.cor  as setor_cor,
         u.nome  as criado_por_nome,
         (sp.situacao in ('agendado', 'em_andamento')
          and (sp.data_programada + sp.hora_termino) < (now() at time zone 'America/Sao_Paulo')) as atrasado
    from rg.servicos_programados sp
    join rg.setores st on st.codigo = sp.setor_codigo
    left join rg.v_usuarios_publico u on u.id = sp.criado_por;
