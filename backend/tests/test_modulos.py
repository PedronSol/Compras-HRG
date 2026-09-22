"""Serviços programados, painel, relatórios, auditoria, SLA e tempo real."""
from datetime import date, timedelta

import psycopg
import pytest

from conftest import criar_solicitacao
from rg.servicos.tempo_real import Conexao, pode_ver


def _servico(cliente, **extra):
    dados = {"titulo": "Calibração de bombas de infusão", "setor_codigo": "uti_adulto", "categoria": "calibracao",
             "data_programada": date.today().isoformat(), "hora_inicio": "08:00", "hora_termino": "10:30",
             "responsavel_executor": "Eng. Marcos Lima", "empresa_terceirizada": "BioCal Serviços",
             "periodicidade": "mensal", "local": "UTI Adulto — Leitos 1 a 10"}
    dados.update(extra)
    return cliente.post("/api/v1/servicos", json=dados)


def test_servicos_programados_ciclo_e_recorrencia(clientes):
    gestor, gestor_lab, compras, admin = (clientes[k] for k in ("gestor", "gestor_lab", "compras", "admin"))
    assert _servico(gestor, hora_termino="07:00").status_code == 422
    assert _servico(gestor, setor_codigo="laboratorio").status_code == 422
    assert _servico(compras).status_code == 403
    r = _servico(gestor)
    assert r.status_code == 201, r.get_json()
    s = r.get_json()
    assert s["codigo"].startswith("SRV-") and s["situacao"] == "agendado"

    assert gestor_lab.get(f"/api/v1/servicos/{s['id']}").status_code == 404
    assert compras.get(f"/api/v1/servicos/{s['id']}").status_code == 200  # leitura

    assert gestor.post(f"/api/v1/servicos/{s['id']}/iniciar").status_code == 200
    r = gestor.post(f"/api/v1/servicos/{s['id']}/concluir", json={"observacoes": "Calibradas 10 bombas, todas conformes."})
    assert r.status_code == 200 and r.get_json()["situacao"] == "concluido"
    assert gestor.post(f"/api/v1/servicos/{s['id']}/cancelar", json={"motivo": "teste inválido"}).status_code == 422

    inicio = date.today().isoformat()
    fim = (date.today() + timedelta(days=40)).isoformat()
    itens = admin.get("/api/v1/servicos", query_string={"inicio": inicio, "fim": fim, "q": "bombas"}).get_json()["itens"]
    proxima = [i for i in itens if i["situacao"] == "agendado" and i["titulo"] == s["titulo"]]
    assert proxima, "a próxima ocorrência mensal deve ser gerada"

    r = admin.get("/api/v1/servicos/relatorio.pdf", query_string={"inicio": inicio, "fim": fim})
    assert r.status_code == 200 and r.data.startswith(b"%PDF")


def test_painel_escopo_e_relatorio_executivo(clientes):
    gestor, gestor_lab, admin = clientes["gestor"], clientes["gestor_lab"], clientes["admin"]
    criar_solicitacao(gestor, com_anexo=False)
    p_admin = admin.get("/api/v1/painel").get_json()
    p_lab = gestor_lab.get("/api/v1/painel", query_string={"setor": "uti_adulto"}).get_json()
    assert p_admin["kpis"]["total"] >= 1
    assert all(s["setor_codigo"] == "laboratorio" for s in p_lab["por_setor"])  # gestor fica no próprio setor
    assert p_lab["periodo"]["setor"] == "laboratorio"

    r = admin.get("/api/v1/painel/relatorio.pdf")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    r = admin.get("/api/v1/solicitacoes/relatorio.pdf", query_string={"status": "aguardando_adm"})
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    r = admin.get("/api/v1/solicitacoes/exportar.csv")
    assert r.status_code == 200 and r.data.startswith("﻿".encode())

    # Código de verificação do relatório registrado na auditoria
    eventos = admin.get("/api/v1/auditoria", query_string={"operacao": "RELATORIO_GERADO"}).get_json()["itens"]
    codigo = eventos[0]["dados_depois"]["codigo_verificacao"]
    assert admin.get(f"/api/v1/auditoria/relatorios/{codigo}").get_json()["autentico"] is True
    assert admin.get("/api/v1/auditoria/relatorios/" + "0" * 64).get_json()["autentico"] is False


def test_auditoria_registra_e_e_imutavel(clientes, url_banco):
    gestor, admin = clientes["gestor"], clientes["admin"]
    d = criar_solicitacao(gestor, com_anexo=False)
    sid = d["solicitacao"]["id"]
    eventos = admin.get("/api/v1/auditoria", query_string={"registro": sid}).get_json()["itens"]
    assert any(e["operacao"] == "INSERT" and e["tabela"] == "rg.solicitacoes" for e in eventos)
    assert gestor.get("/api/v1/auditoria").status_code == 403
    with psycopg.connect(url_banco) as conn:
        with pytest.raises(psycopg.Error):
            conn.execute("delete from audit.eventos")
        conn.rollback()
        with pytest.raises(psycopg.Error):
            conn.execute("update rg.assinaturas set ip = '0.0.0.0'")


def test_alertas_de_sla(clientes, url_banco):
    gestor, admin = clientes["gestor"], clientes["admin"]
    d = criar_solicitacao(gestor, com_anexo=False)
    sid = d["solicitacao"]["id"]
    with psycopg.connect(url_banco, autocommit=True) as conn:
        conn.execute("alter table rg.solicitacoes disable trigger solicitacoes_validar")
        conn.execute("update rg.solicitacoes set sla_prazo_limite = now() - interval '1 hour' where id = %s", (sid,))
        conn.execute("alter table rg.solicitacoes enable trigger solicitacoes_validar")
        conn.execute("select set_config('app.contexto', 'sistema', false)")
        assert conn.execute("select rg.processar_alertas_sla()").fetchone()[0] >= 1
        assert conn.execute("select rg.processar_alertas_sla()").fetchone()[0] == 0  # não repete
    s = admin.get(f"/api/v1/solicitacoes/{sid}").get_json()["solicitacao"]
    assert s["sla_situacao"] == "estourado"
    titulos = [n["titulo"] for n in admin.get("/api/v1/notificacoes").get_json()["itens"]]
    assert "SLA estourado" in titulos
    assert admin.get("/api/v1/solicitacoes", query_string={"sla": "estourado"}).get_json()["total"] >= 1


def test_roteamento_de_eventos_em_tempo_real():
    admin = Conexao(None, {"id": "a", "papel": "admin", "setor_codigo": "administracao"}, "t")
    gestor = Conexao(None, {"id": "g", "papel": "gestor", "setor_codigo": "uti_adulto"}, "t")
    compras = Conexao(None, {"id": "c", "papel": "compras", "setor_codigo": "suprimentos"}, "t")
    evento = {"tabela": "solicitacoes", "setor": "uti_adulto", "status": "aguardando_adm"}
    assert pode_ver(admin, evento) and pode_ver(gestor, evento) and not pode_ver(compras, evento)
    evento["status"] = "em_cotacao"
    assert pode_ver(compras, evento)
    evento["setor"] = "laboratorio"
    assert not pode_ver(gestor, evento)
    notif = {"tabela": "notificacoes", "destinatario": "g"}
    assert pode_ver(gestor, notif) and not pode_ver(admin, notif)


def test_busca_global_respeita_escopo(clientes):
    gestor, gestor_lab = clientes["gestor"], clientes["gestor_lab"]
    d = criar_solicitacao(gestor, com_anexo=False, titulo="Ventilador pulmonar de transporte")
    assert gestor.get("/api/v1/busca", query_string={"q": "Ventilador"}).get_json()["solicitacoes"]
    codigo = d["solicitacao"]["codigo"]
    assert not gestor_lab.get("/api/v1/busca", query_string={"q": codigo}).get_json()["solicitacoes"]


def test_lgpd_exportacao_e_anonimizacao(app, clientes, usuarios):
    gestor, admin = clientes["gestor"], clientes["admin"]
    r = gestor.get("/api/v1/auth/meus-dados")
    assert r.status_code == 200 and r.get_json()["titular"]["email"] == usuarios["gestor"]["email"]
    alvo = usuarios["gestor_lab"]["id"]
    assert admin.post(f"/api/v1/usuarios/{alvo}/anonimizar").status_code == 422  # precisa estar suspenso
    assert admin.patch(f"/api/v1/usuarios/{alvo}", json={"status": "suspenso"}).status_code == 200
    assert clientes["gestor_lab"].get("/api/v1/auth/me").status_code == 401  # sessão revogada
    assert admin.post(f"/api/v1/usuarios/{alvo}/anonimizar").status_code == 200
    lista = admin.get("/api/v1/usuarios", query_string={"q": "anonimizado"}).get_json()["itens"]
    assert any(u["id"] == alvo and u["nome"] == "Titular anonimizado" for u in lista)
    # Administrador não altera o próprio papel
    assert admin.patch(f"/api/v1/usuarios/{usuarios['admin']['id']}", json={"papel": "gestor"}).status_code == 422
