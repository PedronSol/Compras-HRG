"""Cadastro de fornecedores e indicadores de desempenho (Compras e Administração editam)."""
from __future__ import annotations

import re

from flask import Blueprint, g, jsonify, request

from ..errors import NaoEncontrado, ValidacaoError
from ..permissoes import exigir, pode
from ..seguranca.sessao import requer_login, tx
from ..validacao import Campo, cnpj_valido, validar
from ._util import corpo_json, like, paginacao

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
    Campo("cidade", "texto", max_len=80, rotulo="Cidade"),
    Campo("uf", "texto", max_len=2, rotulo="UF",
          validador=lambda v: None if re.fullmatch(r"[A-Za-z]{2}", v) else "UF inválida"),
    Campo("observacoes", "texto", max_len=1000, rotulo="Observações"),
    Campo("ativo", "bool", rotulo="Ativo"),
]

# Desempenho calculado a partir do histórico real de propostas, pedidos e recebimentos.
DESEMPENHO = """
    (select count(*) from rg.cotacoes c where c.fornecedor_id = f.id) as propostas,
    (select count(*) from rg.cotacoes c where c.fornecedor_id = f.id and c.selecionada) as vencedoras,
    (select count(*) from rg.pedidos p where p.fornecedor_id = f.id and p.status not in ('reprovado', 'cancelado')) as pedidos,
    (select coalesce(sum(p.valor_total), 0) from rg.pedidos p
      where p.fornecedor_id = f.id and p.status not in ('reprovado', 'cancelado')) as valor_contratado,
    (select round(100.0 * count(*) filter (where p.concluido_em::date <= p.data_prevista_entrega) / nullif(count(*), 0))
       from rg.pedidos p where p.fornecedor_id = f.id and p.status = 'entregue') as pontualidade,
    (select round(100.0 * count(*) filter (where r.situacao = 'conforme') / nullif(count(*), 0))
       from rg.recebimentos r join rg.pedidos p on p.id = r.pedido_id where p.fornecedor_id = f.id) as conformidade,
    (select max(p.criado_em) from rg.pedidos p where p.fornecedor_id = f.id) as ultimo_pedido_em
"""


def _normalizar(dados: dict) -> dict:
    if dados.get("cnpj"):
        dados["cnpj"] = re.sub(r"[^0-9A-Za-z]", "", dados["cnpj"]).upper()
    if dados.get("uf"):
        dados["uf"] = dados["uf"].upper()
    return dados


@bp.get("/fornecedores")
@requer_login
def listar():
    args = validar(request.args.to_dict(), [Campo("q", "texto", max_len=100), Campo("ativos", "bool"),
                                            Campo("ordem", "escolha", escolhas=("nome", "valor", "pedidos"),
                                                  padrao="nome")])
    pagina, por_pagina = paginacao(50, 500)
    where, params = ["true"], []
    if args.get("ativos"):
        where.append("f.ativo")
    if args.get("q"):
        termo = like(args["q"])
        cnpj = re.sub(r"[^0-9A-Za-z]", "", args["q"]).upper()
        where.append("(f.razao_social ilike %s or f.nome_fantasia ilike %s or f.cidade ilike %s"
                     " or (%s <> '' and f.cnpj like %s))")
        params += [termo, termo, termo, cnpj, cnpj + "%"]
    clausula = " and ".join(where)
    ordem = {"nome": "f.razao_social", "valor": "valor_contratado desc, f.razao_social",
             "pedidos": "pedidos desc, f.razao_social"}[args.get("ordem") or "nome"]
    completo = pode(g.usuario, "fornecedor.ver")
    with tx() as cur:
        cur.execute(f"select count(*) as n from rg.fornecedores f where {clausula}", params)
        total = cur.fetchone()["n"]
        colunas = f"f.*, {DESEMPENHO}" if completo else "f.id, f.razao_social, f.nome_fantasia, f.cnpj, f.cidade, f.uf, f.ativo"
        cur.execute(f"select {colunas} from rg.fornecedores f where {clausula} order by {ordem if completo else 'f.razao_social'}"
                    " limit %s offset %s", (*params, por_pagina, (pagina - 1) * por_pagina))
        itens = cur.fetchall()
    return jsonify({"itens": itens, "total": total, "pagina": pagina, "por_pagina": por_pagina})


@bp.get("/fornecedores/<uuid:fornecedor_id>")
@requer_login
def detalhar(fornecedor_id):
    exigir(g.usuario, "fornecedor.ver")
    fid = str(fornecedor_id)
    with tx() as cur:
        cur.execute(f"select f.*, {DESEMPENHO} from rg.fornecedores f where f.id = %s", (fid,))
        f = cur.fetchone()
        if not f:
            raise NaoEncontrado("Fornecedor não encontrado")
        cur.execute("""select id, codigo, status, valor_total, criado_em, data_prevista_entrega, solicitacao_codigo,
                              solicitacao_titulo, setor_nome, setor_cor, atrasado, percentual_recebido
                         from rg.v_pedidos where fornecedor_id = %s order by criado_em desc limit 30""", (fid,))
        pedidos = cur.fetchall()
        cur.execute("""select c.id, c.valor_total, c.prazo_entrega_dias, c.selecionada, c.criado_em, s.id as solicitacao_id,
                              s.codigo as solicitacao_codigo, s.titulo as solicitacao_titulo, s.status as solicitacao_status
                         from rg.cotacoes c join rg.solicitacoes s on s.id = c.solicitacao_id
                        where c.fornecedor_id = %s order by c.criado_em desc limit 30""", (fid,))
        propostas = cur.fetchall()
    return jsonify({"fornecedor": f, "pedidos": pedidos, "propostas": propostas})


@bp.post("/fornecedores")
@requer_login
def criar():
    exigir(g.usuario, "fornecedor.gerenciar")
    dados = _normalizar(validar(corpo_json(), CAMPOS))
    dados.pop("ativo", None)
    with tx() as cur:
        cur.execute("select id from rg.fornecedores where cnpj = %s", (dados["cnpj"],))
        if cur.fetchone():
            raise ValidacaoError({"cnpj": "Já existe fornecedor com este CNPJ"})
        colunas = ["razao_social", "nome_fantasia", "cnpj", "email", "telefone", "contato", "cidade", "uf", "observacoes"]
        cur.execute(
            f"""insert into rg.fornecedores ({", ".join(colunas)}, criado_por)
                values ({", ".join(["%s"] * len(colunas))}, %s) returning *""",
            (*[dados.get(c) for c in colunas], g.usuario["id"]),
        )
        return jsonify(cur.fetchone()), 201


@bp.patch("/fornecedores/<uuid:fornecedor_id>")
@requer_login
def atualizar(fornecedor_id):
    exigir(g.usuario, "fornecedor.gerenciar")
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
