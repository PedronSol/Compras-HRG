"""Trilha de auditoria (somente Administração)."""
from __future__ import annotations

import re

from flask import Blueprint, current_app, jsonify, request

from ..errors import ValidacaoError
from ..seguranca.sessao import requer_papel, tx
from ..validacao import Campo, validar
from ._util import paginacao

bp = Blueprint("auditoria", __name__)


@bp.get("/auditoria")
@requer_papel("admin")
def listar():
    args = validar(request.args.to_dict(), [
        Campo("tabela", "texto", max_len=60),
        Campo("operacao", "texto", max_len=40),
        Campo("usuario", "uuid"),
        Campo("registro", "texto", max_len=64),
        Campo("inicio", "data"),
        Campo("fim", "data"),
    ])
    pagina, por_pagina = paginacao(50, 200)
    where, params = ["true"], []
    tz = current_app.config["TIMEZONE"]
    if args.get("tabela"):
        where.append("e.tabela = %s")
        params.append(args["tabela"])
    if args.get("operacao"):
        where.append("e.operacao = %s")
        params.append(args["operacao"].upper())
    if args.get("usuario"):
        where.append("e.usuario_id = %s")
        params.append(args["usuario"])
    if args.get("registro"):
        where.append("e.registro_id = %s")
        params.append(args["registro"])
    if args.get("inicio"):
        where.append("(e.ocorrido_em at time zone %s)::date >= %s")
        params += [tz, args["inicio"]]
    if args.get("fim"):
        where.append("(e.ocorrido_em at time zone %s)::date <= %s")
        params += [tz, args["fim"]]
    clausula = " and ".join(where)
    with tx() as cur:
        cur.execute(f"select count(*) as n from audit.eventos e where {clausula}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"""select e.id, e.ocorrido_em, e.usuario_id, u.nome as usuario_nome, e.ip, e.tabela, e.registro_id,
                               e.operacao, e.campos_alterados, e.dados_antes, e.dados_depois
                          from audit.eventos e left join rg.v_usuarios_publico u on u.id = e.usuario_id
                         where {clausula} order by e.id desc limit %s offset %s""",
                    (*params, por_pagina, (pagina - 1) * por_pagina))
        itens = cur.fetchall()
        cur.execute("select distinct tabela from audit.eventos order by 1")
        tabelas = [r["tabela"] for r in cur.fetchall()]
        cur.execute("select distinct operacao from audit.eventos order by 1")
        operacoes = [r["operacao"] for r in cur.fetchall()]
    return jsonify({"itens": itens, "total": total, "pagina": pagina, "por_pagina": por_pagina,
                    "tabelas": tabelas, "operacoes": operacoes})


@bp.get("/auditoria/relatorios/<codigo>")
@requer_papel("admin")
def verificar_relatorio(codigo: str):
    """Confere se um código de verificação impresso em um PDF foi emitido pela plataforma."""
    if not re.fullmatch(r"[0-9a-f]{64}", codigo):
        raise ValidacaoError({"codigo": "Código de verificação inválido"})
    with tx() as cur:
        cur.execute("""select e.ocorrido_em, e.registro_id, e.dados_depois, u.nome as usuario_nome, e.ip
                         from audit.eventos e left join rg.v_usuarios_publico u on u.id = e.usuario_id
                        where e.operacao = 'RELATORIO_GERADO' and e.dados_depois ->> 'codigo_verificacao' = %s
                        order by e.id desc limit 1""", (codigo,))
        evento = cur.fetchone()
    return jsonify({"autentico": bool(evento), "emissao": evento})
