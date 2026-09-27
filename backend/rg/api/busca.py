"""Busca global (solicitações, pedidos, fornecedores, materiais e usuários), sempre sob RLS."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..permissoes import pode
from ..seguranca.sessao import requer_login, tx
from ._util import like

bp = Blueprint("busca", __name__)


@bp.get("/busca")
@requer_login
def buscar():
    q = (request.args.get("q") or "").strip()[:100]
    vazio = {"solicitacoes": [], "pedidos": [], "fornecedores": [], "materiais": [], "usuarios": []}
    if len(q) < 2:
        return jsonify(vazio)
    termo = like(q)
    resultado = dict(vazio)
    with tx() as cur:
        cur.execute("""select id, codigo, titulo, status, setor_nome, setor_cor from rg.v_solicitacoes
                        where codigo ilike %s or titulo ilike %s
                           or to_tsvector('portuguese', titulo || ' ' || coalesce(descricao, '')) @@ plainto_tsquery('portuguese', %s)
                        order by criado_em desc limit 8""", (termo, termo, q))
        resultado["solicitacoes"] = cur.fetchall()
        if pode(g.usuario, "pedido.ver"):
            cur.execute("""select id, codigo, status, fornecedor_nome, fornecedor_fantasia, valor_total from rg.v_pedidos
                            where codigo ilike %s or fornecedor_nome ilike %s or fornecedor_fantasia ilike %s
                            order by criado_em desc limit 6""", (termo, termo, termo))
            resultado["pedidos"] = cur.fetchall()
        if pode(g.usuario, "fornecedor.ver"):
            cur.execute("select id, razao_social, nome_fantasia, cnpj from rg.fornecedores where razao_social ilike %s"
                        " or nome_fantasia ilike %s or cnpj ilike %s order by razao_social limit 5", (termo, termo, termo))
            resultado["fornecedores"] = cur.fetchall()
        cur.execute("select id, codigo, nome, unidade from rg.materiais where nome ilike %s or codigo ilike %s"
                    " order by nome limit 5", (termo, termo))
        resultado["materiais"] = cur.fetchall()
        if pode(g.usuario, "usuario.gerenciar"):
            cur.execute("select id, nome, email, status from rg.usuarios where nome ilike %s or email ilike %s"
                        " order by nome limit 5", (termo, termo))
            resultado["usuarios"] = cur.fetchall()
    return jsonify(resultado)
