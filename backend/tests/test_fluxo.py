"""Workflow completo Gestor → Administração → Compras, assinaturas, OCR, histórico e notificações."""
import io

import psycopg
import pytest

from conftest import Cliente, criar_solicitacao, criar_usuario, pdf_orcamento


def _acao(cliente, sid, acao, **dados):
    return cliente.post(f"/api/v1/solicitacoes/{sid}/acoes/{acao}", json=dados)


def _fornecedor(cliente, cnpj="11.222.333/0001-81", razao="MEDTEC EQUIPAMENTOS HOSPITALARES LTDA"):
    r = cliente.post("/api/v1/fornecedores", json={"razao_social": razao, "cnpj": cnpj})
    assert r.status_code in (201, 422), r.get_json()
    if r.status_code == 422:
        lista = cliente.get("/api/v1/fornecedores", query_string={"q": cnpj}).get_json()["itens"]
        return lista[0]["id"]
    return r.get_json()["id"]


def test_fluxo_completo_com_assinaturas(clientes, usuarios):
    gestor, admin, compras = clientes["gestor"], clientes["admin"], clientes["compras"]

    d = criar_solicitacao(gestor)
    s = d["solicitacao"]
    sid = s["id"]
    assert s["status"] == "aguardando_adm"
    assert s["codigo"].startswith("SOL-")
    assert s["sla_situacao"] == "dentro_prazo"
    assert len(d["assinaturas"]) == 1 and d["assinaturas"][0]["acao"] == "submissao"
    assert d["acoes"] == ["gestor_cancelar"]

    # OCR executado (modo síncrono nos testes) sobre o PDF anexado
    anexo = d["anexos"][0]
    assert anexo["ocr_status"] == "concluido", anexo
    assert anexo["dados_ocr"]["cnpj_emitente"]["valor"] == "11.222.333/0001-81"
    assert anexo["dados_ocr"]["valor_total"]["valor"] == "12450.90"

    # Compras ainda não enxerga (RLS)
    assert compras.get(f"/api/v1/solicitacoes/{sid}").status_code == 404
    # Gestor não aprova
    assert _acao(gestor, sid, "adm_aprovar", versao=s["versao"]).status_code == 403

    # Administração aprova com assinatura
    r = _acao(admin, sid, "adm_aprovar", versao=s["versao"], texto="Mérito técnico validado pela diretoria.")
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d["solicitacao"]["status"] == "aprovado_adm"
    versao = d["solicitacao"]["versao"]

    # Após liberação, a Administração não altera mais
    r = _acao(admin, sid, "adm_urgencia", versao=versao, urgencia="imediato", texto="Tentativa tardia de alteração")
    assert r.status_code == 422

    # Compras inicia cotação, cadastra fornecedores e cotações
    r = _acao(compras, sid, "compras_iniciar", versao=versao)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["solicitacao"]["status"] == "em_cotacao"
    f1 = _fornecedor(compras)
    f2 = _fornecedor(compras, cnpj="12.ABC.345/01DE-35", razao="BIOMED SERVICOS LTDA")
    r = compras.post(f"/api/v1/solicitacoes/{sid}/cotacoes",
                     json={"fornecedor_id": f1, "valor": "12450.90", "prazo_entrega_dias": 15,
                           "condicoes_pagamento": "30/60 dias", "anexo_id": anexo["id"]})
    assert r.status_code == 201, r.get_json()
    r = compras.post(f"/api/v1/solicitacoes/{sid}/cotacoes",
                     json={"fornecedor_id": f2, "valor": "11990,00", "prazo_entrega_dias": 20})
    assert r.status_code == 201, r.get_json()
    d = r.get_json()
    vencedora = next(c for c in d["cotacoes"] if c["fornecedor_id"] == f2)

    # Gestor não pode lançar cotação
    assert gestor.post(f"/api/v1/solicitacoes/{sid}/cotacoes",
                       json={"fornecedor_id": f1, "valor": "1", "prazo_entrega_dias": 1}).status_code == 403

    r = _acao(compras, sid, "compras_homologar", versao=d["solicitacao"]["versao"], cotacao_id=vencedora["id"],
              texto="Menor preço com prazo compatível.")
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    s = d["solicitacao"]
    assert s["status"] == "aprovado"
    assert s["valor_final_aprovado"] == 11990.0
    assert s["sla_situacao"] == "cumprido"
    assert [a["acao"] for a in d["assinaturas"]] == ["submissao", "aprovacao_adm", "homologacao"]
    acoes_hist = [(h["status_de"], h["status_para"]) for h in d["historico"]]
    assert (None, "aguardando_adm") in acoes_hist
    assert ("em_cotacao", "aprovado") in acoes_hist
    assert d["acoes"] == []

    # Verificação criptográfica de todas as assinaturas
    for a in d["assinaturas"]:
        v = admin.get(f"/api/v1/assinaturas/{a['id']}/verificar").get_json()
        assert v["registro_integro"] is True
    assert admin.get(f"/api/v1/assinaturas/{d['assinaturas'][-1]['id']}/verificar").get_json()[
        "conteudo_inalterado_desde_assinatura"] is True

    # Encerrada: nada mais pode ser alterado
    assert _acao(compras, sid, "compras_rejeitar", texto="Tentativa após homologação").status_code == 422

    # Notificações geradas para o gestor
    notif = gestor.get("/api/v1/notificacoes").get_json()
    titulos = [n["titulo"] for n in notif["itens"]]
    assert "Solicitação homologada" in titulos
    assert "Solicitação aprovada pela Administração" in titulos

    # Dossiê PDF com assinaturas
    r = gestor.get(f"/api/v1/solicitacoes/{sid}/dossie.pdf")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_nova_cotacao_reenvio_e_limite_de_anexos(clientes):
    gestor, admin = clientes["gestor"], clientes["admin"]
    d = criar_solicitacao(gestor)
    sid = d["solicitacao"]["id"]

    r = _acao(admin, sid, "adm_nova_cotacao", versao=d["solicitacao"]["versao"], texto="curto")
    assert r.status_code == 422
    r = _acao(admin, sid, "adm_nova_cotacao", versao=d["solicitacao"]["versao"],
              texto="Apresentar ao menos dois orçamentos de fornecedores homologados.")
    assert r.status_code == 200
    d = r.get_json()
    assert d["solicitacao"]["status"] == "necessita_nova_cotacao"
    assert d["acoes"] == ["adm_urgencia"]  # Administração ainda pode ajustar a urgência

    g = gestor.get(f"/api/v1/solicitacoes/{sid}").get_json()
    assert set(g["acoes"]) == {"gestor_reenviar", "gestor_cancelar"}

    arquivos = [(io.BytesIO(pdf_orcamento()), f"orc{i}.pdf") for i in range(3)]
    r = gestor.post(f"/api/v1/solicitacoes/{sid}/acoes/gestor_reenviar",
                    data={"versao": str(g["solicitacao"]["versao"]), "arquivos": arquivos})
    assert r.status_code == 422  # 1 ativo + 3 novos > 3

    arquivos = [(io.BytesIO(pdf_orcamento()), f"orc{i}.pdf") for i in range(3)]
    r = gestor.post(f"/api/v1/solicitacoes/{sid}/acoes/gestor_reenviar",
                    data={"versao": str(g["solicitacao"]["versao"]), "arquivos": arquivos,
                          "remover_anexos": g["anexos"][0]["id"], "texto": "Incluídos três orçamentos."})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d["solicitacao"]["status"] == "aguardando_adm"
    assert d["solicitacao"]["rodada_cotacao"] == 2
    assert len([a for a in d["anexos"] if not a["removido_em"]]) == 3
    assert [a["acao"] for a in d["assinaturas"]] == ["submissao", "nova_cotacao_adm", "reenvio"]


def test_alteracao_de_urgencia_recalcula_sla(clientes):
    gestor, admin = clientes["gestor"], clientes["admin"]
    d = criar_solicitacao(gestor, com_anexo=False, urgencia="normal")
    s = d["solicitacao"]
    r = _acao(admin, s["id"], "adm_urgencia", versao=s["versao"], urgencia="imediato", texto="")
    assert r.status_code == 422
    r = _acao(admin, s["id"], "adm_urgencia", versao=s["versao"], urgencia="imediato",
              texto="Risco assistencial confirmado pela coordenação médica.")
    assert r.status_code == 200, r.get_json()
    novo = r.get_json()["solicitacao"]
    assert novo["urgencia"] == "imediato"
    from datetime import datetime
    delta = datetime.fromisoformat(novo["sla_prazo_limite"]) - datetime.fromisoformat(novo["criado_em"])
    assert delta.days == 3
    # Conflito de versão (edição concorrente)
    r = _acao(admin, s["id"], "adm_aprovar", versao=s["versao"])
    assert r.status_code == 409


def test_isolamento_por_setor_e_papel(clientes, usuarios, url_banco):
    gestor, gestor_lab, compras, admin = (clientes[k] for k in ("gestor", "gestor_lab", "compras", "admin"))
    d = criar_solicitacao(gestor, com_anexo=False)
    sid = d["solicitacao"]["id"]

    assert gestor_lab.get(f"/api/v1/solicitacoes/{sid}").status_code == 404
    lista = gestor_lab.get("/api/v1/solicitacoes").get_json()
    assert all(i["setor_codigo"] == "laboratorio" for i in lista["itens"])
    assert compras.get(f"/api/v1/solicitacoes/{sid}").status_code == 404
    assert admin.get(f"/api/v1/solicitacoes/{sid}").status_code == 200
    assert compras.post("/api/v1/solicitacoes", data={"tipo": "compra"}).status_code == 403

    # Mesmo com SQL direto no papel rg_app, o banco impede a aprovação pelo gestor
    with psycopg.connect(url_banco) as conn:
        conn.execute("set role rg_app")
        conn.execute("select set_config('app.user_id', %s, false)", (usuarios["gestor"]["id"],))
        with pytest.raises(psycopg.Error):
            conn.execute("update rg.solicitacoes set status = 'aprovado_adm' where id = %s", (sid,))
        conn.rollback()
        # gestor de outro setor não enxerga nem via SQL
        conn.execute("set role rg_app")
        conn.execute("select set_config('app.user_id', %s, false)", (usuarios["gestor_lab"]["id"],))
        assert conn.execute("select count(*) from rg.solicitacoes where id = %s", (sid,)).fetchone()[0] == 0
        # auditoria é somente leitura para não-admin
        assert conn.execute("select count(*) from audit.eventos").fetchone()[0] == 0


def test_justificativa_minima_e_limite_de_arquivos(clientes):
    gestor = clientes["gestor"]
    r = gestor.post("/api/v1/solicitacoes", data={"tipo": "compra", "titulo": "Compra de luvas",
                                                   "descricao": "Luvas de procedimento tamanho M.",
                                                   "justificativa": "curta demais"})
    assert r.status_code == 422
    assert "justificativa" in r.get_json()["erro"]["campos"]
    arquivos = [(io.BytesIO(pdf_orcamento()), f"o{i}.pdf") for i in range(4)]
    r = gestor.post("/api/v1/solicitacoes", data={
        "tipo": "compra", "titulo": "Compra de luvas", "descricao": "Luvas de procedimento tamanho M.",
        "justificativa": "Estoque abaixo do mínimo de segurança definido pela CCIH.", "arquivos": arquivos})
    assert r.status_code == 422
    r = gestor.post("/api/v1/solicitacoes", data={
        "tipo": "compra", "titulo": "Compra de luvas", "descricao": "Luvas de procedimento tamanho M.",
        "justificativa": "Estoque abaixo do mínimo de segurança definido pela CCIH.",
        "arquivos": [(io.BytesIO(b"MZ\x90\x00binario"), "virus.pdf")]})
    assert r.status_code == 422


def test_cadastro_pendente_aprovacao_e_bloqueio(app, clientes, url_banco):
    anonimo = Cliente(app)
    dados = {"nome": "Paula Pendente", "email": "paula.pendente@rghospital.com.br", "setor_codigo": "maternidade",
             "papel": "gestor", "senha": "Maternidade#2026Rg", "consentimento": True, "telefone": "(51) 99999-8888"}
    r = anonimo.post("/api/v1/auth/cadastro", json=dados)
    assert r.status_code == 202
    # Duplicado recebe a mesma resposta (sem enumeração)
    assert anonimo.post("/api/v1/auth/cadastro", json=dados).status_code == 202

    r = anonimo.post("/api/v1/auth/login", json={"email": dados["email"], "senha": dados["senha"]})
    assert r.status_code == 403 and r.get_json()["erro"]["codigo"] == "conta_pendente"

    admin = clientes["admin"]
    pendentes = admin.get("/api/v1/usuarios", query_string={"status": "pendente"}).get_json()["itens"]
    alvo = next(u for u in pendentes if u["email"] == dados["email"])
    assert any(n["titulo"] == "Novo cadastro aguardando aprovação"
               for n in admin.get("/api/v1/notificacoes").get_json()["itens"])
    r = admin.post(f"/api/v1/usuarios/{alvo['id']}/aprovar", json={"papel": "gestor", "setor_codigo": "administracao"})
    assert r.status_code == 422  # gestor precisa de setor operacional
    r = admin.post(f"/api/v1/usuarios/{alvo['id']}/aprovar", json={"papel": "gestor", "setor_codigo": "maternidade"})
    assert r.status_code == 200

    novo = Cliente(app, {"email": dados["email"], "senha": dados["senha"]})
    perfil = novo.get("/api/v1/auth/perfil").get_json()
    assert perfil["telefone"] == "51999998888"  # decifrado apenas para o titular

    # telefone é armazenado cifrado
    with psycopg.connect(url_banco) as conn:
        cifrado = conn.execute("select telefone_cript from rg.usuarios where id = %s", (alvo["id"],)).fetchone()[0]
    assert cifrado and "9999" not in cifrado

    # Troca de senha: histórico impede reutilização
    r = novo.post("/api/v1/auth/senha", json={"senha_atual": dados["senha"], "nova_senha": dados["senha"]})
    assert r.status_code == 422
    r = novo.post("/api/v1/auth/senha", json={"senha_atual": dados["senha"], "nova_senha": "NovaSenha#Segura2026"})
    assert r.status_code == 200, r.get_json()

    # Bloqueio após 5 tentativas incorretas
    for _ in range(5):
        r = anonimo.post("/api/v1/auth/login", json={"email": dados["email"], "senha": "errada"})
        assert r.status_code == 401
    r = anonimo.post("/api/v1/auth/login", json={"email": dados["email"], "senha": "NovaSenha#Segura2026"})
    assert r.status_code == 423


def test_csrf_e_sessao(app, clientes):
    gestor = clientes["gestor"]
    r = gestor.http.post("/api/v1/notificacoes/lidas", json={})
    assert r.status_code == 403 and r.get_json()["erro"]["codigo"] == "csrf"
    anonimo = Cliente(app)
    assert anonimo.get("/api/v1/solicitacoes").status_code == 401
    r = gestor.post("/api/v1/auth/logout")
    assert r.status_code == 200
    assert gestor.get("/api/v1/auth/me").status_code == 401


def test_admin_redefine_senha_e_troca_obrigatoria(app, clientes, url_banco):
    alvo = criar_usuario(url_banco, papel="compras", setor="suprimentos")
    r = clientes["admin"].post(f"/api/v1/usuarios/{alvo['id']}/redefinir-senha")
    assert r.status_code == 200
    temporaria = r.get_json()["senha_temporaria"]
    c = Cliente(app, {"email": alvo["email"], "senha": temporaria})
    r = c.get("/api/v1/solicitacoes")
    assert r.status_code == 403 and r.get_json()["erro"]["codigo"] == "troca_senha_obrigatoria"
    assert c.post("/api/v1/auth/senha", json={"senha_atual": temporaria,
                                              "nova_senha": "Estoque#Forte2026x"}).status_code == 200
    assert c.get("/api/v1/solicitacoes").status_code == 200


def test_seguranca_cabecalhos_e_frontend(app):
    c = app.test_client()
    r = c.get("/api/v1/meta")
    assert r.status_code == 200
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"
    meta = r.get_json()
    assert meta["sla_dias"] == {"imediato": 3, "urgente": 7, "normal": 14}
    assert len([s for s in meta["setores"] if s["operacional"]]) == 10
    # SPA: rotas do frontend retornam o index
    assert c.get("/solicitacoes/qualquer").status_code == 200
    assert c.get("/api/v1/inexistente").status_code == 404
