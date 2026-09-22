"""Painel executivo (KPIs, SLAs, custos, setores) e exportação em PDF."""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..seguranca.sessao import registrar_evento, requer_login, tx
from ..servicos import pdf
from ..servicos.painel import painel as montar_painel
from ..validacao import Campo, validar
from ._util import periodo, resposta_pdf

bp = Blueprint("painel", __name__)


def _parametros():
    inicio, fim = periodo(180)
    setor = validar(request.args.to_dict(), [Campo("setor", "texto", max_len=40)]).get("setor")
    if g.usuario["papel"] == "gestor":
        setor = g.usuario["setor_codigo"]
    return inicio, fim, setor


@bp.get("/painel")
@requer_login
def painel():
    inicio, fim, setor = _parametros()
    with tx() as cur:
        dados = montar_painel(cur, inicio, fim, setor, current_app.config["TIMEZONE"])
    return jsonify(dados)


@bp.get("/painel/relatorio.pdf")
@requer_login
def relatorio():
    inicio, fim, setor = _parametros()
    with tx() as cur:
        dados = montar_painel(cur, inicio, fim, setor, current_app.config["TIMEZONE"])
        nome_setor = None
        if setor:
            cur.execute("select nome from rg.setores where codigo = %s", (setor,))
            linha = cur.fetchone()
            nome_setor = linha["nome"] if linha else setor
        filtros = f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} · Setor: {nome_setor or 'todos os setores acessíveis'}"
        conteudo, codigo = pdf.relatorio_executivo(dados, filtros, autor=g.usuario["nome"],
                                                   instituicao=current_app.config["INSTITUICAO"],
                                                   tz=current_app.config["TIMEZONE"])
        registrar_evento(cur, "RELATORIO_GERADO", "relatorios", "executivo",
                         {"codigo_verificacao": codigo, "filtros": filtros})
    return resposta_pdf(conteudo, f"relatorio-executivo-{fim:%Y%m%d}.pdf")
