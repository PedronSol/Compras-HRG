"""Fluxo completo Solicitação → Aprovação → Cotação → Fornecedor → Pedido → Recebimento → Conclusão."""
import io
from decimal import Decimal

import psycopg
import pytest

from conftest import (Cliente, acao, acao_pedido, ate_aprovada, ate_pedido, criar_solicitacao, criar_usuario,
                      fornecedor, pdf_orcamento, proposta)


def test_fluxo_completo_ate_conclusao(clientes, usuarios):
    solicitante, gestor, comprador = clientes["solicitante"], clientes["gestor"], clientes["comprador"]
    financeiro, recebimento = clientes["financeiro"], clientes["recebimento"]

    d = criar_solicitacao(solicitante)
    s, sid = d["solicitacao"], d["solicitacao"]["id"]
    assert s["status"] == "aguardando_gestor" and s["codigo"].startswith("SC-")
    assert Decimal(str(s["valor_estimado"])) == Decimal("14000.00")  # 2 × 6.500 + 4 × 250, derivado dos itens
    assert [a["acao"] for a in d["assinaturas"]] == ["submissao"]
    assert d["anexos"][0]["nome_original"] == "orcamento-medtec.pdf"
    assert "ocr_status" not in d["anexos"][0] and "dados_ocr" not in d["anexos"][0]  # nenhum conteúdo é interpretado

    # Visibilidade: Compras e Recebimento ainda não enxergam; ninguém fora do gestor aprova
    assert comprador.get(f"/api/v1/solicitacoes/{sid}").status_code == 404
    assert recebimento.get(f"/api/v1/solicitacoes/{sid}").status_code == 404
    for nome in ("solicitante", "comprador", "financeiro", "admin", "auditoria"):
        assert acao(clientes[nome], sid, "aprovar", versao=s["versao"]).status_code in (403, 404, 422), nome

    d = acao(gestor, sid, "aprovar", versao=s["versao"], texto="Necessidade confirmada.").get_json()
    assert d["solicitacao"]["status"] == "aprovada"  # abaixo da alçada: segue direto para Compras
    assert d["aprovacoes"][0]["nivel"] == "gestor" and d["aprovacoes"][0]["decisao"] == "aprovado"

    d = acao(comprador, sid, "iniciar_cotacao", versao=d["solicitacao"]["versao"]).get_json()
    assert d["solicitacao"]["status"] == "em_cotacao" and d["solicitacao"]["comprador_id"] == usuarios["comprador"]["id"]
    itens = d["itens"]

    # Proposta com documento anexado (ou fotografado) e todos os dados digitados manualmente
    r = comprador.post(f"/api/v1/solicitacoes/{sid}/anexos",
                       data={"tipo_documento": "proposta", "arquivos": [(io.BytesIO(pdf_orcamento()), "proposta.pdf")]})
    assert r.status_code == 201
    anexo_id = r.get_json()["anexos_criados"][0]
    f1 = fornecedor(comprador, "11.222.333/0001-81", "MEDTEC EQUIPAMENTOS HOSPITALARES LTDA")
    f2 = fornecedor(comprador, "12.ABC.345/01DE-35", "BIOMED SERVICOS LTDA")
    f3 = fornecedor(comprador, "45.723.174/0001-10", "LAGOA PRODUTOS HOSPITALARES LTDA")
    assert proposta(comprador, sid, f1, itens, ["6400", "240"], frete="150", anexo_id=anexo_id).status_code == 201
    assert proposta(comprador, sid, f2, itens, ["6100", "260"]).status_code == 201
    r = proposta(comprador, sid, f3, itens, ["6900,50", "230"], desconto="100")
    assert r.status_code == 201
    d = r.get_json()
    totais = {c["fornecedor_id"]: Decimal(str(c["valor_total"])) for c in d["cotacoes"]}
    assert totais[f1] == Decimal("13910.00") and totais[f2] == Decimal("13240.00") and totais[f3] == Decimal("14621.00")
    comp = d["comparacao"]
    assert Decimal(str(comp["menor_total"])) == Decimal("13240.00")
    assert comp["linhas"][1]["menor_unitario"] == 230.0
    vencedora = next(c for c in d["cotacoes"] if c["fornecedor_id"] == f2)
    assert comp["ranking"][0] == vencedora["id"]

    # Somente o comprador lança propostas
    assert proposta(clientes["gestor"], sid, f1, itens, ["1", "1"]).status_code == 403

    d = acao(comprador, sid, "definir_fornecedor", versao=d["solicitacao"]["versao"], cotacao_id=vencedora["id"]).get_json()
    assert d["solicitacao"]["status"] == "aguardando_pedido"
    assert Decimal(str(d["solicitacao"]["valor_final"])) == Decimal("13240.00")

    r = acao(comprador, sid, "emitir_pedido", versao=d["solicitacao"]["versao"],
             condicoes_pagamento="28 dias", local_entrega="Almoxarifado central")
    assert r.status_code == 200, r.get_json()
    d, pid = r.get_json(), r.get_json()["pedido_criado"]
    assert d["solicitacao"]["status"] == "em_pedido"
    p = recebimento.get(f"/api/v1/pedidos/{pid}").get_json()  # Recebimento passa a enxergar
    assert p["pedido"]["status"] == "aguardando_financeiro" and p["pedido"]["codigo"].startswith("PC-")
    assert Decimal(str(p["pedido"]["valor_total"])) == Decimal("13240.00") and len(p["itens"]) == 2
    assert p["acoes"] == []

    assert acao_pedido(comprador, pid, "aprovar", versao=p["pedido"]["versao"]).status_code == 403
    r = acao_pedido(financeiro, pid, "aprovar", versao=p["pedido"]["versao"], texto="Dotação confirmada.")
    assert r.status_code == 200, r.get_json()
    p = r.get_json()
    assert p["pedido"]["status"] == "aprovado"
    p = acao_pedido(comprador, pid, "enviar", versao=p["pedido"]["versao"]).get_json()
    assert p["pedido"]["status"] == "enviado" and p["pedido"]["data_prevista_entrega"]

    # 1º recebimento: parcial com divergência (uma unidade avariada)
    monitor, cabo = p["itens"]
    itens_rec = [{"pedido_item_id": monitor["id"], "quantidade_recebida": "2", "quantidade_aceita": "1",
                  "motivo_divergencia": "Tela trincada no transporte"},
                 {"pedido_item_id": cabo["id"], "quantidade_recebida": "4", "quantidade_aceita": "4"}]
    import json
    r = recebimento.post(f"/api/v1/pedidos/{pid}/recebimentos",
                         data={"nota_fiscal": "4521", "valor_nf": "13240,00", "itens": json.dumps(itens_rec),
                               "arquivos": [(io.BytesIO(b"\xff\xd8\xff\xe0 foto nota"), "nota.jpg")]})
    assert r.status_code == 201, r.get_json()
    p = r.get_json()
    assert p["pedido"]["status"] == "entregue_parcial" and p["recebimentos"][0]["situacao"] == "divergente"
    assert p["recebimentos"][0]["anexos"][0]["nome_original"] == "nota.jpg"
    assert solicitante.get(f"/api/v1/solicitacoes/{sid}").get_json()["solicitacao"]["status"] == "recebida_parcial"

    # Não é possível aceitar além do saldo
    excesso = [{"pedido_item_id": monitor["id"], "quantidade_recebida": "3", "quantidade_aceita": "3"}]
    assert recebimento.post(f"/api/v1/pedidos/{pid}/recebimentos",
                            json={"nota_fiscal": "4600", "itens": excesso}).status_code == 422

    r = recebimento.post(f"/api/v1/pedidos/{pid}/recebimentos", json={
        "nota_fiscal": "4588", "itens": [{"pedido_item_id": monitor["id"], "quantidade_recebida": "1", "quantidade_aceita": "1"}]})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["pedido"]["status"] == "entregue"

    d = solicitante.get(f"/api/v1/solicitacoes/{sid}").get_json()
    assert d["solicitacao"]["status"] == "concluida" and d["acoes"] == []
    acoes = [a["acao"] for a in d["assinaturas"]]
    assert acoes == ["submissao", "aprovacao_gestor", "definicao_fornecedor", "emissao_pedido", "aprovacao_financeiro",
                     "envio_pedido", "recebimento", "recebimento"]
    assert [a["nivel"] for a in d["aprovacoes"]] == ["gestor", "financeiro"]
    for a in d["assinaturas"]:
        v = solicitante.get(f"/api/v1/assinaturas/{a['id']}/verificar").get_json()
        assert v["registro_integro"] is True
    assert any(n["titulo"] == "Solicitação concluída" for n in solicitante.get("/api/v1/notificacoes").get_json()["itens"])

    # Encerrada: nada mais pode ser alterado
    assert acao(comprador, sid, "cancelar", versao=d["solicitacao"]["versao"], texto="Tentativa após conclusão").status_code == 422

    r = solicitante.get(f"/api/v1/solicitacoes/{sid}/dossie.pdf")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    r = comprador.get(f"/api/v1/pedidos/{pid}/documento.pdf")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_alcada_da_diretoria_e_segregacao_de_funcoes(clientes, usuarios):
    gestor, diretoria = clientes["gestor"], clientes["diretoria"]
    itens_caros = [{"descricao": "Ventilador pulmonar", "unidade": "UN", "quantidade": "1",
                    "valor_unitario_estimado": "48000"}]
    d = criar_solicitacao(clientes["solicitante"], com_anexo=False, itens=itens_caros)
    sid = d["solicitacao"]["id"]
    d = acao(gestor, sid, "aprovar", versao=d["solicitacao"]["versao"]).get_json()
    assert d["solicitacao"]["status"] == "aguardando_diretoria"  # acima da alçada (R$ 25.000)
    assert acao(gestor, sid, "aprovar", versao=d["solicitacao"]["versao"]).status_code == 422
    d = acao(diretoria, sid, "aprovar", versao=d["solicitacao"]["versao"], texto="Previsto no plano anual.").get_json()
    assert d["solicitacao"]["status"] == "aprovada"
    assert [a["nivel"] for a in d["aprovacoes"]] == ["gestor", "diretoria"]

    # Aberta pelo próprio gestor: vai direto à Diretoria (sem autoaprovação)
    d = criar_solicitacao(gestor, com_anexo=False)
    assert d["solicitacao"]["status"] == "aguardando_diretoria" and d["solicitacao"]["aberta_por_gestor"] is True
    assert "aprovar" not in d["acoes"]

    # Gestor de outro setor não enxerga nem aprova
    d = criar_solicitacao(clientes["solicitante"], com_anexo=False)
    assert "aprovar" in gestor.get(f"/api/v1/solicitacoes/{d['solicitacao']['id']}").get_json()["acoes"]
    assert acao(clientes["gestor_lab"], d["solicitacao"]["id"], "aprovar").status_code == 404


def test_devolucao_ajuste_e_reenvio(clientes):
    solicitante, gestor = clientes["solicitante"], clientes["gestor"]
    d = criar_solicitacao(solicitante)
    sid, versao = d["solicitacao"]["id"], d["solicitacao"]["versao"]
    assert acao(gestor, sid, "devolver", versao=versao, texto="curto").status_code == 422
    d = acao(gestor, sid, "devolver", versao=versao, texto="Detalhe a especificação técnica dos monitores.").get_json()
    assert d["solicitacao"]["status"] == "devolvida" and "reenviar" not in d["acoes"]
    d = solicitante.get(f"/api/v1/solicitacoes/{sid}").get_json()
    assert "reenviar" in d["acoes"]
    import json
    novos = [{"descricao": "Monitor multiparamétrico com capnografia", "unidade": "UN", "quantidade": "2",
              "valor_unitario_estimado": "7200"}]
    r = solicitante.post(f"/api/v1/solicitacoes/{sid}/acoes/reenviar", data={
        "versao": str(d["solicitacao"]["versao"]), "texto": "Especificação detalhada.", "itens": json.dumps(novos),
        "remover_anexos": d["anexos"][0]["id"],
        "arquivos": [(io.BytesIO(b"\x89PNG\r\n\x1a\n foto do orcamento"), "foto-orcamento.png")]})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d["solicitacao"]["status"] == "aguardando_gestor" and d["solicitacao"]["rodada"] == 2
    assert len(d["itens"]) == 1 and Decimal(str(d["solicitacao"]["valor_estimado"])) == Decimal("14400.00")
    ativos = [a for a in d["anexos"] if not a["removido_em"]]
    assert [a["nome_original"] for a in ativos] == ["foto-orcamento.png"]

    # Conflito de versão (edição concorrente)
    assert acao(gestor, sid, "aprovar", versao=1).status_code == 409
    # Fora da devolução o conteúdo não pode ser alterado nem por SQL direto
    assert acao(gestor, sid, "aprovar", versao=d["solicitacao"]["versao"]).status_code == 200


def test_escolha_sem_minimo_exige_justificativa_e_pedido_acima_da_alcada(clientes):
    comprador, financeiro, diretoria = clientes["comprador"], clientes["financeiro"], clientes["diretoria"]
    d = ate_aprovada(clientes)
    sid = d["solicitacao"]["id"]
    d = acao(comprador, sid, "iniciar_cotacao", versao=d["solicitacao"]["versao"]).get_json()
    f1 = fornecedor(comprador, "11.222.333/0001-81", "MEDTEC EQUIPAMENTOS HOSPITALARES LTDA")
    # Preço de mercado acima do estimado: pedido ultrapassa a alçada sem ter passado pela Diretoria
    d = proposta(comprador, sid, f1, d["itens"], ["13000", "300"]).get_json()
    cot = d["cotacoes"][0]
    assert d["comparacao"]["abaixo_do_minimo"] is True
    r = acao(comprador, sid, "definir_fornecedor", versao=d["solicitacao"]["versao"], cotacao_id=cot["id"])
    assert r.status_code == 422 and "Justifique" in r.get_json()["erro"]["mensagem"]
    d = acao(comprador, sid, "definir_fornecedor", versao=d["solicitacao"]["versao"], cotacao_id=cot["id"],
             texto="Fornecedor exclusivo do modelo homologado pela engenharia clínica.").get_json()
    assert d["solicitacao"]["status"] == "aguardando_pedido"
    d = acao(comprador, sid, "emitir_pedido", versao=d["solicitacao"]["versao"]).get_json()
    pid = d["pedido_criado"]
    p = financeiro.get(f"/api/v1/pedidos/{pid}").get_json()
    assert p["pedido"]["exige_diretoria"] is True
    p = acao_pedido(financeiro, pid, "aprovar", versao=p["pedido"]["versao"]).get_json()
    assert p["pedido"]["status"] == "aguardando_diretoria"
    assert acao_pedido(financeiro, pid, "aprovar", versao=p["pedido"]["versao"]).status_code in (403, 422)
    p = acao_pedido(diretoria, pid, "aprovar", versao=p["pedido"]["versao"]).get_json()
    assert p["pedido"]["status"] == "aprovado"
    assert [a["nivel"] for a in p["aprovacoes"]] == ["financeiro", "diretoria"]


def test_reprovacao_financeira_reabre_a_cotacao(clientes):
    d, pid = ate_pedido(clientes)
    sid = d["solicitacao"]["id"]
    financeiro, comprador = clientes["financeiro"], clientes["comprador"]
    p = financeiro.get(f"/api/v1/pedidos/{pid}").get_json()
    assert acao_pedido(financeiro, pid, "reprovar", versao=p["pedido"]["versao"], texto="curto").status_code == 422
    p = acao_pedido(financeiro, pid, "reprovar", versao=p["pedido"]["versao"],
                    texto="Sem dotação orçamentária neste mês; renegociar prazo de pagamento.").get_json()
    assert p["pedido"]["status"] == "reprovado"
    d = comprador.get(f"/api/v1/solicitacoes/{sid}").get_json()
    assert d["solicitacao"]["status"] == "em_cotacao" and d["solicitacao"]["cotacao_vencedora_id"] is None
    assert not any(c["selecionada"] for c in d["cotacoes"])
    assert "definir_fornecedor" in d["acoes"]


def test_cancelamentos_e_permissoes(clientes):
    solicitante, comprador, admin, auditoria = (clientes["solicitante"], clientes["comprador"], clientes["admin"],
                                                clientes["auditoria"])
    d = criar_solicitacao(solicitante, com_anexo=False)
    sid = d["solicitacao"]["id"]
    assert acao(auditoria, sid, "cancelar", versao=d["solicitacao"]["versao"], texto="Auditoria é somente leitura").status_code == 403
    assert acao(solicitante, sid, "cancelar", versao=d["solicitacao"]["versao"], texto="curto").status_code == 422
    d = acao(solicitante, sid, "cancelar", versao=d["solicitacao"]["versao"],
             texto="Demanda atendida por remanejamento de estoque.").get_json()
    assert d["solicitacao"]["status"] == "cancelada"

    d, pid = ate_pedido(clientes)
    p = comprador.get(f"/api/v1/pedidos/{pid}").get_json()
    assert acao_pedido(clientes["recebimento"], pid, "cancelar", versao=p["pedido"]["versao"], texto="x" * 20).status_code == 403
    p = acao_pedido(admin, pid, "cancelar", versao=p["pedido"]["versao"], texto="Fornecedor comunicou falta de estoque.").get_json()
    assert p["pedido"]["status"] == "cancelado"
    assert comprador.get(f"/api/v1/solicitacoes/{d['solicitacao']['id']}").get_json()["solicitacao"]["status"] == "em_cotacao"

    # Criação é exclusiva de solicitantes e gestores
    for nome in ("comprador", "financeiro", "recebimento", "diretoria", "auditoria", "admin"):
        r = clientes[nome].post("/api/v1/solicitacoes", json={"tipo": "material", "titulo": "Teste de permissão",
                                                              "justificativa": "Justificativa longa o bastante.",
                                                              "itens": [{"descricao": "Item", "unidade": "UN", "quantidade": 1}]})
        assert r.status_code == 403, nome


def test_isolamento_rls_por_perfil_e_sql_direto(clientes, usuarios, url_banco):
    d = criar_solicitacao(clientes["solicitante"], com_anexo=False)
    sid = d["solicitacao"]["id"]
    assert clientes["solicitante_lab"].get(f"/api/v1/solicitacoes/{sid}").status_code == 404
    assert clientes["gestor_lab"].get(f"/api/v1/solicitacoes/{sid}").status_code == 404
    for nome in ("admin", "financeiro", "diretoria", "auditoria", "gestor"):
        assert clientes[nome].get(f"/api/v1/solicitacoes/{sid}").status_code == 200, nome
    assert clientes["auditoria"].get("/api/v1/auditoria").status_code == 200
    assert clientes["comprador"].get("/api/v1/auditoria").status_code == 403

    def como(usuario, sql, params=()):
        with psycopg.connect(url_banco) as conn:
            with conn.transaction():
                conn.execute("set local role rg_app")
                conn.execute("select set_config('app.user_id', %s, true)", (usuario["id"],))
                return conn.execute(sql, params)

    # Gestor de outro setor não altera (RLS: 0 linhas); gestor do setor não pula a assinatura
    assert como(usuarios["gestor_lab"], "update rg.solicitacoes set status = 'aprovada' where id = %s", (sid,)).rowcount == 0
    with pytest.raises(psycopg.Error, match="assinatura"):
        como(usuarios["gestor"], "update rg.solicitacoes set status = 'aprovada' where id = %s", (sid,))
    # Tabelas derivadas não aceitam escrita direta
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        como(usuarios["comprador"], "insert into rg.aprovacoes (solicitacao_id, nivel, decisao) values (%s, 'gestor', 'aprovado')",
             (sid,))
    # Auditoria não escreve em nada (RLS não expõe nenhuma linha para alteração)
    assert como(usuarios["auditoria"], "update rg.solicitacoes set titulo = 'alterado pela auditoria' where id = %s",
                (sid,)).rowcount == 0
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        como(usuarios["auditoria"], "insert into rg.fornecedores (razao_social, cnpj) values ('X', '11444777000161')")


def test_valores_nao_podem_ser_forjados(clientes, usuarios, url_banco):
    d, pid = ate_pedido(clientes)

    def como(usuario, sql, params=()):
        with psycopg.connect(url_banco) as conn:
            with conn.transaction():
                conn.execute("set local role rg_app")
                conn.execute("select set_config('app.user_id', %s, true)", (usuario["id"],))
                return conn.execute(sql, params)

    with pytest.raises(psycopg.Error, match="não podem ser alterados"):
        como(usuarios["comprador"], "update rg.pedidos set valor_total = 1 where id = %s", (pid,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        como(usuarios["comprador"], "update rg.pedido_itens set valor_unitario = 1 where pedido_id = %s", (pid,))
    with pytest.raises(psycopg.Error, match="Financeiro"):
        como(usuarios["comprador"], "update rg.pedidos set status = 'aprovado' where id = %s", (pid,))


def test_limites_de_documentos_e_tipos(clientes):
    solicitante = clientes["solicitante"]
    d = criar_solicitacao(solicitante)
    sid = d["solicitacao"]["id"]
    for i in range(4):
        r = solicitante.post(f"/api/v1/solicitacoes/{sid}/anexos",
                             data={"arquivos": [(io.BytesIO(pdf_orcamento()), f"orcamento-{i}.pdf")]})
        assert r.status_code == 201, r.get_json()
    r = solicitante.post(f"/api/v1/solicitacoes/{sid}/anexos",
                         data={"arquivos": [(io.BytesIO(pdf_orcamento()), "sexto.pdf")]})
    assert r.status_code == 422
    r = solicitante.post("/api/v1/solicitacoes", data={
        "tipo": "material", "titulo": "Compra de luvas", "justificativa": "Estoque abaixo do mínimo de segurança da CCIH.",
        "itens": '[{"descricao": "Luva", "unidade": "CX", "quantidade": 10}]',
        "arquivos": [(io.BytesIO(b"MZ\x90\x00binario"), "virus.pdf")]})
    assert r.status_code == 422
    r = solicitante.post("/api/v1/solicitacoes", json={"tipo": "material", "titulo": "Sem itens",
                                                       "justificativa": "Justificativa suficientemente longa."})
    assert r.status_code == 422 and "itens" in r.get_json()["erro"]["campos"]


def test_cadastro_pendente_aprovacao_e_bloqueio(app, clientes, url_banco):
    anonimo = Cliente(app)
    dados = {"nome": "Paula Pendente", "email": "paula.pendente@hrg.demo", "setor_codigo": "maternidade",
             "papel": "solicitante", "senha": "Maternidade#2026Rg", "consentimento": True, "telefone": "(51) 99999-8888"}
    assert anonimo.post("/api/v1/auth/cadastro", json=dados).status_code == 202
    assert anonimo.post("/api/v1/auth/cadastro", json=dados).status_code == 202  # sem enumeração
    r = anonimo.post("/api/v1/auth/login", json={"email": dados["email"], "senha": dados["senha"]})
    assert r.status_code == 403 and r.get_json()["erro"]["codigo"] == "conta_pendente"
    assert anonimo.post("/api/v1/auth/cadastro", json={**dados, "email": "x@hrg.demo", "papel": "admin"}).status_code == 422

    admin = clientes["admin"]
    alvo = next(u for u in admin.get("/api/v1/usuarios", query_string={"status": "pendente"}).get_json()["itens"]
                if u["email"] == dados["email"])
    r = admin.post(f"/api/v1/usuarios/{alvo['id']}/aprovar", json={"papel": "solicitante", "setor_codigo": "financeiro"})
    assert r.status_code == 422  # solicitante precisa de setor que abre solicitações
    r = admin.post(f"/api/v1/usuarios/{alvo['id']}/aprovar", json={"papel": "solicitante", "setor_codigo": "maternidade"})
    assert r.status_code == 200

    novo = Cliente(app, {"email": dados["email"], "senha": dados["senha"]})
    assert novo.get("/api/v1/auth/perfil").get_json()["telefone"] == "51999998888"
    with psycopg.connect(url_banco) as conn:
        cifrado = conn.execute("select telefone_cript from rg.usuarios where id = %s", (alvo["id"],)).fetchone()[0]
    assert cifrado and "9999" not in cifrado
    assert novo.post("/api/v1/auth/senha", json={"senha_atual": dados["senha"], "nova_senha": dados["senha"]}).status_code == 422
    assert novo.post("/api/v1/auth/senha", json={"senha_atual": dados["senha"],
                                                  "nova_senha": "NovaSenha#Segura2026"}).status_code == 200
    for _ in range(5):
        assert anonimo.post("/api/v1/auth/login", json={"email": dados["email"], "senha": "errada"}).status_code == 401
    assert anonimo.post("/api/v1/auth/login", json={"email": dados["email"],
                                                    "senha": "NovaSenha#Segura2026"}).status_code == 423


def test_csrf_e_sessao(app, clientes):
    gestor = clientes["gestor"]
    r = gestor.http.post("/api/v1/notificacoes/lidas", json={})
    assert r.status_code == 403 and r.get_json()["erro"]["codigo"] == "csrf"
    assert Cliente(app).get("/api/v1/solicitacoes").status_code == 401
    assert gestor.post("/api/v1/auth/logout").status_code == 200
    assert gestor.get("/api/v1/auth/me").status_code == 401


def test_admin_redefine_senha_e_troca_obrigatoria(app, clientes, url_banco):
    alvo = criar_usuario(url_banco, papel="comprador", setor="suprimentos")
    r = clientes["admin"].post(f"/api/v1/usuarios/{alvo['id']}/redefinir-senha")
    temporaria = r.get_json()["senha_temporaria"]
    c = Cliente(app, {"email": alvo["email"], "senha": temporaria})
    r = c.get("/api/v1/solicitacoes")
    assert r.status_code == 403 and r.get_json()["erro"]["codigo"] == "troca_senha_obrigatoria"
    assert c.post("/api/v1/auth/senha", json={"senha_atual": temporaria, "nova_senha": "Estoque#Forte2026x"}).status_code == 200
    assert c.get("/api/v1/solicitacoes").status_code == 200


def test_seguranca_cabecalhos_e_frontend(app):
    c = app.test_client()
    r = c.get("/api/v1/meta")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert "connect-src 'self'" in r.headers["Content-Security-Policy"]  # nenhum serviço externo
    assert r.headers["X-Frame-Options"] == "DENY" and r.headers["Cache-Control"] == "no-store"
    meta = r.get_json()
    assert len(meta["rotulos"]["papel"]) == 8
    assert meta["etapas"][0] == "Solicitação" and meta["etapas"][-1] == "Conclusão"
    assert c.get("/solicitacoes/qualquer").status_code == 200
    assert c.get("/api/v1/inexistente").status_code == 404
