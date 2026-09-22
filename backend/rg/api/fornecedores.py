"""Cadastro de fornecedores (Compras e Administração)."""
from __future__ import annotations

import re

from flask import Blueprint, g, jsonify, request

from ..errors import NaoEncontrado, ValidacaoError
from ..seguranca.sessao import requer_login, requer_papel, tx
from ..servicos.ocr.analise import cnpj_valido
from ..validacao import Campo, validar
from ._util import corpo_json, paginacao

bp = Blueprint("fornecedores", __name__)


def _cnpj(valor: str) -> str | None:
    d = re.sub(r"[^0-9A-Za-z]", "", valor or "").upper()
    return None if cnpj_valido(d) else "CNPJ inválido (dígito verificador não confere)"


CAMPOS = [
    Campo("razao_social", "texto", obrigatorio=True, min_len=2, max_len=160, rotulo="Razão social"),
    Campo("nome_fantasia", "texto", max_len=160, rotulo="Nome fantasia"),
    Campo("cnpj", "texto", obrigatorio=True, max_len=20, rotulo="CNPJ", validador=_cnpj),
    Campo("email", "email", rotulo="E-mail"),
    Campo("telefone", "texto", max_len=30, rotulo="Telefone"),
    Campo("contato", "texto", max_len=120, rotulo="Contato"),
    Campo("ativo", "bool", rotulo="Ativo"),
]


def _normalizar(dados: dict) -> dict:
    if dados.get("cnpj"):
        dados["cnpj"] = re.sub(r"[^0-9A-Za-z]", "", dados["cnpj"]).upper()
    return dados


@bp.get("/fornecedores")
@requer_login
def listar():
    args = validar(request.args.to_dict(), [Campo("q", "texto", max_len=100), Campo("ativos", "bool")])
    pagina, por_pagina = paginacao(50, 200)
    where, params = ["true"], []
    if args.get("ativos"):
        where.append("ativo")
    if args.get("q"):
        termo = "%" + args["q"].replace("%", r"\%").replace("_", r"\_") + "%"
        cnpj = re.sub(r"[^0-9A-Za-z]", "", args["q"]).upper()
        where.append("(razao_social ilike %s or nome_fantasia ilike %s or (%s <> '' and cnpj like %s))")
        params += [termo, termo, cnpj, cnpj + "%"]
    clausula = " and ".join(where)
    with tx() as cur:
        cur.execute(f"select count(*) as n from rg.fornecedores where {clausula}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"""select f.*, (select count(*) from rg.cotacoes c where c.fornecedor_id = f.id) as cotacoes,
                               (select count(*) from rg.cotacoes c where c.fornecedor_id = f.id and c.selecionada) as vencedoras
                          from rg.fornecedores f where {clausula}
                         order by razao_social limit %s offset %s""", (*params, por_pagina, (pagina - 1) * por_pagina))
        itens = cur.fetchall()
    return jsonify({"itens": itens, "total": total, "pagina": pagina, "por_pagina": por_pagina})


@bp.post("/fornecedores")
@requer_papel("compras", "admin")
def criar():
    dados = _normalizar(validar(corpo_json(), CAMPOS))
    dados.pop("ativo", None)
    with tx() as cur:
        cur.execute("select id from rg.fornecedores where cnpj = %s", (dados["cnpj"],))
        if cur.fetchone():
            raise ValidacaoError({"cnpj": "Já existe fornecedor com este CNPJ"})
        cur.execute(
            """insert into rg.fornecedores (razao_social, nome_fantasia, cnpj, email, telefone, contato, criado_por)
               values (%s, %s, %s, %s, %s, %s, %s) returning *""",
            (dados["razao_social"], dados.get("nome_fantasia"), dados["cnpj"], dados.get("email"),
             dados.get("telefone"), dados.get("contato"), g.usuario["id"]),
        )
        return jsonify(cur.fetchone()), 201


@bp.patch("/fornecedores/<uuid:fornecedor_id>")
@requer_papel("compras", "admin")
def atualizar(fornecedor_id):
    dados = _normalizar(validar(corpo_json(), CAMPOS, parcial=True))
    for obrigatorio in ("razao_social", "cnpj"):
        if obrigatorio in dados and not dados[obrigatorio]:
            raise ValidacaoError({obrigatorio: "Campo obrigatório"})
    if not dados:
        raise ValidacaoError({"geral": "Nenhuma alteração informada"})
    with tx() as cur:
        sets = ", ".join(f"{k} = %s" for k in dados)
        cur.execute(f"update rg.fornecedores set {sets} where id = %s returning *", (*dados.values(), str(fornecedor_id)))
        f = cur.fetchone()
        if not f:
            raise NaoEncontrado("Fornecedor não encontrado")
    return jsonify(f)
