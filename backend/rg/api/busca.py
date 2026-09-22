"""Busca global (solicitações, serviços, fornecedores e usuários), sempre sob RLS."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..seguranca.sessao import requer_login, tx

bp = Blueprint("busca", __name__)


@bp.get("/busca")
@requer_login
def buscar():
    q = (request.args.get("q") or "").strip()[:100]
    if len(q) < 2:
        return jsonify({"solicitacoes": [], "servicos": [], "fornecedores": [], "usuarios": []})
    like = "%" + q.replace("%", r"\%").replace("_", r"\_") + "%"
    with tx() as cur:
        cur.execute("""select id, codigo, titulo, status, setor_nome, setor_cor from rg.v_solicitacoes
                        where codigo ilike %s or titulo ilike %s
                           or to_tsvector('portuguese', titulo || ' ' || descricao) @@ plainto_tsquery('portuguese', %s)
                        order by criado_em desc limit 8""", (like, like, q))
        solicitacoes = cur.fetchall()
        cur.execute("""select id, codigo, titulo, situacao, data_programada, setor_nome, setor_cor from rg.v_servicos
                        where codigo ilike %s or titulo ilike %s or responsavel_executor ilike %s
                        order by data_programada desc limit 6""", (like, like, like))
        servicos = cur.fetchall()
        fornecedores, usuarios = [], []
        if g.usuario["papel"] in ("admin", "compras"):
            cur.execute("select id, razao_social, cnpj from rg.fornecedores where razao_social ilike %s"
                        " or nome_fantasia ilike %s or cnpj ilike %s order by razao_social limit 5", (like, like, like))
            fornecedores = cur.fetchall()
        if g.usuario["papel"] == "admin":
            cur.execute("select id, nome, email, status from rg.usuarios where nome ilike %s or email ilike %s"
                        " order by nome limit 5", (like, like))
            usuarios = cur.fetchall()
    return jsonify({"solicitacoes": solicitacoes, "servicos": servicos, "fornecedores": fornecedores,
                    "usuarios": usuarios})
