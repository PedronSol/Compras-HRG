"""Serviços programados: manutenção, calibração, higienização, rondas e intervenções prediais."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from flask import Blueprint, current_app, g, jsonify, request

from ..errors import ApiError, NaoEncontrado, ValidacaoError
from ..rotulos import CATEGORIA_SERVICO, PERIODICIDADE, SITUACAO_SERVICO
from ..seguranca.sessao import registrar_evento, requer_login, requer_papel, tx
from ..servicos import pdf
from ..servicos.arquivos import LoteArquivos, inserir_anexo, validar_arquivo
from ..servicos.ocr import fila_ocr
from ..validacao import Campo, validar
from ._util import corpo_json, periodo, resposta_pdf

bp = Blueprint("servicos", __name__)

CAMPOS = [
    Campo("titulo", "texto", obrigatorio=True, min_len=5, max_len=160, rotulo="Título"),
    Campo("descricao", "texto", max_len=5000, rotulo="Descrição"),
    Campo("setor_codigo", "texto", obrigatorio=True, max_len=40, rotulo="Setor"),
    Campo("categoria", "escolha", obrigatorio=True, escolhas=tuple(CATEGORIA_SERVICO), rotulo="Categoria"),
    Campo("local", "texto", max_len=160, rotulo="Local"),
    Campo("data_programada", "data", obrigatorio=True, rotulo="Data"),
    Campo("hora_inicio", "hora", obrigatorio=True, rotulo="Início"),
    Campo("hora_termino", "hora", obrigatorio=True, rotulo="Término"),
    Campo("responsavel_executor", "texto", obrigatorio=True, min_len=3, max_len=120, rotulo="Responsável"),
    Campo("empresa_terceirizada", "texto", max_len=160, rotulo="Empresa terceirizada"),
    Campo("periodicidade", "escolha", escolhas=tuple(PERIODICIDADE), padrao="unica", rotulo="Periodicidade"),
]
EDITAVEIS = {c.nome for c in CAMPOS} - {"setor_codigo"}


def proxima_data(atual: date, periodicidade: str) -> date | None:
    dias = {"diaria": 1, "semanal": 7, "quinzenal": 14}
    meses = {"mensal": 1, "trimestral": 3, "semestral": 6, "anual": 12}
    if periodicidade in dias:
        return atual + timedelta(days=dias[periodicidade])
    if periodicidade in meses:
        total = atual.month - 1 + meses[periodicidade]
        ano, mes = atual.year + total // 12, total % 12 + 1
        return date(ano, mes, min(atual.day, calendar.monthrange(ano, mes)[1]))
    return None


def _obter(cur, servico_id: str) -> dict:
    cur.execute("select * from rg.v_servicos where id = %s", (servico_id,))
    s = cur.fetchone()
    if not s:
        raise NaoEncontrado("Serviço não encontrado ou fora do seu escopo de acesso")
    cur.execute("""select a.id, a.tipo_documento, a.nome_original, a.mime, a.tamanho, a.sha256, a.ocr_status,
                          a.dados_ocr, a.ocr_erro, a.criado_em, a.removido_em, u.nome as enviado_por_nome
                     from rg.anexos a left join rg.v_usuarios_publico u on u.id = a.enviado_por
                    where a.servico_id = %s and a.removido_em is null order by a.criado_em""", (servico_id,))
    s["anexos"] = cur.fetchall()
    s["pode_editar"] = s["situacao"] in ("agendado", "em_andamento") and (
        g.usuario["papel"] == "admin" or (g.usuario["papel"] == "gestor" and s["setor_codigo"] == g.usuario["setor_codigo"]))
    return s


def _validar_horario(dados: dict) -> None:
    if dados.get("hora_inicio") and dados.get("hora_termino") and dados["hora_termino"] <= dados["hora_inicio"]:
        raise ValidacaoError({"hora_termino": "O término deve ser posterior ao início"})


def _filtros():
    inicio, fim = periodo(30)
    args = validar(request.args.to_dict(), [
        Campo("setor", "texto", max_len=40),
        Campo("categoria", "escolha", escolhas=tuple(CATEGORIA_SERVICO)),
        Campo("situacao", "escolha", escolhas=tuple(SITUACAO_SERVICO)),
        Campo("periodicidade", "escolha", escolhas=tuple(PERIODICIDADE)),
        Campo("atrasados", "bool"),
        Campo("q", "texto", max_len=120),
    ])
    where = ["data_programada between %s and %s"]
    params: list = [inicio, fim]
    for campo, coluna in (("setor", "setor_codigo"), ("categoria", "categoria"), ("situacao", "situacao"),
                          ("periodicidade", "periodicidade")):
        if args.get(campo):
            where.append(f"{coluna} = %s")
            params.append(args[campo])
    if args.get("atrasados"):
        where.append("atrasado")
    if args.get("q"):
        termo = "%" + args["q"].replace("%", r"\%").replace("_", r"\_") + "%"
        where.append("(codigo ilike %s or titulo ilike %s or responsavel_executor ilike %s"
                     " or empresa_terceirizada ilike %s or local ilike %s)")
        params += [termo] * 5
    return " and ".join(where), params, inicio, fim, args


@bp.get("/servicos")
@requer_login
def listar():
    clausula, params, inicio, fim, _ = _filtros()
    with tx() as cur:
        cur.execute(f"""select id, codigo, titulo, setor_codigo, setor_nome, setor_cor, categoria, local,
                               data_programada, hora_inicio, hora_termino, responsavel_executor, empresa_terceirizada,
                               periodicidade, situacao, atrasado
                          from rg.v_servicos where {clausula}
                         order by data_programada, hora_inicio limit 2000""", params)
        itens = cur.fetchall()
    return jsonify({"itens": itens, "inicio": inicio, "fim": fim})


@bp.get("/servicos/relatorio.pdf")
@requer_login
def relatorio():
    clausula, params, inicio, fim, args = _filtros()
    with tx() as cur:
        cur.execute(f"select * from rg.v_servicos where {clausula} order by data_programada, hora_inicio limit 5000",
                    params)
        linhas = cur.fetchall()
        descricao = f"Período: {inicio:%d/%m/%Y} a {fim:%d/%m/%Y}" + (
            f" · Setor: {args['setor']}" if args.get("setor") else "") + (
            f" · Categoria: {CATEGORIA_SERVICO[args['categoria']]}" if args.get("categoria") else "")
        conteudo, codigo = pdf.relatorio_servicos(linhas, descricao, autor=g.usuario["nome"],
                                                  instituicao=current_app.config["INSTITUICAO"],
                                                  tz=current_app.config["TIMEZONE"])
        registrar_evento(cur, "RELATORIO_GERADO", "relatorios", "servicos",
                         {"codigo_verificacao": codigo, "registros": len(linhas)})
    return resposta_pdf(conteudo, "servicos-programados.pdf")


@bp.post("/servicos")
@requer_papel("admin", "gestor")
def criar():
    dados = validar(corpo_json(), CAMPOS)
    _validar_horario(dados)
    if g.usuario["papel"] == "gestor" and dados["setor_codigo"] != g.usuario["setor_codigo"]:
        raise ValidacaoError({"setor_codigo": "Gestores só programam serviços do próprio setor"})
    with tx() as cur:
        cur.execute(
            """insert into rg.servicos_programados (titulo, descricao, setor_codigo, categoria, local, data_programada,
                   hora_inicio, hora_termino, responsavel_executor, empresa_terceirizada, periodicidade, criado_por)
               values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
            (dados["titulo"], dados.get("descricao"), dados["setor_codigo"], dados["categoria"], dados.get("local"),
             dados["data_programada"], dados["hora_inicio"], dados["hora_termino"], dados["responsavel_executor"],
             dados.get("empresa_terceirizada"), dados.get("periodicidade") or "unica", g.usuario["id"]),
        )
        return jsonify(_obter(cur, str(cur.fetchone()["id"]))), 201


@bp.get("/servicos/<uuid:servico_id>")
@requer_login
def detalhar(servico_id):
    with tx() as cur:
        return jsonify(_obter(cur, str(servico_id)))


@bp.patch("/servicos/<uuid:servico_id>")
@requer_papel("admin", "gestor")
def atualizar(servico_id):
    dados = validar(corpo_json(), [c for c in CAMPOS if c.nome in EDITAVEIS], parcial=True)
    for campo in ("titulo", "categoria", "data_programada", "hora_inicio", "hora_termino", "responsavel_executor",
                  "periodicidade"):
        if campo in dados and dados[campo] is None:
            raise ValidacaoError({campo: "Campo obrigatório"})
    if not dados:
        raise ValidacaoError({"geral": "Nenhuma alteração informada"})
    with tx() as cur:
        atual = _obter(cur, str(servico_id))
        if atual["situacao"] != "agendado":
            raise ApiError("Somente serviços agendados podem ser reprogramados", 422, "status_invalido")
        _validar_horario({"hora_inicio": dados.get("hora_inicio", atual["hora_inicio"]),
                          "hora_termino": dados.get("hora_termino", atual["hora_termino"])})
        sets = ", ".join(f"{k} = %s" for k in dados)
        cur.execute(f"update rg.servicos_programados set {sets} where id = %s", (*dados.values(), str(servico_id)))
        if cur.rowcount != 1:
            raise ApiError("Você não pode alterar este serviço", 403, "proibido")
        return jsonify(_obter(cur, str(servico_id)))


@bp.post("/servicos/<uuid:servico_id>/<acao>")
@requer_papel("admin", "gestor")
def transicao(servico_id, acao: str):
    sid = str(servico_id)
    dados = corpo_json()
    with tx() as cur:
        atual = _obter(cur, sid)
        if atual["situacao"] in ("concluido", "cancelado"):
            raise ApiError(f"Serviço {atual['codigo']} já está encerrado", 422, "status_invalido")
        if not atual["pode_editar"]:
            raise ApiError("Você não pode alterar este serviço", 403, "proibido")
        if acao == "iniciar":
            if atual["situacao"] != "agendado":
                raise ApiError("O serviço já está em andamento", 422, "status_invalido")
            cur.execute("update rg.servicos_programados set situacao = 'em_andamento', iniciado_em = now()"
                        " where id = %s", (sid,))
        elif acao == "concluir":
            v = validar(dados, [Campo("observacoes", "texto", obrigatorio=True, min_len=5, max_len=5000,
                                      rotulo="Observações de conclusão"),
                                Campo("gerar_proxima", "bool", padrao=True)])
            cur.execute("""update rg.servicos_programados set situacao = 'concluido', concluido_em = now(),
                                  concluido_por = %s, observacoes_conclusao = %s,
                                  iniciado_em = coalesce(iniciado_em, now()) where id = %s""",
                        (g.usuario["id"], v["observacoes"], sid))
            proxima = proxima_data(atual["data_programada"], atual["periodicidade"])
            if proxima and v.get("gerar_proxima", True):
                cur.execute(
                    """insert into rg.servicos_programados (titulo, descricao, setor_codigo, categoria, local,
                           data_programada, hora_inicio, hora_termino, responsavel_executor, empresa_terceirizada,
                           periodicidade, serie_id, servico_origem_id, criado_por)
                       select titulo, descricao, setor_codigo, categoria, local, %s, hora_inicio, hora_termino,
                              responsavel_executor, empresa_terceirizada, periodicidade, serie_id, id, %s
                         from rg.servicos_programados where id = %s
                       on conflict (servico_origem_id) where servico_origem_id is not null do nothing""",
                    (proxima, g.usuario["id"], sid))
        elif acao == "cancelar":
            v = validar(dados, [Campo("motivo", "texto", obrigatorio=True, min_len=5, max_len=2000, rotulo="Motivo")])
            cur.execute("update rg.servicos_programados set situacao = 'cancelado', motivo_cancelamento = %s"
                        " where id = %s", (v["motivo"], sid))
        else:
            raise NaoEncontrado("Ação inexistente")
        return jsonify(_obter(cur, sid))


@bp.post("/servicos/<uuid:servico_id>/anexos")
@requer_papel("admin", "gestor")
def anexar(servico_id):
    sid = str(servico_id)
    dados = validar(corpo_json(), [Campo("tipo_documento", "escolha", escolhas=("laudo", "nota_fiscal", "orcamento", "outro"),
                                         padrao="laudo")])
    max_mb = current_app.config["MAX_UPLOAD_MB"]
    arquivos = [validar_arquivo(f, max_mb) for f in request.files.getlist("arquivos") if f and f.filename]
    if not arquivos:
        raise ValidacaoError({"arquivos": "Selecione ao menos um arquivo"})
    if len(arquivos) > 5:
        raise ValidacaoError({"arquivos": "Envie no máximo 5 arquivos por vez"})
    with LoteArquivos() as lote:
        with tx() as cur:
            _obter(cur, sid)
            ids = [inserir_anexo(cur, lote, a, usuario_id=g.usuario["id"], origem="servico",
                                 tipo_documento=dados.get("tipo_documento") or "laudo", servico_id=sid)
                   for a in arquivos]
    fila_ocr.enfileirar(ids)
    with tx() as cur:
        return jsonify(_obter(cur, sid)), 201
