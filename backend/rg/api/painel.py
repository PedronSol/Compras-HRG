"""Painel de indicadores (conforme o perfil), pendências do usuário e relatório executivo em PDF."""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..seguranca.sessao import registrar_evento, requer_login, tx
from ..servicos import pdf
from ..servicos.painel import painel as montar_painel
from ..validacao import Campo, validar
from ._util import periodo, resposta_pdf
from .alertas import calcular as calcular_alertas
from .aprovacoes import pendencias
from .pedidos import fila_pedidos_sql
from .solicitacoes import fila_sql

bp = Blueprint("painel", __name__)


def _parametros():
    inicio, fim = periodo(365)
    setor = validar(request.args.to_dict(), [Campo("setor", "texto", max_len=40)]).get("setor")
    if g.usuario["papel"] in ("solicitante", "gestor"):
        setor = g.usuario["setor_codigo"]
    return inicio, fim, setor


@bp.get("/painel")
@requer_login
def painel():
    inicio, fim, setor = _parametros()
    with tx() as cur:
        dados = montar_painel(cur, inicio, fim, setor, current_app.config["TIMEZONE"])
    return jsonify(dados)


@bp.get("/painel/pendencias")
@requer_login
def minhas_pendencias():
    """Resumo do que aguarda o usuário, usado pela página inicial e pelos contadores do menu."""
    u = g.usuario
    with tx() as cur:
        cond_s, par_s = fila_sql(u)
        cur.execute(f"""select v.id, v.codigo, v.titulo, v.status, v.urgencia, v.setor_nome, v.setor_cor, v.atualizado_em,
                               v.valor_estimado, v.sla_situacao, v.sla_horas_restantes
                          from rg.v_solicitacoes v where {cond_s}
                         order by array_position(array['imediato','urgente','normal'], v.urgencia::text), v.sla_prazo_limite
                         limit 50""", par_s)
        solicitacoes = cur.fetchall()
        cond_p, par_p = fila_pedidos_sql(u)
        cur.execute(f"""select p.id, p.codigo, p.status, p.valor_total, p.fornecedor_nome, p.fornecedor_fantasia,
                               p.solicitacao_codigo, p.solicitacao_titulo, p.setor_nome, p.setor_cor, p.data_prevista_entrega,
                               p.atrasado, p.atualizado_em
                          from rg.v_pedidos p where {cond_p} order by p.atrasado desc, p.data_prevista_entrega nulls last,
                               p.criado_em limit 50""", par_p)
        pedidos = cur.fetchall()
        aprov = pendencias(cur, u)
        alertas = calcular_alertas(cur, u)
        cur.execute("select count(*) as n from rg.notificacoes where destinatario_id = %s and not lida", (u["id"],))
        nao_lidas = cur.fetchone()["n"]
        usuarios_pendentes = 0
        if u["papel"] == "admin":
            cur.execute("select count(*) as n from rg.usuarios where status = 'pendente'")
            usuarios_pendentes = cur.fetchone()["n"]
    return jsonify({
        "solicitacoes": solicitacoes, "pedidos": pedidos,
        "contadores": {
            "fila": len(solicitacoes) + len(pedidos),
            "aprovacoes": len(aprov["solicitacoes"]) + len(aprov["pedidos"]),
            "cotacoes": sum(1 for s in solicitacoes if s["status"] in ("aprovada", "em_cotacao", "aguardando_pedido")),
            "pedidos": len(pedidos),
            "recebimentos": len(pedidos) if u["papel"] == "recebimento" else 0,
            "alertas": sum(1 for a in alertas if a["gravidade"] != "info"),
            "notificacoes": nao_lidas,
            "usuarios": usuarios_pendentes,
        },
    })


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
    return resposta_pdf(conteudo, f"relatorio-executivo-compras-{fim:%Y%m%d}.pdf")
