-- =====================================================================
-- RG Hospital — 0003: Row Level Security e privilégios do papel rg_app
--   Gestor  → apenas o próprio setor
--   Compras → solicitações liberadas pela Administração
--   Admin   → acesso global
-- As subconsultas usam (select fn()) para avaliação única por consulta.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Privilégios
-- ---------------------------------------------------------------------
revoke all on schema rg, audit from public;
grant usage on schema rg, audit to rg_app;

grant select on all tables in schema rg to rg_app;
grant select on audit.eventos to rg_app;

grant insert, update                  on rg.usuarios             to rg_app;
grant insert, delete                  on rg.senhas_historico     to rg_app;
grant insert, update, delete          on rg.sessoes              to rg_app;
grant update                          on rg.setores              to rg_app;
grant insert, update                  on rg.fornecedores         to rg_app;
grant insert, update                  on rg.solicitacoes         to rg_app;
grant insert, update                  on rg.anexos               to rg_app;
grant insert, update, delete          on rg.cotacoes             to rg_app;
grant insert                          on rg.assinaturas          to rg_app;
grant update (lida, lida_em)          on rg.notificacoes         to rg_app;
grant insert, update                  on rg.servicos_programados to rg_app;

grant usage on all sequences in schema rg to rg_app;
grant execute on all functions in schema rg to rg_app;
grant execute on function audit.registrar_evento(text, text, text, jsonb) to rg_app;
revoke execute on function audit.tg_registrar() from public;

-- ---------------------------------------------------------------------
-- Habilita RLS em todas as tabelas de negócio
-- ---------------------------------------------------------------------
alter table rg.setores               enable row level security;
alter table rg.usuarios              enable row level security;
alter table rg.senhas_historico      enable row level security;
alter table rg.sessoes               enable row level security;
alter table rg.fornecedores          enable row level security;
alter table rg.solicitacoes          enable row level security;
alter table rg.servicos_programados  enable row level security;
alter table rg.anexos                enable row level security;
alter table rg.cotacoes              enable row level security;
alter table rg.assinaturas           enable row level security;
alter table rg.solicitacao_historico enable row level security;
alter table rg.notificacoes          enable row level security;
alter table audit.eventos            enable row level security;

-- Setores -------------------------------------------------------------
create policy setores_leitura on rg.setores for select to rg_app using (true);
create policy setores_admin on rg.setores for update to rg_app
  using ((select rg.papel_atual()) = 'admin') with check ((select rg.papel_atual()) = 'admin');

-- Usuários ------------------------------------------------------------
create policy usuarios_leitura on rg.usuarios for select to rg_app using (
  (select rg.eh_sistema())
  or id = (select rg.usuario_atual_id())
  or (select rg.papel_atual()) = 'admin'
);
create policy usuarios_insercao on rg.usuarios for insert to rg_app with check (
  (select rg.eh_sistema()) or (select rg.papel_atual()) = 'admin'
);
create policy usuarios_atualizacao on rg.usuarios for update to rg_app
  using ((select rg.eh_sistema()) or id = (select rg.usuario_atual_id()) or (select rg.papel_atual()) = 'admin')
  with check ((select rg.eh_sistema()) or id = (select rg.usuario_atual_id()) or (select rg.papel_atual()) = 'admin');

create policy senhas_historico_acesso on rg.senhas_historico for all to rg_app
  using ((select rg.eh_sistema()) or usuario_id = (select rg.usuario_atual_id()))
  with check ((select rg.eh_sistema()) or usuario_id = (select rg.usuario_atual_id()));

create policy sessoes_acesso on rg.sessoes for all to rg_app
  using ((select rg.eh_sistema()) or usuario_id = (select rg.usuario_atual_id()))
  with check ((select rg.eh_sistema()) or usuario_id = (select rg.usuario_atual_id()));

-- Fornecedores --------------------------------------------------------
create policy fornecedores_leitura on rg.fornecedores for select to rg_app
  using ((select rg.papel_atual()) is not null);
create policy fornecedores_insercao on rg.fornecedores for insert to rg_app
  with check ((select rg.papel_atual()) in ('compras', 'admin'));
create policy fornecedores_atualizacao on rg.fornecedores for update to rg_app
  using ((select rg.papel_atual()) in ('compras', 'admin'))
  with check ((select rg.papel_atual()) in ('compras', 'admin'));

-- Solicitações --------------------------------------------------------
create policy solicitacoes_leitura on rg.solicitacoes for select to rg_app using (
  (select rg.eh_sistema())
  or (select rg.papel_atual()) = 'admin'
  or ((select rg.papel_atual()) = 'gestor' and setor_codigo = (select rg.setor_atual()))
  or ((select rg.papel_atual()) = 'compras' and status in ('aprovado_adm', 'em_cotacao', 'aprovado', 'rejeitado_compras'))
);
create policy solicitacoes_insercao on rg.solicitacoes for insert to rg_app with check (
  (select rg.papel_atual()) = 'gestor'
  and setor_codigo = (select rg.setor_atual())
  and gestor_id = (select rg.usuario_atual_id())
);
create policy solicitacoes_atualizacao on rg.solicitacoes for update to rg_app
  using (
    ((select rg.papel_atual()) = 'admin' and status in ('aguardando_adm', 'necessita_nova_cotacao'))
    or ((select rg.papel_atual()) = 'gestor' and setor_codigo = (select rg.setor_atual())
        and status in ('aguardando_adm', 'necessita_nova_cotacao'))
    or ((select rg.papel_atual()) = 'compras' and status in ('aprovado_adm', 'em_cotacao'))
  )
  with check (
    (select rg.papel_atual()) = 'admin'
    or ((select rg.papel_atual()) = 'gestor' and setor_codigo = (select rg.setor_atual()))
    or ((select rg.papel_atual()) = 'compras' and status in ('aprovado_adm', 'em_cotacao', 'aprovado', 'rejeitado_compras'))
  );

-- Serviços programados ------------------------------------------------
create policy servicos_leitura on rg.servicos_programados for select to rg_app using (
  (select rg.eh_sistema())
  or (select rg.papel_atual()) in ('admin', 'compras')
  or ((select rg.papel_atual()) = 'gestor' and setor_codigo = (select rg.setor_atual()))
);
create policy servicos_insercao on rg.servicos_programados for insert to rg_app with check (
  criado_por = (select rg.usuario_atual_id())
  and ((select rg.papel_atual()) = 'admin'
       or ((select rg.papel_atual()) = 'gestor' and setor_codigo = (select rg.setor_atual())))
);
create policy servicos_atualizacao on rg.servicos_programados for update to rg_app
  using ((select rg.papel_atual()) = 'admin'
         or ((select rg.papel_atual()) = 'gestor' and setor_codigo = (select rg.setor_atual())))
  with check ((select rg.papel_atual()) = 'admin'
              or ((select rg.papel_atual()) = 'gestor' and setor_codigo = (select rg.setor_atual())));

-- Anexos (visibilidade herdada da solicitação/serviço) ----------------
create policy anexos_leitura on rg.anexos for select to rg_app using (
  (select rg.eh_sistema())
  or exists (select 1 from rg.solicitacoes s where s.id = anexos.solicitacao_id)
  or exists (select 1 from rg.servicos_programados sp where sp.id = anexos.servico_id)
);
create policy anexos_insercao on rg.anexos for insert to rg_app with check (
  enviado_por = (select rg.usuario_atual_id())
  and (
    (origem = 'solicitante' and (select rg.papel_atual()) = 'gestor'
      and exists (select 1 from rg.solicitacoes s where s.id = anexos.solicitacao_id
                    and s.setor_codigo = (select rg.setor_atual())
                    and s.status in ('aguardando_adm', 'necessita_nova_cotacao')))
    or (origem = 'compras' and (select rg.papel_atual()) = 'compras'
      and exists (select 1 from rg.solicitacoes s where s.id = anexos.solicitacao_id and s.status = 'em_cotacao'))
    or (origem = 'servico'
      and exists (select 1 from rg.servicos_programados sp where sp.id = anexos.servico_id
                    and sp.situacao in ('agendado', 'em_andamento')
                    and ((select rg.papel_atual()) = 'admin'
                         or ((select rg.papel_atual()) = 'gestor' and sp.setor_codigo = (select rg.setor_atual())))))
  )
);
create policy anexos_atualizacao on rg.anexos for update to rg_app
  using (
    (select rg.eh_sistema())
    or (origem = 'solicitante' and (select rg.papel_atual()) = 'gestor'
      and exists (select 1 from rg.solicitacoes s where s.id = anexos.solicitacao_id
                    and s.setor_codigo = (select rg.setor_atual())
                    and s.status in ('aguardando_adm', 'necessita_nova_cotacao')))
    or (origem = 'compras' and (select rg.papel_atual()) = 'compras'
      and exists (select 1 from rg.solicitacoes s where s.id = anexos.solicitacao_id and s.status = 'em_cotacao'))
    or (origem = 'servico'
      and exists (select 1 from rg.servicos_programados sp where sp.id = anexos.servico_id
                    and sp.situacao in ('agendado', 'em_andamento')
                    and ((select rg.papel_atual()) = 'admin'
                         or ((select rg.papel_atual()) = 'gestor' and sp.setor_codigo = (select rg.setor_atual())))))
  )
  with check (true);

-- Cotações (somente Compras, durante a cotação) -----------------------
create policy cotacoes_leitura on rg.cotacoes for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = cotacoes.solicitacao_id)
);
create policy cotacoes_escrita on rg.cotacoes for all to rg_app
  using ((select rg.papel_atual()) = 'compras'
         and exists (select 1 from rg.solicitacoes s where s.id = cotacoes.solicitacao_id and s.status = 'em_cotacao'))
  with check ((select rg.papel_atual()) = 'compras'
         and exists (select 1 from rg.solicitacoes s where s.id = cotacoes.solicitacao_id and s.status = 'em_cotacao'));

-- Assinaturas ---------------------------------------------------------
create policy assinaturas_leitura on rg.assinaturas for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = assinaturas.solicitacao_id)
);
create policy assinaturas_insercao on rg.assinaturas for insert to rg_app with check (
  usuario_id = (select rg.usuario_atual_id())
  and (select rg.papel_atual()) is not null
  and exists (select 1 from rg.solicitacoes s where s.id = assinaturas.solicitacao_id)
);

-- Histórico -----------------------------------------------------------
create policy historico_leitura on rg.solicitacao_historico for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = solicitacao_historico.solicitacao_id)
);

-- Notificações --------------------------------------------------------
create policy notificacoes_proprias on rg.notificacoes for select to rg_app
  using (destinatario_id = (select rg.usuario_atual_id()));
create policy notificacoes_marcar on rg.notificacoes for update to rg_app
  using (destinatario_id = (select rg.usuario_atual_id()))
  with check (destinatario_id = (select rg.usuario_atual_id()));

-- Auditoria (somente administradores) ---------------------------------
create policy eventos_admin on audit.eventos for select to rg_app
  using ((select rg.papel_atual()) = 'admin');
