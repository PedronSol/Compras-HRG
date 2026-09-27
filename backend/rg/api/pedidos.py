"""Pedidos de compra (aprovação financeira, envio ao fornecedor) e recebimento com conferência."""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..errors import ApiError, NaoEncontrado
from ..permissoes import exigir, pode
from ..rotulos import SITUACAO_RECEBIMENTO, STATUS_PEDIDO
from ..seguranca.sessao import ip_cliente, registrar_evento, requer_login, tx, user_agent
from ..servicos import pdf, workflow
from ..servicos.arquivos import LoteArquivos, validar_arquivo
from ..validacao import Campo, validar
from ._util import corpo_json, like, lista_itens, paginacao, resposta_csv, resposta_pdf

bp = Blueprint("pedidos", __name__)

ORDENACOES = {
    "recentes": "p.criado_em desc",
    "valor": "p.valor_total desc",
    "previsao": "p.data_prevista_entrega asc nulls last",
}


def fila_pedidos_sql(usuario: dict) -> tuple[str, list]:
    papel = usuario["papel"]
    if papel == "financeiro":
        return "p.status = 'aguardando_financeiro'", []
    if papel == "diretoria":
        return "p.status = 'aguardando_diretoria'", []
    if papel == "comprador":
        return "(p.status = 'aprovado' and p.comprador_id = %s)", [usuario["id"]]
    if papel == "recebimento":
        return "p.status in ('enviado', 'entregue_parcial')", []
    return "false", []


def _filtros():
    args = validar(request.args.to_dict(), [
        Campo("status", "texto", max_len=200),
        Campo("fornecedor", "uuid"),
        Campo("setor", "texto", max_len=40),
        Campo("q", "texto", max_len=120),
        Campo("atrasados", "bool"),
        Campo("fila", "bool"),
        Campo("inicio", "data"),
        Campo("fim", "data"),
        Campo("ordem", "escolha", escolhas=tuple(ORDENACOES), padrao="recentes"),
    ])
    where, params = ["true"], []
    if args.get("status"):
        status = [s for s in args["status"].split(",") if s in STATUS_PEDIDO]
        if status:
            where.append("p.status = any(%s::rg.status_pedido[])")
            params.append(status)
    if args.get("fornecedor"):
        where.append("p.fornecedor_id = %s")
        params.append(args["fornecedor"])
    if args.get("setor"):
        where.append("p.setor_codigo = %s")
        params.append(args["setor"])
    if args.get("atrasados"):
        where.append("p.atrasado")
    if args.get("fila"):
        condicao, p = fila_pedidos_sql(g.usuario)
        where.append(condicao)
        params += p
    tz = current_app.config["TIMEZONE"]
    if args.get("inicio"):
        where.append("(p.criado_em at time zone %s)::date >= %s")
        params += [tz, args["inicio"]]
    if args.get("fim"):
        where.append("(p.criado_em at time zone %s)::date <= %s")
        params += [tz, args["fim"]]
    if args.get("q"):
        termo = like(args["q"])
        where.append("(p.codigo ilike %s or p.solicitacao_codigo ilike %s or p.solicitacao_titulo ilike %s"
                     " or p.fornecedor_nome ilike %s or p.fornecedor_fantasia ilike %s)")
        params += [termo] * 5
    return " and ".join(where), params, ORDENACOES[args.get("ordem") or "recentes"]


@bp.get("/pedidos")
@requer_login
def listar():
    exigir(g.usuario, "pedido.ver")
    clausula, params, ordem = _filtros()
    pagina, por_pagina = paginacao()
    with tx() as cur:
        cur.execute(f"select count(*) as n, coalesce(sum(p.valor_total), 0) as valor from rg.v_pedidos p where {clausula}",
                    params)
        agregado = cur.fetchone()
        cur.execute(f"select * from rg.v_pedidos p where {clausula} order by {ordem} limit %s offset %s",
                    (*params, por_pagina, (pagina - 1) * por_pagina))
        itens = cur.fetchall()
    return jsonify({"itens": itens, "total": agregado["n"], "valor_total": agregado["valor"], "pagina": pagina,
                    "por_pagina": por_pagina})


@bp.get("/pedidos/contagem")
@requer_login
def contagem():
    exigir(g.usuario, "pedido.ver")
    condicao, p = fila_pedidos_sql(g.usuario)
    with tx() as cur:
        cur.execute("select p.status, count(*) as n from rg.v_pedidos p group by p.status")
        por_status = {r["status"]: r["n"] for r in cur.fetchall()}
        cur.execute("select count(*) as n from rg.v_pedidos p where p.atrasado")
        atrasados = cur.fetchone()["n"]
        cur.execute(f"select count(*) as n from rg.v_pedidos p where {condicao}", p)
        fila = cur.fetchone()["n"]
    return jsonify({"por_status": por_status, "atrasados": atrasados, "fila": fila,
                    "total": sum(por_status.values())})


@bp.get("/pedidos/exportar.csv")
@requer_login
def exportar():
    exigir(g.usuario, "pedido.ver")
    clausula, params, ordem = _filtros()
    with tx() as cur:
        cur.execute(f"select * from rg.v_pedidos p where {clausula} order by {ordem} limit 20000", params)
        linhas = cur.fetchall()
        registrar_evento(cur, "EXPORTACAO_CSV", "rg.pedidos", None, {"registros": len(linhas)})
    return resposta_csv("pedidos-compras-hrg.csv",
                        ["Pedido", "Solicitação", "Setor", "Fornecedor", "CNPJ", "Status", "Valor total", "Emissão",
                         "Previsão de entrega", "Recebido (%)", "Comprador"],
                        [[l["codigo"], l["solicitacao_codigo"], l["setor_nome"], l["fornecedor_nome"], l["fornecedor_cnpj"],
                          STATUS_PEDIDO[l["status"]], f"{l['valor_total']:.2f}".replace(".", ","),
                          pdf.data_hora(l["criado_em"]), pdf.data_hora(l["data_prevista_entrega"]),
                          l["percentual_recebido"], l["comprador_nome"]] for l in linhas])


def carregar_pedido(cur, pedido_id: str) -> dict:
    cur.execute("select * from rg.v_pedidos where id = %s", (pedido_id,))
    p = cur.fetchone()
    if not p:
        raise NaoEncontrado("Pedido não encontrado ou fora do seu escopo de acesso")
    cur.execute("""select pi.*, m.codigo as material_codigo, (pi.quantidade * pi.valor_unitario) as total,
                          (pi.quantidade - pi.quantidade_recebida) as saldo
                     from rg.pedido_itens pi left join rg.materiais m on m.id = pi.material_id
                    where pi.pedido_id = %s order by pi.ordem""", (pedido_id,))
    itens = cur.fetchall()
    cur.execute("select * from rg.v_recebimentos where pedido_id = %s order by recebido_em", (pedido_id,))
    recebimentos = cur.fetchall()
    for r in recebimentos:
        cur.execute("""select ri.*, pi.descricao, pi.unidade from rg.recebimento_itens ri
                         join rg.pedido_itens pi on pi.id = ri.pedido_item_id
                        where ri.recebimento_id = %s order by pi.ordem""", (r["id"],))
        r["itens"] = cur.fetchall()
        cur.execute("""select id, nome_original, mime, tamanho, tipo_documento, criado_em from rg.anexos
                        where recebimento_id = %s and removido_em is null""", (r["id"],))
        r["anexos"] = cur.fetchall()
    cur.execute("""select f.* from rg.fornecedores f where f.id = %s""", (p["fornecedor_id"],))
    fornecedor = cur.fetchone()
    cur.execute("""select a.*, u.nome as usuario_nome, u.cargo as usuario_cargo from rg.aprovacoes a
                     left join rg.v_usuarios_publico u on u.id = a.usuario_id
                    where a.pedido_id = %s order by a.criado_em""", (pedido_id,))
    aprovacoes = cur.fetchall()
    cur.execute("""select h.*, u.nome as autor_nome, u.papel as autor_papel from rg.solicitacao_historico h
                     left join rg.v_usuarios_publico u on u.id = h.autor_id
                    where h.pedido_id = %s order by h.criado_em, h.id""", (pedido_id,))
    historico = cur.fetchall()
    cur.execute("""select a.id, a.acao, a.papel, a.assinado_em, a.ip, a.hash_autenticidade, u.nome as usuario_nome
                     from rg.assinaturas a left join rg.v_usuarios_publico u on u.id = a.usuario_id
                    where a.pedido_id = %s order by a.assinado_em""", (pedido_id,))
    assinaturas = cur.fetchall()
    cur.execute("select id, justificativa, local_entrega, data_necessidade, solicitante_id from rg.solicitacoes where id = %s",
                (p["solicitacao_id"],))
    solicitacao = cur.fetchone()
    return {"pedido": p, "itens": itens, "recebimentos": recebimentos, "fornecedor": fornecedor,
            "aprovacoes": aprovacoes, "historico": historico, "assinaturas": assinaturas, "solicitacao": solicitacao,
            "acoes": workflow.acoes_pedido(g.usuario, p)}


@bp.get("/pedidos/<uuid:pedido_id>")
@requer_login
def detalhar(pedido_id):
    with tx() as cur:
        return jsonify(carregar_pedido(cur, str(pedido_id)))


@bp.get("/pedidos/<uuid:pedido_id>/documento.pdf")
@requer_login
def documento(pedido_id):
    with tx() as cur:
        dados = carregar_pedido(cur, str(pedido_id))
        conteudo, codigo = pdf.documento_pedido(dados, autor=g.usuario["nome"],
                                                instituicao=current_app.config["INSTITUICAO"],
                                                tz=current_app.config["TIMEZONE"])
        registrar_evento(cur, "RELATORIO_GERADO", "rg.pedidos", str(pedido_id),
                         {"codigo_verificacao": codigo, "tipo": "pedido_compra"})
    return resposta_pdf(conteudo, f"{dados['pedido']['codigo']}.pdf", inline=request.args.get("inline") == "1")


@bp.post("/pedidos/<uuid:pedido_id>/acoes/<acao>")
@requer_login
def executar_acao(pedido_id, acao: str):
    pid = str(pedido_id)
    u = g.usuario
    requisitos = {"aprovar": None, "reprovar": None, "enviar": "pedido.emitir", "cancelar": None,
                  "encerrar": "pedido.emitir", "atualizar_previsao": "pedido.emitir"}
    if acao not in requisitos:
        raise NaoEncontrado("Ação inexistente")
    if acao in ("aprovar", "reprovar"):
        permitido = pode(u, "pedido.aprovar_financeiro") or pode(u, "pedido.aprovar_diretoria")
    elif acao == "cancelar":
        permitido = u["papel"] in ("comprador", "admin")
    else:
        permitido = pode(u, requisitos[acao])
    if not permitido:
        raise ApiError("Seu perfil não pode executar esta ação", 403, "proibido")
    corpo = corpo_json()
    comum = validar(corpo, [Campo("versao", "inteiro", minimo=1), Campo("texto", "texto", max_len=2000),
                            Campo("data_prevista_entrega", "data", rotulo="Previsão de entrega")])
    versao, texto = comum.get("versao"), comum.get("texto")
    ip, ua = ip_cliente(), user_agent()
    with tx() as cur:
        if acao in ("aprovar", "reprovar"):
            workflow.decidir_pedido(cur, u, pid, acao, texto, versao, ip, ua)
        elif acao == "enviar":
            workflow.enviar_pedido(cur, u, pid, comum.get("data_prevista_entrega"), versao, ip, ua)
        elif acao == "cancelar":
            workflow.cancelar_pedido(cur, u, pid, texto, versao, ip, ua)
        elif acao == "encerrar":
            workflow.encerrar_pedido(cur, u, pid, texto, versao, ip, ua)
        elif acao == "atualizar_previsao":
            if not comum.get("data_prevista_entrega"):
                from ..errors import ValidacaoError
                raise ValidacaoError({"data_prevista_entrega": "Informe a nova previsão"})
            workflow.atualizar_previsao(cur, pid, comum["data_prevista_entrega"], texto)
    with tx() as cur:
        return jsonify(carregar_pedido(cur, pid))


CAMPOS_RECEBIMENTO = [
    Campo("nota_fiscal", "texto", obrigatorio=True, max_len=60, rotulo="Nota fiscal"),
    Campo("data_emissao_nf", "data", rotulo="Emissão da NF"),
    Campo("valor_nf", "decimal", minimo=0, maximo=999_999_999, rotulo="Valor da NF"),
    Campo("observacoes", "texto", max_len=2000, rotulo="Observações"),
    Campo("tipo_documento", "escolha", escolhas=("nota_fiscal", "foto", "laudo", "outro"), padrao="nota_fiscal"),
]
CAMPOS_ITEM_RECEBIDO = [
    Campo("pedido_item_id", "uuid", obrigatorio=True, rotulo="Item"),
    Campo("quantidade_recebida", "decimal", obrigatorio=True, minimo=0, maximo=1_000_000, rotulo="Quantidade recebida"),
    Campo("quantidade_aceita", "decimal", obrigatorio=True, minimo=0, maximo=1_000_000, rotulo="Quantidade aceita"),
    Campo("motivo_divergencia", "texto", max_len=500, rotulo="Divergência"),
]


@bp.post("/pedidos/<uuid:pedido_id>/recebimentos")
@requer_login
def receber(pedido_id):
    exigir(g.usuario, "recebimento.registrar")
    corpo = corpo_json()
    dados = validar(corpo, CAMPOS_RECEBIMENTO)
    itens = lista_itens(corpo, CAMPOS_ITEM_RECEBIDO)
    max_mb = current_app.config["MAX_UPLOAD_MB"]
    arquivos = [validar_arquivo(f, max_mb) for f in request.files.getlist("arquivos") if f and f.filename]
    with LoteArquivos() as lote:
        with tx("Recebimento registrado") as cur:
            workflow.registrar_recebimento(cur, g.usuario, str(pedido_id), dados, itens, arquivos, lote,
                                           ip_cliente(), user_agent())
    with tx() as cur:
        return jsonify(carregar_pedido(cur, str(pedido_id))), 201


@bp.get("/recebimentos")
@requer_login
def listar_recebimentos():
    exigir(g.usuario, "recebimento.ver")
    args = validar(request.args.to_dict(), [Campo("situacao", "escolha", escolhas=tuple(SITUACAO_RECEBIMENTO)),
                                            Campo("q", "texto", max_len=120)])
    pagina, por_pagina = paginacao()
    where, params = ["true"], []
    if args.get("situacao"):
        where.append("r.situacao = %s")
        params.append(args["situacao"])
    if args.get("q"):
        termo = like(args["q"])
        where.append("(r.codigo ilike %s or r.nota_fiscal ilike %s or r.pedido_codigo ilike %s or r.fornecedor_nome ilike %s)")
        params += [termo] * 4
    clausula = " and ".join(where)
    with tx() as cur:
        cur.execute(f"select count(*) as n from rg.v_recebimentos r where {clausula}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"select * from rg.v_recebimentos r where {clausula} order by r.recebido_em desc limit %s offset %s",
                    (*params, por_pagina, (pagina - 1) * por_pagina))
        itens = cur.fetchall()
    return jsonify({"itens": itens, "total": total, "pagina": pagina, "por_pagina": por_pagina})
