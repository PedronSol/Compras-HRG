"""Solicitações de compra: abertura com itens, aprovações, cotação (propostas manuais) e emissão do pedido."""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..errors import ApiError, NaoEncontrado, ValidacaoError
from ..permissoes import exigir, pode
from ..rotulos import SLA_SITUACAO, STATUS_SOLICITACAO, TIPO_SOLICITACAO, UNIDADES, URGENCIA
from ..seguranca.sessao import ip_cliente, registrar_evento, requer_login, tx, user_agent
from ..servicos import pdf, workflow
from ..servicos.arquivos import LoteArquivos, inserir_anexo, validar_arquivo
from ..validacao import Campo, validar
from ._util import corpo_json, like, lista_itens, paginacao, resposta_csv, resposta_pdf

bp = Blueprint("solicitacoes", __name__)

CAMPOS_SOLICITACAO = [
    Campo("tipo", "escolha", obrigatorio=True, escolhas=tuple(TIPO_SOLICITACAO), rotulo="Tipo"),
    Campo("titulo", "texto", obrigatorio=True, min_len=5, max_len=160, rotulo="Título"),
    Campo("descricao", "texto", max_len=5000, rotulo="Descrição"),
    Campo("justificativa", "texto", obrigatorio=True, min_len=20, max_len=5000, rotulo="Justificativa"),
    Campo("urgencia", "escolha", escolhas=tuple(URGENCIA), padrao="normal", rotulo="Urgência"),
    Campo("local_entrega", "texto", max_len=160, rotulo="Local de entrega"),
    Campo("data_necessidade", "data", rotulo="Data de necessidade"),
    Campo("tipo_documento", "escolha", escolhas=("orcamento", "proposta", "laudo", "foto", "outro"),
          padrao="orcamento", rotulo="Tipo de documento"),
]
CAMPOS_ITEM = [
    Campo("material_id", "uuid", rotulo="Material"),
    Campo("descricao", "texto", max_len=300, rotulo="Descrição"),
    Campo("unidade", "escolha", escolhas=tuple(UNIDADES), rotulo="Unidade"),
    Campo("quantidade", "decimal", obrigatorio=True, minimo=0.001, maximo=1_000_000, rotulo="Quantidade"),
    Campo("valor_unitario_estimado", "decimal", minimo=0, maximo=999_999_999, rotulo="Valor unitário estimado"),
    Campo("observacao", "texto", max_len=500, rotulo="Observação"),
]
CAMPOS_PROPOSTA = [
    Campo("fornecedor_id", "uuid", obrigatorio=True, rotulo="Fornecedor"),
    Campo("numero_proposta", "texto", max_len=60, rotulo="Nº da proposta"),
    Campo("data_proposta", "data", rotulo="Data da proposta"),
    Campo("validade_proposta", "data", rotulo="Validade"),
    Campo("prazo_entrega_dias", "inteiro", obrigatorio=True, minimo=0, maximo=3650, rotulo="Prazo de entrega"),
    Campo("condicoes_pagamento", "texto", max_len=300, rotulo="Condições de pagamento"),
    Campo("frete", "decimal", minimo=0, maximo=999_999_999, rotulo="Frete"),
    Campo("desconto", "decimal", minimo=0, maximo=999_999_999, rotulo="Desconto"),
    Campo("observacoes", "texto", max_len=2000, rotulo="Observações"),
    Campo("anexo_id", "uuid", rotulo="Documento da proposta"),
]
CAMPOS_ITEM_PROPOSTA = [
    Campo("solicitacao_item_id", "uuid", obrigatorio=True, rotulo="Item"),
    Campo("quantidade", "decimal", obrigatorio=True, minimo=0.001, maximo=1_000_000, rotulo="Quantidade"),
    Campo("valor_unitario", "decimal", obrigatorio=True, minimo=0, maximo=999_999_999, rotulo="Valor unitário"),
    Campo("marca", "texto", max_len=120, rotulo="Marca"),
    Campo("observacao", "texto", max_len=300, rotulo="Observação"),
]
ORDENACOES = {
    "recentes": "v.criado_em desc",
    "antigas": "v.criado_em asc",
    "sla": "case when v.sla_concluido_em is null then 0 else 1 end, v.sla_prazo_limite asc",
    "valor": "coalesce(v.valor_final, v.valor_estimado) desc nulls last",
    "urgencia": "array_position(array['imediato','urgente','normal'], v.urgencia::text), v.sla_prazo_limite",
}
ETAPAS = {
    "aprovacao": ("aguardando_gestor", "aguardando_diretoria", "devolvida"),
    "cotacao": ("aprovada", "em_cotacao"),
    "fornecedor": ("aguardando_pedido",),
    "pedido": ("em_pedido",),
    "recebimento": ("recebida_parcial",),
    "abertas": ("aguardando_gestor", "aguardando_diretoria", "devolvida", "aprovada", "em_cotacao",
                "aguardando_pedido", "em_pedido", "recebida_parcial"),
    "encerradas": ("concluida", "reprovada", "cancelada"),
}


def fila_sql(usuario: dict) -> tuple[str, list]:
    """Condição SQL das solicitações que aguardam uma ação do usuário."""
    papel = usuario["papel"]
    if papel == "gestor":
        return ("(v.status = 'aguardando_gestor' and v.setor_codigo = %s and v.solicitante_id <> %s)",
                [usuario["setor_codigo"], usuario["id"]])
    if papel == "diretoria":
        return "v.status = 'aguardando_diretoria'", []
    if papel == "solicitante":
        return "(v.status = 'devolvida' and v.setor_codigo = %s)", [usuario["setor_codigo"]]
    if papel == "comprador":
        return ("(v.status = 'aprovada' or (v.status in ('em_cotacao', 'aguardando_pedido')"
                " and (v.comprador_id = %s or v.comprador_id is null)))", [usuario["id"]])
    return "false", []


def _arquivos(campo: str = "arquivos") -> list:
    max_mb = current_app.config["MAX_UPLOAD_MB"]
    return [validar_arquivo(f, max_mb, campo) for f in request.files.getlist(campo) if f and f.filename]


def _filtros():
    args = validar(request.args.to_dict(), [
        Campo("status", "texto", max_len=300),
        Campo("etapa", "escolha", escolhas=tuple(ETAPAS)),
        Campo("setor", "texto", max_len=40),
        Campo("urgencia", "escolha", escolhas=tuple(URGENCIA)),
        Campo("tipo", "escolha", escolhas=tuple(TIPO_SOLICITACAO)),
        Campo("sla", "escolha", escolhas=tuple(SLA_SITUACAO)),
        Campo("q", "texto", max_len=120),
        Campo("inicio", "data"),
        Campo("fim", "data"),
        Campo("fila", "bool"),
        Campo("minhas", "bool"),
        Campo("ordem", "escolha", escolhas=tuple(ORDENACOES), padrao="recentes"),
    ])
    where, params = ["true"], []
    if args.get("fila"):
        condicao, p = fila_sql(g.usuario)
        where.append(condicao)
        params += p
    if args.get("minhas"):
        where.append("(v.solicitante_id = %s or v.comprador_id = %s)")
        params += [g.usuario["id"], g.usuario["id"]]
    if args.get("etapa"):
        where.append("v.status = any(%s::rg.status_solicitacao[])")
        params.append(list(ETAPAS[args["etapa"]]))
    if args.get("status"):
        status = [s for s in args["status"].split(",") if s in STATUS_SOLICITACAO]
        if status:
            where.append("v.status = any(%s::rg.status_solicitacao[])")
            params.append(status)
    for campo, coluna in (("setor", "setor_codigo"), ("urgencia", "urgencia"), ("tipo", "tipo"), ("sla", "sla_situacao")):
        if args.get(campo):
            where.append(f"v.{coluna} = %s")
            params.append(args[campo])
    tz = current_app.config["TIMEZONE"]
    if args.get("inicio"):
        where.append("(v.criado_em at time zone %s)::date >= %s")
        params += [tz, args["inicio"]]
    if args.get("fim"):
        where.append("(v.criado_em at time zone %s)::date <= %s")
        params += [tz, args["fim"]]
    if args.get("q"):
        termo = like(args["q"])
        where.append("(v.codigo ilike %s or v.titulo ilike %s or v.solicitante_nome ilike %s or v.pedido_codigo ilike %s"
                     " or v.fornecedor_nome ilike %s"
                     " or to_tsvector('portuguese', v.titulo || ' ' || coalesce(v.descricao, '')) @@ plainto_tsquery('portuguese', %s))")
        params += [termo, termo, termo, termo, termo, args["q"]]
    return " and ".join(where), params, ORDENACOES[args.get("ordem") or "recentes"], args


COLUNAS_LISTA = """v.id, v.codigo, v.tipo, v.titulo, v.setor_codigo, v.setor_nome, v.setor_cor, v.urgencia, v.status,
                   v.valor_estimado, v.valor_final, v.solicitante_nome, v.comprador_nome, v.criado_em, v.atualizado_em,
                   v.sla_prazo_limite, v.sla_situacao, v.sla_horas_restantes, v.rodada, v.itens_qtd, v.cotacoes_qtd,
                   v.fornecedor_nome, v.fornecedor_fantasia, v.pedido_id, v.pedido_codigo, v.pedido_status,
                   v.pedido_previsao, v.data_necessidade"""


@bp.get("/solicitacoes")
@requer_login
def listar():
    clausula, params, ordem, _ = _filtros()
    pagina, por_pagina = paginacao()
    with tx() as cur:
        cur.execute(f"select count(*) as n, coalesce(sum(coalesce(v.valor_final, v.valor_estimado)), 0) as valor"
                    f" from rg.v_solicitacoes v where {clausula}", params)
        agregado = cur.fetchone()
        cur.execute(f"select {COLUNAS_LISTA} from rg.v_solicitacoes v where {clausula} order by {ordem}"
                    " limit %s offset %s", (*params, por_pagina, (pagina - 1) * por_pagina))
        itens = cur.fetchall()
    return jsonify({"itens": itens, "total": agregado["n"], "valor_total": agregado["valor"], "pagina": pagina,
                    "por_pagina": por_pagina})


@bp.get("/solicitacoes/contagem")
@requer_login
def contagem():
    """Quantidade por etapa (abas da listagem) e pendências do usuário."""
    condicao, p = fila_sql(g.usuario)
    with tx() as cur:
        cur.execute(f"""select v.status, count(*) as n from rg.v_solicitacoes v group by v.status""")
        por_status = {r["status"]: r["n"] for r in cur.fetchall()}
        cur.execute(f"select count(*) as n from rg.v_solicitacoes v where {condicao}", p)
        fila = cur.fetchone()["n"]
    etapas = {nome: sum(por_status.get(s, 0) for s in lista) for nome, lista in ETAPAS.items()}
    return jsonify({"por_status": por_status, "etapas": etapas, "total": sum(por_status.values()), "fila": fila})


@bp.get("/solicitacoes/exportar.csv")
@requer_login
def exportar_csv():
    clausula, params, ordem, _ = _filtros()
    with tx() as cur:
        cur.execute(f"select {COLUNAS_LISTA} from rg.v_solicitacoes v where {clausula} order by {ordem} limit 20000",
                    params)
        linhas = cur.fetchall()
        registrar_evento(cur, "EXPORTACAO_CSV", "rg.solicitacoes", None, {"registros": len(linhas)})
    return resposta_csv("solicitacoes-compras-hrg.csv",
                        ["Código", "Tipo", "Título", "Setor", "Urgência", "Status", "Prazo de atendimento", "Solicitante",
                         "Comprador", "Fornecedor", "Pedido", "Valor estimado", "Valor contratado", "Abertura"],
                        [[l["codigo"], TIPO_SOLICITACAO[l["tipo"]], l["titulo"], l["setor_nome"], URGENCIA[l["urgencia"]],
                          STATUS_SOLICITACAO[l["status"]], SLA_SITUACAO[l["sla_situacao"]], l["solicitante_nome"],
                          l["comprador_nome"], l["fornecedor_nome"], l["pedido_codigo"], _num(l["valor_estimado"]),
                          _num(l["valor_final"]), pdf.data_hora(l["criado_em"])]
                         for l in linhas])


@bp.get("/solicitacoes/relatorio.pdf")
@requer_login
def relatorio_pdf():
    clausula, params, ordem, args = _filtros()
    with tx() as cur:
        cur.execute(f"select {COLUNAS_LISTA} from rg.v_solicitacoes v where {clausula} order by {ordem} limit 5000",
                    params)
        linhas = cur.fetchall()
        descricao = _descrever_filtros(args)
        conteudo, codigo = pdf.relatorio_solicitacoes(linhas, descricao, autor=g.usuario["nome"],
                                                      instituicao=current_app.config["INSTITUICAO"],
                                                      tz=current_app.config["TIMEZONE"])
        registrar_evento(cur, "RELATORIO_GERADO", "relatorios", "solicitacoes",
                         {"codigo_verificacao": codigo, "registros": len(linhas), "filtros": descricao})
    return resposta_pdf(conteudo, "relatorio-solicitacoes.pdf")


def _descrever_filtros(args: dict) -> str:
    partes = []
    if args.get("inicio") or args.get("fim"):
        ini = args["inicio"].strftime("%d/%m/%Y") if args.get("inicio") else "início"
        fim = args["fim"].strftime("%d/%m/%Y") if args.get("fim") else "hoje"
        partes.append(f"Período: {ini} a {fim}")
    if args.get("etapa"):
        partes.append(f"Etapa: {args['etapa']}")
    if args.get("setor"):
        partes.append(f"Setor: {args['setor']}")
    if args.get("status"):
        partes.append("Status: " + ", ".join(STATUS_SOLICITACAO.get(s, s) for s in args["status"].split(",")))
    if args.get("urgencia"):
        partes.append(f"Urgência: {URGENCIA[args['urgencia']]}")
    if args.get("q"):
        partes.append(f"Busca: {args['q']}")
    return " · ".join(partes) or "Todos os registros acessíveis ao usuário"


def _num(v):
    return "" if v is None else f"{v:.2f}".replace(".", ",")


def _resposta_detalhe(detalhe: dict) -> dict:
    detalhe["acoes"] = workflow.acoes_disponiveis(g.usuario, detalhe["solicitacao"])
    for p in detalhe["pedidos"]:
        p["acoes"] = workflow.acoes_pedido(g.usuario, p)
    return detalhe


def _carregar(sid: str) -> dict:
    with tx() as cur:
        return _resposta_detalhe(workflow.carregar_detalhe(cur, sid))


def _detalhe(sid: str, status: int = 200):
    return jsonify(_carregar(sid)), status


@bp.post("/solicitacoes")
@requer_login
def criar():
    exigir(g.usuario, "solicitacao.criar")
    corpo = corpo_json()
    dados = validar(corpo, CAMPOS_SOLICITACAO)
    itens = lista_itens(corpo, CAMPOS_ITEM)
    arquivos = _arquivos()
    with LoteArquivos() as lote:
        with tx("Solicitação aberta e assinada") as cur:
            sid = workflow.criar(cur, g.usuario, dados, itens, arquivos, lote, ip_cliente(), user_agent())
    return _detalhe(sid, 201)


@bp.get("/solicitacoes/<uuid:solicitacao_id>")
@requer_login
def detalhar(solicitacao_id):
    return _detalhe(str(solicitacao_id))


@bp.get("/solicitacoes/<uuid:solicitacao_id>/dossie.pdf")
@requer_login
def dossie(solicitacao_id):
    with tx() as cur:
        detalhe = workflow.carregar_detalhe(cur, str(solicitacao_id))
        conteudo, codigo = pdf.dossie_solicitacao(detalhe, autor=g.usuario["nome"],
                                                  instituicao=current_app.config["INSTITUICAO"],
                                                  tz=current_app.config["TIMEZONE"])
        registrar_evento(cur, "RELATORIO_GERADO", "rg.solicitacoes", str(solicitacao_id),
                         {"codigo_verificacao": codigo, "tipo": "dossie"})
    return resposta_pdf(conteudo, f"dossie-{detalhe['solicitacao']['codigo']}.pdf",
                        inline=request.args.get("inline") == "1")


ACOES = {
    "aprovar": "aprovacao", "devolver": "aprovacao", "reprovar": "aprovacao",
    "reenviar": "solicitacao.criar", "cancelar": "solicitacao.cancelar",
    "iniciar_cotacao": "cotacao.gerenciar", "definir_fornecedor": "cotacao.gerenciar",
    "reabrir_cotacao": "cotacao.gerenciar", "emitir_pedido": "pedido.emitir",
}


@bp.post("/solicitacoes/<uuid:solicitacao_id>/acoes/<acao>")
@requer_login
def executar_acao(solicitacao_id, acao: str):
    sid = str(solicitacao_id)
    if acao not in ACOES:
        raise NaoEncontrado("Ação inexistente")
    u = g.usuario
    if ACOES[acao] == "aprovacao":
        if not (pode(u, "solicitacao.aprovar_gestor") or pode(u, "solicitacao.aprovar_diretoria")):
            raise ApiError("Seu perfil não pode executar esta ação", 403, "proibido")
    elif not pode(u, ACOES[acao]):
        raise ApiError("Seu perfil não pode executar esta ação", 403, "proibido")
    corpo = corpo_json()
    comum = validar(corpo, [Campo("versao", "inteiro", minimo=1), Campo("texto", "texto", max_len=2000)])
    versao, texto = comum.get("versao"), comum.get("texto")
    ip, ua = ip_cliente(), user_agent()
    pedido_id = None

    if acao == "reenviar":
        edicao = validar(corpo, [c for c in CAMPOS_SOLICITACAO], parcial=True)
        itens = lista_itens(corpo, CAMPOS_ITEM, obrigatorio=False)
        remover = validar(corpo, [Campo("remover_anexos", "lista_uuid")]).get("remover_anexos") or []
        edicao["observacao"] = texto
        with LoteArquivos() as lote:
            with tx() as cur:
                workflow.reenviar(cur, u, sid, edicao, itens, _arquivos(), remover, lote, versao, ip, ua)
    else:
        with tx() as cur:
            if acao in ("aprovar", "devolver", "reprovar"):
                workflow.decidir_aprovacao(cur, u, sid, acao, texto, versao, ip, ua)
            elif acao == "cancelar":
                workflow.cancelar(cur, u, sid, texto, versao, ip, ua)
            elif acao == "iniciar_cotacao":
                workflow.iniciar_cotacao(cur, sid, versao)
            elif acao == "definir_fornecedor":
                d = validar(corpo, [Campo("cotacao_id", "uuid", obrigatorio=True, rotulo="Proposta vencedora")])
                workflow.definir_fornecedor(cur, u, sid, d["cotacao_id"], texto, versao, ip, ua)
            elif acao == "reabrir_cotacao":
                workflow.reabrir_cotacao(cur, sid, texto, versao)
            elif acao == "emitir_pedido":
                d = validar(corpo, [Campo("condicoes_pagamento", "texto", max_len=300),
                                    Campo("local_entrega", "texto", max_len=160),
                                    Campo("observacoes", "texto", max_len=2000)])
                pedido_id = workflow.emitir_pedido(cur, u, sid, d, versao, ip, ua)
    dados = _carregar(sid)
    if pedido_id:
        dados["pedido_criado"] = pedido_id
    return jsonify(dados)


@bp.post("/solicitacoes/<uuid:solicitacao_id>/anexos")
@requer_login
def anexar(solicitacao_id):
    """Anexar ou fotografar documentos. O conteúdo é armazenado cifrado e nunca interpretado automaticamente."""
    sid = str(solicitacao_id)
    dados = validar(corpo_json(), [Campo("tipo_documento", "escolha",
                                         escolhas=("orcamento", "proposta", "nota_fiscal", "laudo", "foto", "outro"),
                                         padrao="orcamento")])
    arquivos = _arquivos()
    if not arquivos:
        raise ValidacaoError({"arquivos": "Selecione ao menos um arquivo"})
    papel = g.usuario["papel"]
    origem = {"solicitante": "solicitante", "gestor": "solicitante", "comprador": "comprador"}.get(papel)
    if not origem:
        raise ApiError("Seu perfil não pode anexar documentos nesta etapa", 403, "proibido")
    with LoteArquivos() as lote:
        with tx() as cur:
            cur.execute("select 1 from rg.solicitacoes where id = %s", (sid,))
            if not cur.fetchone():
                raise NaoEncontrado()
            ids = [inserir_anexo(cur, lote, a, usuario_id=g.usuario["id"], origem=origem,
                                 tipo_documento=dados.get("tipo_documento") or "orcamento", solicitacao_id=sid)
                   for a in arquivos]
    dados_resp = _carregar(sid)
    dados_resp["anexos_criados"] = ids
    return jsonify(dados_resp), 201


# ---------------------------------------------------------------------------
# Propostas de fornecedores (cotação) — preenchimento manual
# ---------------------------------------------------------------------------
@bp.post("/solicitacoes/<uuid:solicitacao_id>/propostas")
@requer_login
def criar_proposta(solicitacao_id):
    exigir(g.usuario, "cotacao.gerenciar")
    corpo = corpo_json()
    dados = validar(corpo, CAMPOS_PROPOSTA)
    itens = lista_itens(corpo, CAMPOS_ITEM_PROPOSTA)
    with tx("Proposta registrada") as cur:
        workflow.salvar_proposta(cur, g.usuario, str(solicitacao_id), dados, itens)
    return _detalhe(str(solicitacao_id), 201)


@bp.put("/propostas/<uuid:cotacao_id>")
@requer_login
def atualizar_proposta(cotacao_id):
    exigir(g.usuario, "cotacao.gerenciar")
    corpo = corpo_json()
    dados = validar(corpo, [c for c in CAMPOS_PROPOSTA if c.nome != "fornecedor_id"])
    itens = lista_itens(corpo, CAMPOS_ITEM_PROPOSTA)
    with tx() as cur:
        cur.execute("select solicitacao_id from rg.cotacoes where id = %s", (str(cotacao_id),))
        c = cur.fetchone()
        if not c:
            raise NaoEncontrado("Proposta não encontrada")
        sid = str(c["solicitacao_id"])
        workflow.salvar_proposta(cur, g.usuario, sid, dados, itens, cotacao_id=str(cotacao_id))
    return _detalhe(sid)


@bp.delete("/propostas/<uuid:cotacao_id>")
@requer_login
def remover_proposta(cotacao_id):
    exigir(g.usuario, "cotacao.gerenciar")
    with tx() as cur:
        sid = workflow.remover_proposta(cur, str(cotacao_id))
    return _detalhe(sid)


@bp.get("/assinaturas/<uuid:assinatura_id>/verificar")
@requer_login
def verificar_assinatura(assinatura_id):
    from ..servicos import assinaturas
    with tx() as cur:
        resultado = assinaturas.verificar(cur, str(assinatura_id))
        if not resultado:
            raise NaoEncontrado("Assinatura não encontrada")
        registrar_evento(cur, "VERIFICACAO_ASSINATURA", "rg.assinaturas", str(assinatura_id),
                         {"integra": resultado["registro_integro"]})
    return jsonify(resultado)
