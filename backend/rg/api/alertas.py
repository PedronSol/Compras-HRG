"""Alertas operacionais calculados em tempo real (sempre sob RLS: cada perfil vê o seu escopo)."""
from __future__ import annotations

from flask import Blueprint, g, jsonify

from ..seguranca.sessao import requer_login, tx

bp = Blueprint("alertas", __name__)

GRAVIDADE = {"critico": 0, "alerta": 1, "info": 2}


def calcular(cur, usuario: dict) -> list[dict]:
    papel = usuario["papel"]
    alertas: list[dict] = []

    def add(tipo, gravidade, titulo, descricao, link, data=None, setor=None, cor=None, referencia=None):
        alertas.append({"tipo": tipo, "gravidade": gravidade, "titulo": titulo, "descricao": descricao, "link": link,
                        "data": data, "setor": setor, "setor_cor": cor, "referencia": referencia})

    # Prazo de atendimento (SLA) estourado ou vencendo
    cur.execute("""select id, codigo, titulo, status, sla_situacao, sla_prazo_limite, setor_nome, setor_cor, comprador_id
                     from rg.v_solicitacoes
                    where sla_situacao in ('estourado', 'alerta') order by sla_prazo_limite limit 60""")
    for s in cur.fetchall():
        if papel == "comprador" and s["status"] not in ("aprovada", "em_cotacao", "aguardando_pedido"):
            continue
        if papel == "recebimento":
            continue
        estourado = s["sla_situacao"] == "estourado"
        add("sla", "critico" if estourado else "alerta",
            "Prazo de atendimento estourado" if estourado else "Prazo de atendimento vence em menos de 24 h",
            f"{s['codigo']} · {s['titulo']}", f"/solicitacoes/{s['id']}", s["sla_prazo_limite"], s["setor_nome"],
            s["setor_cor"], s["codigo"])

    # Entregas atrasadas e próximas
    cur.execute("select rg.config_num('dias_alerta_entrega') as d")
    dias = int(cur.fetchone()["d"] or 2)
    cur.execute("""select id, codigo, fornecedor_fantasia, fornecedor_nome, data_prevista_entrega, atrasado, dias_atraso,
                          setor_nome, setor_cor
                     from rg.v_pedidos
                    where status in ('enviado', 'entregue_parcial')
                      and data_prevista_entrega <= rg.hoje() + %s
                    order by data_prevista_entrega limit 60""", (dias,))
    for p in cur.fetchall():
        fornecedor = p["fornecedor_fantasia"] or p["fornecedor_nome"]
        if p["atrasado"]:
            add("entrega", "critico", f"Entrega atrasada há {p['dias_atraso']} dia(s)", f"{p['codigo']} · {fornecedor}",
                f"/pedidos/{p['id']}", p["data_prevista_entrega"], p["setor_nome"], p["setor_cor"], p["codigo"])
        elif papel in ("recebimento", "comprador", "admin"):
            add("entrega", "info", "Entrega prevista para os próximos dias", f"{p['codigo']} · {fornecedor}",
                f"/pedidos/{p['id']}", p["data_prevista_entrega"], p["setor_nome"], p["setor_cor"], p["codigo"])

    # Aprovações paradas
    cur.execute("""select id, codigo, titulo, status, atualizado_em, setor_nome, setor_cor,
                          extract(day from now() - atualizado_em)::int as dias
                     from rg.v_solicitacoes
                    where status in ('aguardando_gestor', 'aguardando_diretoria') and atualizado_em < now() - interval '3 days'
                    order by atualizado_em limit 40""")
    for s in cur.fetchall():
        if papel == "gestor" and s["status"] != "aguardando_gestor":
            continue
        if papel not in ("gestor", "diretoria", "admin", "solicitante", "auditoria"):
            continue
        add("aprovacao", "alerta", f"Aguardando aprovação há {s['dias']} dias", f"{s['codigo']} · {s['titulo']}",
            f"/solicitacoes/{s['id']}", s["atualizado_em"], s["setor_nome"], s["setor_cor"], s["codigo"])

    if papel in ("financeiro", "diretoria", "admin", "comprador", "auditoria"):
        cur.execute("""select id, codigo, status, criado_em, valor_total, setor_nome, setor_cor,
                              extract(day from now() - atualizado_em)::int as dias
                         from rg.v_pedidos
                        where status in ('aguardando_financeiro', 'aguardando_diretoria')
                          and atualizado_em < now() - interval '2 days' order by atualizado_em limit 30""")
        for p in cur.fetchall():
            if papel == "diretoria" and p["status"] != "aguardando_diretoria":
                continue
            if papel == "financeiro" and p["status"] != "aguardando_financeiro":
                continue
            add("aprovacao", "alerta", f"Pedido aguardando aprovação há {p['dias']} dias", p["codigo"],
                f"/pedidos/{p['id']}", p["criado_em"], p["setor_nome"], p["setor_cor"], p["codigo"])

    # Propostas vencidas ou vencendo em cotações abertas
    if papel in ("comprador", "admin"):
        cur.execute("""select c.validade_proposta, c.validade_proposta < rg.hoje() as vencida, s.id, s.codigo, f.nome_fantasia, f.razao_social, st.nome as setor_nome,
                              st.cor as setor_cor
                         from rg.cotacoes c join rg.solicitacoes s on s.id = c.solicitacao_id
                         join rg.fornecedores f on f.id = c.fornecedor_id join rg.setores st on st.codigo = s.setor_codigo
                        where s.status in ('em_cotacao', 'aguardando_pedido') and c.validade_proposta is not null
                          and c.validade_proposta <= rg.hoje() + 3 order by c.validade_proposta limit 30""")
        for c in cur.fetchall():
            vencida = c["vencida"]
            add("proposta", "alerta" if vencida else "info",
                "Proposta vencida" if vencida else "Proposta vence em até 3 dias",
                f"{c['codigo']} · {c['nome_fantasia'] or c['razao_social']}", f"/solicitacoes/{c['id']}?aba=cotacao",
                c["validade_proposta"], c["setor_nome"], c["setor_cor"], c["codigo"])

    # Recebimentos com divergência (últimos 30 dias)
    if papel in ("comprador", "recebimento", "admin", "financeiro", "auditoria", "diretoria"):
        cur.execute("""select pedido_id, codigo, pedido_codigo, situacao, recebido_em, nota_fiscal, fornecedor_nome,
                              fornecedor_fantasia, setor_nome, setor_cor
                         from rg.v_recebimentos where situacao <> 'conforme' and recebido_em > now() - interval '30 days'
                        order by recebido_em desc limit 20""")
        for r in cur.fetchall():
            add("recebimento", "alerta", "Recebimento com divergência" if r["situacao"] == "divergente" else "Entrega recusada",
                f"{r['pedido_codigo']} · NF {r['nota_fiscal']} · {r['fornecedor_fantasia'] or r['fornecedor_nome']}",
                f"/pedidos/{r['pedido_id']}", r["recebido_em"], r["setor_nome"], r["setor_cor"], r["codigo"])

    alertas.sort(key=lambda a: (GRAVIDADE[a["gravidade"]], str(a["data"] or "")))
    return alertas


@bp.get("/alertas")
@requer_login
def listar():
    with tx() as cur:
        itens = calcular(cur, g.usuario)
    resumo = {g_: sum(1 for a in itens if a["gravidade"] == g_) for g_ in GRAVIDADE}
    return jsonify({"itens": itens, "resumo": resumo, "total": len(itens)})
