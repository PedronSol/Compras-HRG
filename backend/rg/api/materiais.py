"""Catálogo de materiais e categorias."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..errors import NaoEncontrado, ValidacaoError
from ..permissoes import exigir
from ..rotulos import UNIDADES
from ..seguranca.sessao import requer_login, tx
from ..validacao import Campo, validar
from ._util import corpo_json, like, paginacao

bp = Blueprint("materiais", __name__)

CAMPOS_CATEGORIA = [
    Campo("nome", "texto", obrigatorio=True, min_len=2, max_len=80, rotulo="Nome"),
    Campo("descricao", "texto", max_len=400, rotulo="Descrição"),
    Campo("cor", "texto", max_len=7, rotulo="Cor",
          validador=lambda v: None if len(v) == 7 and v.startswith("#") else "Use o formato #RRGGBB"),
    Campo("ativo", "bool", rotulo="Ativa"),
]
CAMPOS_MATERIAL = [
    Campo("nome", "texto", obrigatorio=True, min_len=3, max_len=160, rotulo="Nome"),
    Campo("descricao", "texto", max_len=1000, rotulo="Descrição"),
    Campo("categoria_id", "uuid", obrigatorio=True, rotulo="Categoria"),
    Campo("unidade", "escolha", obrigatorio=True, escolhas=tuple(UNIDADES), rotulo="Unidade"),
    Campo("preco_referencia", "decimal", minimo=0, maximo=999_999_999, rotulo="Preço de referência"),
    Campo("ativo", "bool", rotulo="Ativo"),
]


@bp.get("/categorias")
@requer_login
def listar_categorias():
    with tx() as cur:
        cur.execute("""select c.*, (select count(*) from rg.materiais m where m.categoria_id = c.id) as materiais,
                              (select count(*) from rg.materiais m where m.categoria_id = c.id and m.ativo) as materiais_ativos
                         from rg.categorias c order by c.nome""")
        return jsonify({"itens": cur.fetchall()})


@bp.post("/categorias")
@requer_login
def criar_categoria():
    exigir(g.usuario, "material.gerenciar")
    d = validar(corpo_json(), CAMPOS_CATEGORIA)
    with tx() as cur:
        cur.execute("select 1 from rg.categorias where lower(nome) = lower(%s)", (d["nome"],))
        if cur.fetchone():
            raise ValidacaoError({"nome": "Já existe uma categoria com este nome"})
        cur.execute("insert into rg.categorias (nome, descricao, cor) values (%s, %s, %s) returning *",
                    (d["nome"], d.get("descricao"), d.get("cor") or "#475569"))
        return jsonify(cur.fetchone()), 201


@bp.patch("/categorias/<uuid:categoria_id>")
@requer_login
def atualizar_categoria(categoria_id):
    exigir(g.usuario, "material.gerenciar")
    d = {k: v for k, v in validar(corpo_json(), CAMPOS_CATEGORIA, parcial=True).items() if v is not None}
    if not d:
        raise ValidacaoError({"geral": "Nenhuma alteração informada"})
    with tx() as cur:
        sets = ", ".join(f"{k} = %s" for k in d)
        cur.execute(f"update rg.categorias set {sets} where id = %s returning *", (*d.values(), str(categoria_id)))
        c = cur.fetchone()
        if not c:
            raise NaoEncontrado("Categoria não encontrada")
        return jsonify(c)


@bp.get("/materiais")
@requer_login
def listar_materiais():
    args = validar(request.args.to_dict(), [Campo("q", "texto", max_len=100), Campo("categoria", "uuid"),
                                            Campo("ativos", "bool")])
    pagina, por_pagina = paginacao(50, 500)
    where, params = ["true"], []
    if args.get("ativos"):
        where.append("m.ativo")
    if args.get("categoria"):
        where.append("m.categoria_id = %s")
        params.append(args["categoria"])
    if args.get("q"):
        termo = like(args["q"])
        where.append("(m.nome ilike %s or m.codigo ilike %s or m.descricao ilike %s)")
        params += [termo, termo, termo]
    clausula = " and ".join(where)
    with tx() as cur:
        cur.execute(f"select count(*) as n from rg.materiais m where {clausula}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"""select m.*, c.nome as categoria_nome, c.cor as categoria_cor,
                               (select count(distinct si.solicitacao_id) from rg.solicitacao_itens si
                                 where si.material_id = m.id) as solicitacoes
                          from rg.materiais m join rg.categorias c on c.id = m.categoria_id
                         where {clausula} order by m.nome limit %s offset %s""",
                    (*params, por_pagina, (pagina - 1) * por_pagina))
        itens = cur.fetchall()
    return jsonify({"itens": itens, "total": total, "pagina": pagina, "por_pagina": por_pagina})


@bp.post("/materiais")
@requer_login
def criar_material():
    exigir(g.usuario, "material.gerenciar")
    d = validar(corpo_json(), CAMPOS_MATERIAL)
    with tx() as cur:
        cur.execute("""insert into rg.materiais (nome, descricao, categoria_id, unidade, preco_referencia, criado_por)
                       values (%s, %s, %s, %s, %s, %s) returning *""",
                    (d["nome"], d.get("descricao"), d["categoria_id"], d["unidade"], d.get("preco_referencia"),
                     g.usuario["id"]))
        return jsonify(cur.fetchone()), 201


@bp.patch("/materiais/<uuid:material_id>")
@requer_login
def atualizar_material(material_id):
    exigir(g.usuario, "material.gerenciar")
    d = validar(corpo_json(), CAMPOS_MATERIAL, parcial=True)
    for obrigatorio in ("nome", "categoria_id", "unidade"):
        if obrigatorio in d and not d[obrigatorio]:
            raise ValidacaoError({obrigatorio: "Campo obrigatório"})
    if not d:
        raise ValidacaoError({"geral": "Nenhuma alteração informada"})
    with tx() as cur:
        sets = ", ".join(f"{k} = %s" for k in d)
        cur.execute(f"update rg.materiais set {sets} where id = %s returning *", (*d.values(), str(material_id)))
        m = cur.fetchone()
        if not m:
            raise NaoEncontrado("Material não encontrado")
        return jsonify(m)
