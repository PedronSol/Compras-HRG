-- =====================================================================
-- Hospital Rio Grande · Compras — 0003: Row Level Security e privilégios do papel rg_app
--
-- Visibilidade das solicitações (e de tudo o que delas depende):
--   Administrador, Financeiro, Diretoria, Auditoria → todas
--   Solicitante e Gestor → somente o próprio setor
--   Comprador            → as que já foram aprovadas
--   Recebimento          → as que possuem pedido de compra
-- Auditoria é somente leitura em todas as tabelas.
-- As subconsultas usam (select fn()) para avaliação única por consulta.
-- =====================================================================

-- ---------------------------------------------------------------------
-- Privilégios (tabelas derivadas por trigger não recebem escrita direta)
-- ---------------------------------------------------------------------
revoke all on schema rg, audit from public;
grant usage on schema rg, audit to rg_app;

grant select on all tables in schema rg to rg_app;
grant select on audit.eventos to rg_app;

grant insert, update                  on rg.usuarios          to rg_app;
grant insert, delete                  on rg.senhas_historico  to rg_app;
grant insert, update, delete          on rg.sessoes           to rg_app;
grant update                          on rg.setores           to rg_app;
grant update (valor)                  on rg.configuracoes     to rg_app;
grant insert, update                  on rg.categorias        to rg_app;
grant insert, update                  on rg.materiais         to rg_app;
grant insert, update                  on rg.fornecedores      to rg_app;
grant insert, update                  on rg.solicitacoes      to rg_app;
grant insert, update, delete          on rg.solicitacao_itens to rg_app;
grant insert, update                  on rg.anexos            to rg_app;
grant insert, update, delete          on rg.cotacoes          to rg_app;
grant insert, update, delete          on rg.cotacao_itens     to rg_app;
grant insert, update                  on rg.pedidos           to rg_app;
grant insert                          on rg.recebimentos      to rg_app;
grant insert                          on rg.recebimento_itens to rg_app;
grant insert                          on rg.assinaturas       to rg_app;
grant update (lida, lida_em)          on rg.notificacoes      to rg_app;
-- pedido_itens, aprovacoes e solicitacao_historico: somente leitura (mantidos por triggers)

grant usage on all sequences in schema rg to rg_app;
grant execute on all functions in schema rg to rg_app;
grant execute on function audit.registrar_evento(text, text, text, jsonb) to rg_app;
revoke execute on function audit.tg_registrar() from public;

-- ---------------------------------------------------------------------
-- Habilita RLS em todas as tabelas de negócio
-- ---------------------------------------------------------------------
alter table rg.setores               enable row level security;
alter table rg.configuracoes         enable row level security;
alter table rg.usuarios              enable row level security;
alter table rg.senhas_historico      enable row level security;
alter table rg.sessoes               enable row level security;
alter table rg.categorias            enable row level security;
alter table rg.materiais             enable row level security;
alter table rg.fornecedores          enable row level security;
alter table rg.solicitacoes          enable row level security;
alter table rg.solicitacao_itens     enable row level security;
alter table rg.anexos                enable row level security;
alter table rg.cotacoes              enable row level security;
alter table rg.cotacao_itens         enable row level security;
alter table rg.pedidos               enable row level security;
alter table rg.pedido_itens          enable row level security;
alter table rg.recebimentos          enable row level security;
alter table rg.recebimento_itens     enable row level security;
alter table rg.aprovacoes            enable row level security;
alter table rg.assinaturas           enable row level security;
alter table rg.solicitacao_historico enable row level security;
alter table rg.notificacoes          enable row level security;
alter table audit.eventos            enable row level security;

-- Referência e catálogo -------------------------------------------------
create policy setores_leitura on rg.setores for select to rg_app using (true);
create policy setores_admin on rg.setores for update to rg_app
  using ((select rg.papel_atual()) = 'admin') with check ((select rg.papel_atual()) = 'admin');

create policy configuracoes_leitura on rg.configuracoes for select to rg_app
  using ((select rg.eh_sistema()) or (select rg.papel_atual()) is not null);
create policy configuracoes_admin on rg.configuracoes for update to rg_app
  using ((select rg.papel_atual()) = 'admin') with check ((select rg.papel_atual()) = 'admin');

create policy categorias_leitura on rg.categorias for select to rg_app
  using ((select rg.papel_atual()) is not null);
create policy categorias_escrita on rg.categorias for insert to rg_app
  with check ((select rg.papel_atual()) in ('comprador', 'admin'));
create policy categorias_atualizacao on rg.categorias for update to rg_app
  using ((select rg.papel_atual()) in ('comprador', 'admin'))
  with check ((select rg.papel_atual()) in ('comprador', 'admin'));

create policy materiais_leitura on rg.materiais for select to rg_app
  using ((select rg.papel_atual()) is not null);
create policy materiais_escrita on rg.materiais for insert to rg_app
  with check ((select rg.papel_atual()) in ('comprador', 'admin'));
create policy materiais_atualizacao on rg.materiais for update to rg_app
  using ((select rg.papel_atual()) in ('comprador', 'admin'))
  with check ((select rg.papel_atual()) in ('comprador', 'admin'));

create policy fornecedores_leitura on rg.fornecedores for select to rg_app
  using ((select rg.papel_atual()) is not null);
create policy fornecedores_insercao on rg.fornecedores for insert to rg_app
  with check ((select rg.papel_atual()) in ('comprador', 'admin'));
create policy fornecedores_atualizacao on rg.fornecedores for update to rg_app
  using ((select rg.papel_atual()) in ('comprador', 'admin'))
  with check ((select rg.papel_atual()) in ('comprador', 'admin'));

-- Usuários ------------------------------------------------------------
create policy usuarios_leitura on rg.usuarios for select to rg_app using (
  (select rg.eh_sistema())
  or id = (select rg.usuario_atual_id())
  or (select rg.papel_atual()) in ('admin', 'auditoria')
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

-- Solicitações --------------------------------------------------------
create policy solicitacoes_leitura on rg.solicitacoes for select to rg_app using (
  (select rg.eh_sistema())
  or (select rg.papel_atual()) in ('admin', 'financeiro', 'diretoria', 'auditoria')
  or ((select rg.papel_atual()) in ('solicitante', 'gestor') and setor_codigo = (select rg.setor_atual()))
  or ((select rg.papel_atual()) = 'comprador' and aprovado_em is not null)
  or ((select rg.papel_atual()) = 'recebimento' and pedido_emitido_em is not null)
);
create policy solicitacoes_insercao on rg.solicitacoes for insert to rg_app with check (
  (select rg.papel_atual()) in ('solicitante', 'gestor')
  and setor_codigo = (select rg.setor_atual())
  and solicitante_id = (select rg.usuario_atual_id())
);
create policy solicitacoes_atualizacao on rg.solicitacoes for update to rg_app
  using (
    ((select rg.papel_atual()) in ('solicitante', 'gestor') and setor_codigo = (select rg.setor_atual()))
    or (select rg.papel_atual()) in ('diretoria', 'admin')
    or ((select rg.papel_atual()) = 'comprador' and aprovado_em is not null)
  )
  with check (
    ((select rg.papel_atual()) in ('solicitante', 'gestor') and setor_codigo = (select rg.setor_atual()))
    or (select rg.papel_atual()) in ('diretoria', 'admin')
    or ((select rg.papel_atual()) = 'comprador' and aprovado_em is not null)
  );

-- Tabelas dependentes herdam a visibilidade da solicitação --------------
create policy sol_itens_leitura on rg.solicitacao_itens for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = solicitacao_itens.solicitacao_id)
);
create policy sol_itens_escrita on rg.solicitacao_itens for all to rg_app
  using ((select rg.papel_atual()) in ('solicitante', 'gestor')
         and exists (select 1 from rg.solicitacoes s where s.id = solicitacao_itens.solicitacao_id
                       and s.setor_codigo = (select rg.setor_atual())))
  with check ((select rg.papel_atual()) in ('solicitante', 'gestor')
         and exists (select 1 from rg.solicitacoes s where s.id = solicitacao_itens.solicitacao_id
                       and s.setor_codigo = (select rg.setor_atual())));

create policy anexos_leitura on rg.anexos for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = anexos.solicitacao_id)
);
create policy anexos_insercao on rg.anexos for insert to rg_app with check (
  enviado_por = (select rg.usuario_atual_id())
  and (select rg.papel_atual()) in ('solicitante', 'gestor', 'comprador', 'recebimento')
  and exists (select 1 from rg.solicitacoes s where s.id = anexos.solicitacao_id)
);
create policy anexos_atualizacao on rg.anexos for update to rg_app
  using (
    (select rg.papel_atual()) in ('solicitante', 'gestor', 'comprador')
    and exists (select 1 from rg.solicitacoes s where s.id = anexos.solicitacao_id)
    and (enviado_por = (select rg.usuario_atual_id())
         or (origem = 'solicitante' and (select rg.papel_atual()) in ('solicitante', 'gestor'))
         or (origem = 'comprador' and (select rg.papel_atual()) = 'comprador'))
  )
  with check (true);

create policy cotacoes_leitura on rg.cotacoes for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = cotacoes.solicitacao_id)
);
create policy cotacoes_escrita on rg.cotacoes for all to rg_app
  using ((select rg.papel_atual()) = 'comprador'
         and exists (select 1 from rg.solicitacoes s where s.id = cotacoes.solicitacao_id))
  with check ((select rg.papel_atual()) = 'comprador'
         and exists (select 1 from rg.solicitacoes s where s.id = cotacoes.solicitacao_id));

create policy cotacao_itens_leitura on rg.cotacao_itens for select to rg_app using (
  exists (select 1 from rg.cotacoes c where c.id = cotacao_itens.cotacao_id)
);
create policy cotacao_itens_escrita on rg.cotacao_itens for all to rg_app
  using ((select rg.papel_atual()) = 'comprador'
         and exists (select 1 from rg.cotacoes c where c.id = cotacao_itens.cotacao_id))
  with check ((select rg.papel_atual()) = 'comprador'
         and exists (select 1 from rg.cotacoes c where c.id = cotacao_itens.cotacao_id));

-- Pedidos -------------------------------------------------------------
create policy pedidos_leitura on rg.pedidos for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = pedidos.solicitacao_id)
);
create policy pedidos_insercao on rg.pedidos for insert to rg_app with check (
  (select rg.papel_atual()) = 'comprador'
  and exists (select 1 from rg.solicitacoes s where s.id = pedidos.solicitacao_id)
);
create policy pedidos_atualizacao on rg.pedidos for update to rg_app
  using ((select rg.papel_atual()) in ('comprador', 'financeiro', 'diretoria', 'admin')
         and exists (select 1 from rg.solicitacoes s where s.id = pedidos.solicitacao_id))
  with check ((select rg.papel_atual()) in ('comprador', 'financeiro', 'diretoria', 'admin'));

create policy pedido_itens_leitura on rg.pedido_itens for select to rg_app using (
  exists (select 1 from rg.pedidos p where p.id = pedido_itens.pedido_id)
);

-- Recebimentos --------------------------------------------------------
create policy recebimentos_leitura on rg.recebimentos for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = recebimentos.solicitacao_id)
);
create policy recebimentos_insercao on rg.recebimentos for insert to rg_app with check (
  (select rg.papel_atual()) = 'recebimento'
);
create policy rec_itens_leitura on rg.recebimento_itens for select to rg_app using (
  exists (select 1 from rg.recebimentos r where r.id = recebimento_itens.recebimento_id)
);
create policy rec_itens_insercao on rg.recebimento_itens for insert to rg_app with check (
  (select rg.papel_atual()) = 'recebimento'
);

-- Aprovações, assinaturas e histórico ----------------------------------
create policy aprovacoes_leitura on rg.aprovacoes for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = aprovacoes.solicitacao_id)
);
create policy assinaturas_leitura on rg.assinaturas for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = assinaturas.solicitacao_id)
);
create policy assinaturas_insercao on rg.assinaturas for insert to rg_app with check (
  usuario_id = (select rg.usuario_atual_id())
  and papel = (select rg.papel_atual())
  and (select rg.papel_atual()) <> 'auditoria'
  and exists (select 1 from rg.solicitacoes s where s.id = assinaturas.solicitacao_id)
);
create policy historico_leitura on rg.solicitacao_historico for select to rg_app using (
  exists (select 1 from rg.solicitacoes s where s.id = solicitacao_historico.solicitacao_id)
);

-- Notificações --------------------------------------------------------
create policy notificacoes_proprias on rg.notificacoes for select to rg_app
  using (destinatario_id = (select rg.usuario_atual_id()));
create policy notificacoes_marcar on rg.notificacoes for update to rg_app
  using (destinatario_id = (select rg.usuario_atual_id()))
  with check (destinatario_id = (select rg.usuario_atual_id()));

-- Auditoria (Administrador e Auditoria) ------------------------------
create policy eventos_leitura on audit.eventos for select to rg_app
  using ((select rg.papel_atual()) in ('admin', 'auditoria'));
