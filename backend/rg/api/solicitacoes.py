"""Solicitações de compras, orçamentos e contratações com workflow de aprovação."""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from ..errors import ApiError, NaoEncontrado, ValidacaoError
from ..rotulos import SLA_SITUACAO, STATUS_SOLICITACAO, TIPO_SOLICITACAO, URGENCIA
from ..seguranca.sessao import ip_cliente, registrar_evento, requer_login, requer_papel, tx, user_agent
from ..servicos import pdf, workflow
from ..servicos.arquivos import LoteArquivos, inserir_anexo, validar_arquivo
from ..servicos.ocr import fila_ocr
from ..validacao import Campo, validar
from ._util import corpo_json, paginacao, resposta_csv, resposta_pdf

bp = Blueprint("solicitacoes", __name__)

CAMPOS_SOLICITACAO = [
    Campo("tipo", "escolha", obrigatorio=True, escolhas=tuple(TIPO_SOLICITACAO), rotulo="Tipo"),
    Campo("titulo", "texto", obrigatorio=True, min_len=5, max_len=160, rotulo="Título"),
    Campo("descricao", "texto", obrigatorio=True, min_len=10, max_len=5000, rotulo="Descrição"),
    Campo("justificativa", "texto", obrigatorio=True, min_len=20, max_len=5000, rotulo="Justificativa"),
    Campo("urgencia", "escolha", escolhas=tuple(URGENCIA), padrao="normal", rotulo="Urgência"),
    Campo("valor_estimado", "decimal", minimo=0, maximo=999_999_999_999, rotulo="Valor estimado"),
    Campo("tipo_documento", "escolha", escolhas=("orcamento", "nota_fiscal", "laudo", "outro"),
          padrao="orcamento", rotulo="Tipo de documento"),
]
ORDENACOES = {
    "recentes": "v.criado_em desc",
    "antigas": "v.criado_em asc",
    "sla": "case when v.sla_concluido_em is null then 0 else 1 end, v.sla_prazo_limite asc",
    "valor": "coalesce(v.valor_final_aprovado, v.valor_estimado) desc nulls last",
    "urgencia": "array_position(array['imediato','urgente','normal'], v.urgencia::text), v.sla_prazo_limite",
}
FILA_POR_PAPEL = {
    "admin": ("aguardando_adm",),
    "compras": ("aprovado_adm", "em_cotacao"),
    "gestor": ("necessita_nova_cotacao",),
}


def _arquivos(campo: str = "arquivos") -> list:
    max_mb = current_app.config["MAX_UPLOAD_MB"]
    return [validar_arquivo(f, max_mb, campo) for f in request.files.getlist(campo) if f and f.filename]


def _filtros():
    args = validar(request.args.to_dict(), [
        Campo("status", "texto", max_len=200),
        Campo("setor", "texto", max_len=40),
        Campo("urgencia", "escolha", escolhas=tuple(URGENCIA)),
        Campo("tipo", "escolha", escolhas=tuple(TIPO_SOLICITACAO)),
        Campo("sla", "escolha", escolhas=tuple(SLA_SITUACAO)),
        Campo("q", "texto", max_len=120),
        Campo("inicio", "data"),
        Campo("fim", "data"),
        Campo("fila", "bool"),
        Campo("ordem", "escolha", escolhas=tuple(ORDENACOES), padrao="recentes"),
    ])
    where, params = ["true"], []
    if args.get("fila"):
        where.append("v.status = any(%s::rg.status_solicitacao[])")
        params.append(list(FILA_POR_PAPEL[g.usuario["papel"]]))
    if args.get("status"):
        status = [s for s in args["status"].split(",") if s in STATUS_SOLICITACAO]
        if status:
            where.append("v.status = any(%s::rg.status_solicitacao[])")
            params.append(status)
    for campo, coluna in (("setor", "setor_codigo"), ("urgencia", "urgencia"), ("tipo", "tipo"),
                          ("sla", "sla_situacao")):
        if args.get(campo):
            where.append(f"v.{coluna} = %s")
            params.append(args[campo])
    if args.get("inicio"):
        where.append("(v.criado_em at time zone %s)::date >= %s")
        params += [current_app.config["TIMEZONE"], args["inicio"]]
    if args.get("fim"):
        where.append("(v.criado_em at time zone %s)::date <= %s")
        params += [current_app.config["TIMEZONE"], args["fim"]]
    if args.get("q"):
        termo = args["q"]
        where.append("(v.codigo ilike %s or v.titulo ilike %s or v.gestor_nome ilike %s"
                     " or to_tsvector('portuguese', v.titulo || ' ' || v.descricao) @@ plainto_tsquery('portuguese', %s))")
        like = "%" + termo.replace("%", r"\%").replace("_", r"\_") + "%"
        params += [like, like, like, termo]
    return " and ".join(where), params, ORDENACOES[args.get("ordem") or "recentes"], args


COLUNAS_LISTA = """v.id, v.codigo, v.tipo, v.titulo, v.setor_codigo, v.setor_nome, v.setor_cor, v.urgencia, v.status,
                   v.valor_estimado, v.valor_final_aprovado, v.gestor_nome, v.comprador_nome, v.criado_em,
                   v.atualizado_em, v.sla_prazo_limite, v.sla_situacao, v.sla_horas_restantes, v.rodada_cotacao"""


@bp.get("/solicitacoes")
@requer_login
def listar():
    clausula, params, ordem, _ = _filtros()
    pagina, por_pagina = paginacao()
    with tx() as cur:
        cur.execute(f"select count(*) as n from rg.v_solicitacoes v where {clausula}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"select {COLUNAS_LISTA} from rg.v_solicitacoes v where {clausula} order by {ordem}"
                    " limit %s offset %s", (*params, por_pagina, (pagina - 1) * por_pagina))
        itens = cur.fetchall()
    return jsonify({"itens": itens, "total": total, "pagina": pagina, "por_pagina": por_pagina})


@bp.get("/solicitacoes/exportar.csv")
@requer_login
def exportar_csv():
    clausula, params, ordem, _ = _filtros()
    with tx() as cur:
        cur.execute(f"select {COLUNAS_LISTA} from rg.v_solicitacoes v where {clausula} order by {ordem} limit 20000",
                    params)
        linhas = cur.fetchall()
        registrar_evento(cur, "EXPORTACAO_CSV", "rg.solicitacoes", None, {"registros": len(linhas)})
    return resposta_csv("solicitacoes-rg-hospital.csv",
                        ["Código", "Tipo", "Título", "Setor", "Urgência", "Status", "SLA", "Prazo SLA",
                         "Gestor", "Comprador", "Valor estimado", "Valor homologado", "Abertura"],
                        [[l["codigo"], TIPO_SOLICITACAO[l["tipo"]], l["titulo"], l["setor_nome"], URGENCIA[l["urgencia"]],
                          STATUS_SOLICITACAO[l["status"]], SLA_SITUACAO[l["sla_situacao"]],
                          pdf.data_hora(l["sla_prazo_limite"]), l["gestor_nome"], l["comprador_nome"],
                          _num(l["valor_estimado"]), _num(l["valor_final_aprovado"]), pdf.data_hora(l["criado_em"])]
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
    if args.get("setor"):
        partes.append(f"Setor: {args['setor']}")
    if args.get("status"):
        partes.append("Status: " + ", ".join(STATUS_SOLICITACAO.get(s, s) for s in args["status"].split(",")))
    if args.get("urgencia"):
        partes.append(f"Urgência: {URGENCIA[args['urgencia']]}")
    if args.get("sla"):
        partes.append(f"SLA: {SLA_SITUACAO[args['sla']]}")
    if args.get("q"):
        partes.append(f"Busca: {args['q']}")
    return " · ".join(partes) or "Todos os registros acessíveis ao usuário"


def _num(v):
    return "" if v is None else f"{v:.2f}".replace(".", ",")


@bp.post("/solicitacoes")
@requer_papel("gestor")
def criar():
    dados = validar(corpo_json(), CAMPOS_SOLICITACAO)
    arquivos = _arquivos()
    if len(arquivos) > workflow.MAX_ANEXOS:
        raise ValidacaoError({"arquivos": f"Envie no máximo {workflow.MAX_ANEXOS} anexos"})
    with LoteArquivos() as lote:
        with tx("Solicitação criada e assinada pelo gestor") as cur:
            solicitacao_id, anexos = workflow.criar(cur, g.usuario, dados, arquivos, lote, ip_cliente(), user_agent())
    fila_ocr.enfileirar(anexos)
    with tx() as cur:
        detalhe = workflow.carregar_detalhe(cur, solicitacao_id)
    return jsonify(_resposta_detalhe(detalhe)), 201


def _resposta_detalhe(detalhe: dict) -> dict:
    detalhe["acoes"] = workflow.acoes_disponiveis(g.usuario, detalhe["solicitacao"])
    return detalhe


@bp.get("/solicitacoes/<uuid:solicitacao_id>")
@requer_login
def detalhar(solicitacao_id):
    with tx() as cur:
        detalhe = workflow.carregar_detalhe(cur, str(solicitacao_id))
    return jsonify(_resposta_detalhe(detalhe))


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


@bp.post("/solicitacoes/<uuid:solicitacao_id>/acoes/<acao>")
@requer_login
def executar_acao(solicitacao_id, acao: str):
    sid = str(solicitacao_id)
    dados = corpo_json()
    comum = validar(dados, [Campo("versao", "inteiro", minimo=1), Campo("texto", "texto", max_len=2000)])
    versao, texto = comum.get("versao"), comum.get("texto")
    papel = g.usuario["papel"]
    ip, ua = ip_cliente(), user_agent()
    novos_anexos: list[str] = []

    exigido = {"adm_aprovar": "admin", "adm_rejeitar": "admin", "adm_nova_cotacao": "admin", "adm_urgencia": "admin",
               "gestor_reenviar": "gestor", "gestor_cancelar": "gestor", "compras_iniciar": "compras",
               "compras_homologar": "compras", "compras_rejeitar": "compras"}
    if acao not in exigido:
        raise NaoEncontrado("Ação inexistente")
    if papel != exigido[acao]:
        raise ApiError("Seu perfil não pode executar esta ação", 403, "proibido")

    if acao == "gestor_reenviar":
        edicao = validar(dados, [c for c in CAMPOS_SOLICITACAO if c.nome not in ("urgencia",)], parcial=True)
        edicao = {k: v for k, v in edicao.items() if v is not None}
        remover = validar(dados, [Campo("remover_anexos", "lista_uuid")]).get("remover_anexos") or []
        arquivos = _arquivos()
        edicao["observacao"] = texto
        with LoteArquivos() as lote:
            with tx() as cur:
                novos_anexos = workflow.gestor_reenviar(cur, g.usuario, sid, edicao, arquivos, remover, lote,
                                                        versao, ip, ua)
    else:
        with tx() as cur:
            if acao == "adm_aprovar":
                workflow.adm_decidir(cur, g.usuario, sid, "aprovar", texto, versao, ip, ua)
            elif acao == "adm_rejeitar":
                workflow.adm_decidir(cur, g.usuario, sid, "rejeitar", texto, versao, ip, ua)
            elif acao == "adm_nova_cotacao":
                workflow.adm_decidir(cur, g.usuario, sid, "nova_cotacao", texto, versao, ip, ua)
            elif acao == "adm_urgencia":
                urg = validar(dados, [Campo("urgencia", "escolha", obrigatorio=True, escolhas=tuple(URGENCIA),
                                            rotulo="Urgência")])
                workflow.adm_alterar_urgencia(cur, sid, urg["urgencia"], texto, versao)
            elif acao == "gestor_cancelar":
                workflow.gestor_cancelar(cur, sid, texto, versao)
            elif acao == "compras_iniciar":
                workflow.compras_iniciar(cur, sid, versao)
            elif acao == "compras_homologar":
                h = validar(dados, [Campo("cotacao_id", "uuid", obrigatorio=True, rotulo="Cotação vencedora"),
                                    Campo("valor_final", "decimal", minimo=0.01, rotulo="Valor final")])
                workflow.compras_homologar(cur, g.usuario, sid, h["cotacao_id"], h.get("valor_final"), texto,
                                           versao, ip, ua)
            elif acao == "compras_rejeitar":
                workflow.compras_rejeitar(cur, g.usuario, sid, texto, versao, ip, ua)
    fila_ocr.enfileirar(novos_anexos)
    with tx() as cur:
        detalhe = workflow.carregar_detalhe(cur, sid)
    return jsonify(_resposta_detalhe(detalhe))


@bp.post("/solicitacoes/<uuid:solicitacao_id>/anexos")
@requer_login
def anexar(solicitacao_id):
    """Gestor: anexa enquanto aguarda a Administração. Compras: propostas durante a cotação."""
    sid = str(solicitacao_id)
    dados = validar(corpo_json(), [Campo("tipo_documento", "escolha",
                                         escolhas=("orcamento", "nota_fiscal", "laudo", "cotacao", "outro"),
                                         padrao="orcamento")])
    arquivos = _arquivos()
    if not arquivos:
        raise ValidacaoError({"arquivos": "Selecione ao menos um arquivo"})
    papel = g.usuario["papel"]
    if papel not in ("gestor", "compras"):
        raise ApiError("Seu perfil não pode anexar documentos nesta etapa", 403, "proibido")
    origem = "solicitante" if papel == "gestor" else "compras"
    with LoteArquivos() as lote:
        with tx() as cur:
            cur.execute("select status, rodada_cotacao from rg.solicitacoes where id = %s", (sid,))
            s = cur.fetchone()
            if not s:
                raise NaoEncontrado()
            if origem == "solicitante" and s["status"] not in ("aguardando_adm",):
                raise ApiError("Para enviar novos orçamentos após devolução, use a ação de reenvio", 422,
                               "status_invalido")
            if origem == "compras" and s["status"] != "em_cotacao":
                raise ApiError("Propostas só podem ser anexadas durante a cotação", 422, "status_invalido")
            ids = [inserir_anexo(cur, lote, a, usuario_id=g.usuario["id"], origem=origem,
                                 tipo_documento=dados.get("tipo_documento") or "orcamento", solicitacao_id=sid,
                                 rodada=s["rodada_cotacao"]) for a in arquivos]
    fila_ocr.enfileirar(ids)
    with tx() as cur:
        detalhe = workflow.carregar_detalhe(cur, sid)
    return jsonify(_resposta_detalhe(detalhe)), 201


# ---------------------------------------------------------------------------
# Cotações
# ---------------------------------------------------------------------------
CAMPOS_COTACAO = [
    Campo("fornecedor_id", "uuid", obrigatorio=True, rotulo="Fornecedor"),
    Campo("valor", "decimal", obrigatorio=True, minimo=0.01, maximo=999_999_999_999, rotulo="Valor"),
    Campo("prazo_entrega_dias", "inteiro", obrigatorio=True, minimo=0, maximo=3650, rotulo="Prazo de entrega"),
    Campo("condicoes_pagamento", "texto", max_len=300, rotulo="Condições de pagamento"),
    Campo("validade_proposta", "data", rotulo="Validade da proposta"),
    Campo("observacoes", "texto", max_len=2000, rotulo="Observações"),
    Campo("anexo_id", "uuid", rotulo="Documento da proposta"),
]


@bp.post("/solicitacoes/<uuid:solicitacao_id>/cotacoes")
@requer_papel("compras")
def criar_cotacao(solicitacao_id):
    sid = str(solicitacao_id)
    dados = validar(corpo_json(), CAMPOS_COTACAO)
    with tx() as cur:
        cur.execute("select status from rg.solicitacoes where id = %s", (sid,))
        s = cur.fetchone()
        if not s:
            raise NaoEncontrado()
        if s["status"] != "em_cotacao":
            raise ApiError("Inicie a cotação antes de lançar propostas", 422, "status_invalido")
        if dados.get("anexo_id"):
            _checar_anexo(cur, dados["anexo_id"], sid)
        cur.execute(
            """insert into rg.cotacoes (solicitacao_id, fornecedor_id, anexo_id, valor, prazo_entrega_dias,
                                        condicoes_pagamento, validade_proposta, observacoes, criado_por)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
            (sid, dados["fornecedor_id"], dados.get("anexo_id"), dados["valor"], dados["prazo_entrega_dias"],
             dados.get("condicoes_pagamento"), dados.get("validade_proposta"), dados.get("observacoes"),
             g.usuario["id"]),
        )
        detalhe = workflow.carregar_detalhe(cur, sid)
    return jsonify(_resposta_detalhe(detalhe)), 201


def _checar_anexo(cur, anexo_id: str, sid: str) -> None:
    cur.execute("select 1 from rg.anexos where id = %s and solicitacao_id = %s and removido_em is null",
                (anexo_id, sid))
    if not cur.fetchone():
        raise ValidacaoError({"anexo_id": "Documento não pertence a esta solicitação"})


@bp.patch("/cotacoes/<uuid:cotacao_id>")
@requer_papel("compras")
def atualizar_cotacao(cotacao_id):
    dados = validar(corpo_json(), [c for c in CAMPOS_COTACAO if c.nome != "fornecedor_id"], parcial=True)
    with tx() as cur:
        cur.execute("select solicitacao_id from rg.cotacoes where id = %s", (str(cotacao_id),))
        c = cur.fetchone()
        if not c:
            raise NaoEncontrado("Cotação não encontrada")
        sid = str(c["solicitacao_id"])
        if dados.get("anexo_id"):
            _checar_anexo(cur, dados["anexo_id"], sid)
        obrigatorios = {"valor", "prazo_entrega_dias"}
        for campo in obrigatorios & dados.keys():
            if dados[campo] is None:
                raise ValidacaoError({campo: "Campo obrigatório"})
        if dados:
            sets = ", ".join(f"{k} = %s" for k in dados)
            cur.execute(f"update rg.cotacoes set {sets} where id = %s", (*dados.values(), str(cotacao_id)))
            if cur.rowcount != 1:
                raise ApiError("Cotação não pode mais ser alterada", 422, "status_invalido")
        detalhe = workflow.carregar_detalhe(cur, sid)
    return jsonify(_resposta_detalhe(detalhe))


@bp.delete("/cotacoes/<uuid:cotacao_id>")
@requer_papel("compras")
def remover_cotacao(cotacao_id):
    with tx() as cur:
        cur.execute("delete from rg.cotacoes where id = %s returning solicitacao_id", (str(cotacao_id),))
        c = cur.fetchone()
        if not c:
            raise ApiError("Cotação não encontrada ou não pode mais ser removida", 422, "status_invalido")
        detalhe = workflow.carregar_detalhe(cur, str(c["solicitacao_id"]))
    return jsonify(_resposta_detalhe(detalhe))


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
