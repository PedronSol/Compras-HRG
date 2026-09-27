"""Painel, alertas, catálogo, fornecedores, parâmetros, auditoria, tempo real, busca, LGPD e dados de demonstração."""
import json

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import acao, acao_pedido, ate_pedido, criar_solicitacao
from rg.servicos.tempo_real import Conexao, pode_ver


def test_painel_escopo_pendencias_e_relatorios(clientes):
    ate_pedido(clientes)
    admin, gestor_lab = clientes["admin"], clientes["gestor_lab"]
    p = admin.get("/api/v1/painel").get_json()
    assert p["kpis"]["pedidos"] >= 1 and p["kpis"]["valor_contratado"] > 0
    assert [f["etapa"] for f in p["funil"]] == ["aprovacao", "cotacao", "fornecedor", "pedido", "recebimento"]
    p_lab = gestor_lab.get("/api/v1/painel", query_string={"setor": "uti_adulto"}).get_json()
    assert p_lab["periodo"]["setor"] == "laboratorio"  # setor fica restrito ao próprio
    assert all(s["setor_codigo"] == "laboratorio" for s in p_lab["por_setor"])

    pend = clientes["financeiro"].get("/api/v1/painel/pendencias").get_json()
    assert pend["contadores"]["aprovacoes"] >= 1 and pend["pedidos"]
    assert clientes["financeiro"].get("/api/v1/aprovacoes/pendentes").get_json()["pedidos"]

    for url in ("/api/v1/painel/relatorio.pdf", "/api/v1/solicitacoes/relatorio.pdf"):
        r = admin.get(url)
        assert r.status_code == 200 and r.data.startswith(b"%PDF")
    for url in ("/api/v1/solicitacoes/exportar.csv", "/api/v1/pedidos/exportar.csv"):
        r = admin.get(url)
        assert r.status_code == 200 and r.data.startswith("﻿".encode())
    eventos = admin.get("/api/v1/auditoria", query_string={"operacao": "RELATORIO_GERADO"}).get_json()["itens"]
    codigo = eventos[0]["dados_depois"]["codigo_verificacao"]
    assert admin.get(f"/api/v1/auditoria/relatorios/{codigo}").get_json()["autentico"] is True
    assert admin.get("/api/v1/auditoria/relatorios/" + "0" * 64).get_json()["autentico"] is False


def test_alertas_de_prazo_e_entrega(clientes, url_banco):
    d = criar_solicitacao(clientes["solicitante"], com_anexo=False)
    sid = d["solicitacao"]["id"]
    with psycopg.connect(url_banco, autocommit=True) as conn:
        conn.execute("alter table rg.solicitacoes disable trigger solicitacoes_validar")
        conn.execute("update rg.solicitacoes set sla_prazo_limite = now() - interval '1 hour' where id = %s", (sid,))
        conn.execute("alter table rg.solicitacoes enable trigger solicitacoes_validar")
        with pytest.raises(psycopg.Error):
            conn.execute("select rg.processar_alertas()")  # exclusivo do agendador
        conn.execute("select set_config('app.contexto', 'sistema', false)")
        assert conn.execute("select rg.processar_alertas()").fetchone()[0] >= 1
        assert conn.execute("select rg.processar_alertas()").fetchone()[0] == 0  # não repete
    gestor = clientes["gestor"]
    assert gestor.get(f"/api/v1/solicitacoes/{sid}").get_json()["solicitacao"]["sla_situacao"] == "estourado"
    assert "Prazo de atendimento estourado" in [n["titulo"] for n in gestor.get("/api/v1/notificacoes").get_json()["itens"]]
    alertas = gestor.get("/api/v1/alertas").get_json()
    assert any(a["tipo"] == "sla" and a["gravidade"] == "critico" for a in alertas["itens"])


def test_catalogo_de_materiais_e_categorias(clientes):
    comprador, solicitante = clientes["comprador"], clientes["solicitante"]
    r = comprador.post("/api/v1/categorias", json={"nome": "Órteses e próteses", "cor": "#0E7C86"})
    assert r.status_code == 201
    cat = r.get_json()["id"]
    assert comprador.post("/api/v1/categorias", json={"nome": "órteses e próteses"}).status_code == 422
    r = comprador.post("/api/v1/materiais", json={"nome": "Placa de titânio 3,5 mm", "categoria_id": cat, "unidade": "UN",
                                                  "preco_referencia": "890,00"})
    assert r.status_code == 201 and r.get_json()["codigo"].startswith("MAT-")
    mid = r.get_json()["id"]
    assert solicitante.post("/api/v1/materiais", json={"nome": "Sem permissão", "categoria_id": cat, "unidade": "UN"}).status_code == 403
    assert clientes["auditoria"].patch(f"/api/v1/materiais/{mid}", json={"ativo": False}).status_code == 403
    # Solicitação com item do catálogo herda descrição e unidade
    d = criar_solicitacao(solicitante, com_anexo=False, itens=[{"material_id": mid, "quantidade": "3",
                                                                "valor_unitario_estimado": "890"}])
    assert d["itens"][0]["descricao"] == "Placa de titânio 3,5 mm" and d["itens"][0]["unidade"] == "UN"
    lista = solicitante.get("/api/v1/materiais", query_string={"q": "titânio"}).get_json()["itens"]
    assert lista[0]["solicitacoes"] == 1


def test_fornecedores_validacao_e_desempenho(clientes):
    comprador = clientes["comprador"]
    r = comprador.post("/api/v1/fornecedores", json={"razao_social": "CNPJ INVÁLIDO LTDA", "cnpj": "11.222.333/0001-82"})
    assert r.status_code == 422 and "cnpj" in r.get_json()["erro"]["campos"]
    assert clientes["solicitante"].post("/api/v1/fornecedores", json={"razao_social": "X LTDA",
                                                                      "cnpj": "11.444.777/0001-61"}).status_code == 403
    ate_pedido(clientes)
    lista = comprador.get("/api/v1/fornecedores", query_string={"ordem": "valor"}).get_json()["itens"]
    assert lista[0]["pedidos"] >= 1 and lista[0]["valor_contratado"] > 0
    detalhe = comprador.get(f"/api/v1/fornecedores/{lista[0]['id']}").get_json()
    assert detalhe["pedidos"] and detalhe["propostas"]
    # Perfis sem acesso a desempenho recebem apenas dados cadastrais
    resumo = clientes["solicitante"].get("/api/v1/fornecedores").get_json()["itens"][0]
    assert "valor_contratado" not in resumo and "email" not in resumo


def test_parametros_de_alcada_somente_admin(clientes):
    admin, comprador = clientes["admin"], clientes["comprador"]
    assert comprador.patch("/api/v1/configuracoes/alcada_diretoria", json={"valor": "1"}).status_code == 403
    r = admin.patch("/api/v1/configuracoes/alcada_diretoria", json={"valor": "10000"})
    assert r.status_code == 200
    try:
        d = criar_solicitacao(clientes["solicitante"], com_anexo=False)
        d = acao(clientes["gestor"], d["solicitacao"]["id"], "aprovar", versao=d["solicitacao"]["versao"]).get_json()
        assert d["solicitacao"]["status"] == "aguardando_diretoria"  # R$ 14.000 > nova alçada
    finally:
        admin.patch("/api/v1/configuracoes/alcada_diretoria", json={"valor": "25000"})
    assert admin.patch("/api/v1/configuracoes/minimo_cotacoes", json={"valor": "0"}).status_code == 422
    matriz = admin.get("/api/v1/permissoes").get_json()["matriz"]
    assert any(m["capacidade"] == "pedido.aprovar_financeiro" and m["perfis"] == ["financeiro"] for m in matriz)


def test_auditoria_registra_e_e_imutavel(clientes, url_banco):
    d = criar_solicitacao(clientes["solicitante"], com_anexo=False)
    sid = d["solicitacao"]["id"]
    for nome in ("admin", "auditoria"):
        eventos = clientes[nome].get("/api/v1/auditoria", query_string={"registro": sid}).get_json()["itens"]
        assert any(e["operacao"] == "INSERT" and e["tabela"] == "rg.solicitacoes" for e in eventos)
    assert clientes["gestor"].get("/api/v1/auditoria").status_code == 403
    with psycopg.connect(url_banco) as conn:
        with pytest.raises(psycopg.Error):
            conn.execute("delete from audit.eventos")
        conn.rollback()
        with pytest.raises(psycopg.Error):
            conn.execute("update rg.assinaturas set ip = '0.0.0.0'")
        conn.rollback()
        with pytest.raises(psycopg.Error):
            conn.execute("delete from rg.aprovacoes")


def test_roteamento_de_eventos_em_tempo_real():
    def c(papel, setor="uti_adulto", uid="u"):
        return Conexao(None, {"id": uid, "papel": papel, "setor_codigo": setor}, "t")
    evento = {"tabela": "solicitacoes", "setor": "uti_adulto", "status": "aguardando_gestor", "aprovada": False}
    assert pode_ver(c("admin"), evento) and pode_ver(c("gestor"), evento) and pode_ver(c("auditoria"), evento)
    assert not pode_ver(c("comprador", "suprimentos"), evento) and not pode_ver(c("gestor", "laboratorio"), evento)
    assert not pode_ver(c("recebimento", "suprimentos"), evento)
    evento.update(status="em_pedido", aprovada=True)
    assert pode_ver(c("comprador", "suprimentos"), evento) and pode_ver(c("recebimento", "suprimentos"), evento)
    notif = {"tabela": "notificacoes", "destinatario": "g"}
    assert pode_ver(c("gestor", uid="g"), notif) and not pode_ver(c("admin"), notif)


def test_busca_global_respeita_escopo(clientes):
    d = criar_solicitacao(clientes["solicitante"], com_anexo=False, titulo="Ventilador pulmonar de transporte")
    assert clientes["gestor"].get("/api/v1/busca", query_string={"q": "Ventilador"}).get_json()["solicitacoes"]
    assert not clientes["gestor_lab"].get("/api/v1/busca", query_string={"q": d["solicitacao"]["codigo"]}).get_json()["solicitacoes"]
    assert clientes["solicitante"].get("/api/v1/busca", query_string={"q": "LTDA"}).get_json()["fornecedores"] == []


def test_lgpd_exportacao_e_anonimizacao(clientes, usuarios):
    admin = clientes["admin"]
    r = clientes["gestor"].get("/api/v1/auth/meus-dados")
    assert r.status_code == 200 and r.get_json()["titular"]["email"] == usuarios["gestor"]["email"]
    alvo = usuarios["gestor_lab"]["id"]
    assert admin.post(f"/api/v1/usuarios/{alvo}/anonimizar").status_code == 422
    assert admin.patch(f"/api/v1/usuarios/{alvo}", json={"status": "suspenso"}).status_code == 200
    assert clientes["gestor_lab"].get("/api/v1/auth/me").status_code == 401
    assert admin.post(f"/api/v1/usuarios/{alvo}/anonimizar").status_code == 200
    lista = admin.get("/api/v1/usuarios", query_string={"q": "anonimizado"}).get_json()["itens"]
    assert any(u["id"] == alvo and u["nome"] == "Titular anonimizado" for u in lista)
    assert admin.patch(f"/api/v1/usuarios/{usuarios['admin']['id']}", json={"papel": "gestor"}).status_code == 422
    assert clientes["auditoria"].patch(f"/api/v1/usuarios/{alvo}", json={"nome": "Tentativa"}).status_code == 403


def test_dados_de_demonstracao_sao_coerentes_com_as_regras(app, url_banco):
    """Carrega a demonstração e opera sobre ela pelos fluxos reais (triggers e RLS ativos)."""
    from conftest import Cliente
    from rg.contas_teste import SENHA_TESTE
    from rg.demo import Semeador, TABELAS
    from rg.seguranca import senhas
    with psycopg.connect(url_banco, row_factory=dict_row) as conn:
        with conn.transaction():
            cur = conn.cursor()
            cur.execute("select count(*) as n from rg.usuarios where email like '%%@hrg.demo'")
            if cur.fetchone()["n"] < 8:
                for t in TABELAS:
                    cur.execute(f"alter table {t} disable trigger user")
                Semeador(cur, app.config["SIGNATURE_SECRET"], senhas.gerar_hash(SENHA_TESTE), "2026.1").executar()
                for t in TABELAS:
                    cur.execute(f"alter table {t} enable trigger user")
    perfil = lambda p: Cliente(app, {"email": f"{p}@hrg.demo", "senha": SENHA_TESTE})  # noqa: E731

    gestor = perfil("gestor")
    pend = gestor.get("/api/v1/aprovacoes/pendentes").get_json()["solicitacoes"]
    assert pend, "o gestor de demonstração deve ter aprovações pendentes"
    alvo = pend[-1]
    d = acao(gestor, alvo["id"], "aprovar", versao=gestor.get(f"/api/v1/solicitacoes/{alvo['id']}").get_json()["solicitacao"]["versao"])
    assert d.status_code == 200, d.get_json()

    financeiro = perfil("financeiro")
    pedido = financeiro.get("/api/v1/aprovacoes/pendentes").get_json()["pedidos"][0]
    p = financeiro.get(f"/api/v1/pedidos/{pedido['id']}").get_json()
    assert acao_pedido(financeiro, pedido["id"], "aprovar", versao=p["pedido"]["versao"]).status_code == 200

    recebimento = perfil("recebimento")
    enviados = recebimento.get("/api/v1/pedidos", query_string={"fila": 1}).get_json()["itens"]
    p = recebimento.get(f"/api/v1/pedidos/{enviados[0]['id']}").get_json()
    itens = [{"pedido_item_id": i["id"], "quantidade_recebida": str(i["saldo"]), "quantidade_aceita": str(i["saldo"])}
             for i in p["itens"] if float(i["saldo"]) > 0]
    r = recebimento.post(f"/api/v1/pedidos/{p['pedido']['id']}/recebimentos", json={"nota_fiscal": "99001", "itens": itens})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["pedido"]["status"] == "entregue"

    comprador = perfil("comprador")
    em_cotacao = comprador.get("/api/v1/solicitacoes", query_string={"status": "em_cotacao"}).get_json()["itens"]
    assert em_cotacao and all(s["status"] == "em_cotacao" for s in em_cotacao)

    auditor = perfil("auditoria")
    d = auditor.get("/api/v1/solicitacoes", query_string={"status": "concluida"}).get_json()["itens"][0]
    det = auditor.get(f"/api/v1/solicitacoes/{d['id']}").get_json()
    for a in det["assinaturas"]:
        assert auditor.get(f"/api/v1/assinaturas/{a['id']}/verificar").get_json()["registro_integro"] is True
    assert json.dumps(det)  # serializável
