"""Workflow de solicitações em três níveis: Gestor → Administração → Compras.

As regras são garantidas em duas camadas: aqui (mensagens claras e ordem das
operações) e no banco (máquina de estados em trigger + RLS + assinatura exigida).
"""
from __future__ import annotations

from decimal import Decimal

from ..db import definir_observacao
from ..errors import ApiError, Conflito, NaoEncontrado, Proibido
from . import assinaturas
from .arquivos import ArquivoValidado, LoteArquivos, inserir_anexo

MAX_ANEXOS = 3


def _obter(cur, solicitacao_id: str, *permitidos: str) -> dict:
    """Carrega a solicitação, valida o status esperado e bloqueia a linha para atualização.

    Sob RLS, SELECT ... FOR UPDATE também aplica a política de UPDATE; por isso a
    visibilidade e o status são conferidos antes do bloqueio para mensagens precisas.
    """
    cur.execute("select * from rg.solicitacoes where id = %s", (solicitacao_id,))
    linha = cur.fetchone()
    if not linha:
        raise NaoEncontrado("Solicitação não encontrada ou fora do seu escopo de acesso")
    _exigir_status(linha, *permitidos)
    cur.execute("select * from rg.solicitacoes where id = %s for update", (solicitacao_id,))
    bloqueada = cur.fetchone()
    if not bloqueada:
        raise Proibido("Seu perfil não pode alterar esta solicitação na etapa atual")
    _exigir_status(bloqueada, *permitidos)
    return bloqueada


def _conferir_versao(atual: dict, versao: int | None) -> None:
    if versao is not None and atual["versao"] != versao:
        raise Conflito("Esta solicitação foi alterada por outro usuário. Recarregue a página para ver a versão atual.")


def _exigir_status(atual: dict, *permitidos: str) -> None:
    if atual["status"] not in permitidos:
        raise ApiError(f"Ação indisponível no status atual ({atual['status']})", 422, "status_invalido")


def criar(cur, usuario: dict, dados: dict, arquivos: list[ArquivoValidado], lote: LoteArquivos,
          ip: str, user_agent: str) -> tuple[str, list[str]]:
    if len(arquivos) > MAX_ANEXOS:
        raise ApiError(f"Envie no máximo {MAX_ANEXOS} anexos", 422, "limite_anexos")
    cur.execute(
        """insert into rg.solicitacoes (tipo, titulo, descricao, justificativa, setor_codigo, urgencia,
                                        valor_estimado, gestor_id)
           values (%s, %s, %s, %s, %s, %s, %s, %s) returning id""",
        (dados["tipo"], dados["titulo"], dados["descricao"], dados["justificativa"], usuario["setor_codigo"],
         dados.get("urgencia") or "normal", dados.get("valor_estimado"), usuario["id"]),
    )
    solicitacao_id = str(cur.fetchone()["id"])
    anexos = [
        inserir_anexo(cur, lote, arq, usuario_id=usuario["id"], origem="solicitante",
                      tipo_documento=dados.get("tipo_documento") or "orcamento", solicitacao_id=solicitacao_id)
        for arq in arquivos
    ]
    assinaturas.assinar(cur, solicitacao_id=solicitacao_id, usuario_id=usuario["id"], acao="submissao",
                        ip=ip, user_agent=user_agent)
    return solicitacao_id, anexos


def adm_decidir(cur, usuario: dict, solicitacao_id: str, decisao: str, texto: str | None,
                versao: int | None, ip: str, user_agent: str) -> None:
    atual = _obter(cur, solicitacao_id, "aguardando_adm")
    _conferir_versao(atual, versao)
    texto = (texto or "").strip() or None
    if decisao == "aprovar":
        definir_observacao(cur, texto or "Aprovado pela Administração")
        cur.execute("update rg.solicitacoes set status = 'aprovado_adm', justificativa_adm = %s where id = %s",
                    (texto, solicitacao_id))
        acao = "aprovacao_adm"
    elif decisao == "rejeitar":
        _exigir_texto(texto, "justificativa")
        definir_observacao(cur, texto)
        cur.execute("update rg.solicitacoes set status = 'rejeitado_adm', justificativa_adm = %s where id = %s",
                    (texto, solicitacao_id))
        acao = "rejeicao_adm"
    elif decisao == "nova_cotacao":
        _exigir_texto(texto, "justificativa")
        definir_observacao(cur, texto)
        cur.execute("update rg.solicitacoes set status = 'necessita_nova_cotacao', motivo_nova_cotacao = %s"
                    " where id = %s", (texto, solicitacao_id))
        acao = "nova_cotacao_adm"
    else:
        raise ApiError("Decisão inválida", 422, "decisao_invalida")
    assinaturas.assinar(cur, solicitacao_id=solicitacao_id, usuario_id=usuario["id"], acao=acao,
                        ip=ip, user_agent=user_agent)


def adm_alterar_urgencia(cur, solicitacao_id: str, urgencia: str, justificativa: str | None,
                         versao: int | None) -> None:
    atual = _obter(cur, solicitacao_id, "aguardando_adm", "necessita_nova_cotacao")
    _conferir_versao(atual, versao)
    if atual["urgencia"] == urgencia:
        raise ApiError("A urgência informada é igual à atual", 422, "sem_alteracao")
    _exigir_texto(justificativa, "justificativa")
    cur.execute("update rg.solicitacoes set urgencia = %s, justificativa_urgencia = %s where id = %s",
                (urgencia, justificativa.strip(), solicitacao_id))


def gestor_reenviar(cur, usuario: dict, solicitacao_id: str, dados: dict, novos: list[ArquivoValidado],
                    remover: list[str], lote: LoteArquivos, versao: int | None,
                    ip: str, user_agent: str) -> list[str]:
    atual = _obter(cur, solicitacao_id, "necessita_nova_cotacao")
    _conferir_versao(atual, versao)
    for anexo_id in remover:
        cur.execute(
            "update rg.anexos set removido_em = now(), removido_por = %s"
            " where id = %s and solicitacao_id = %s and origem = 'solicitante' and removido_em is null",
            (usuario["id"], anexo_id, solicitacao_id),
        )
        if cur.rowcount != 1:
            raise ApiError("Anexo a remover não encontrado", 422, "anexo_invalido")
    campos = {k: dados[k] for k in ("titulo", "descricao", "justificativa", "tipo", "valor_estimado") if k in dados}
    if campos:
        definir_observacao(cur, "Conteúdo revisado pelo gestor")
        sets = ", ".join(f"{k} = %s" for k in campos)
        cur.execute(f"update rg.solicitacoes set {sets} where id = %s", (*campos.values(), solicitacao_id))
    cur.execute("select count(*) as n from rg.anexos where solicitacao_id = %s and origem = 'solicitante'"
                " and removido_em is null", (solicitacao_id,))
    if cur.fetchone()["n"] + len(novos) > MAX_ANEXOS:
        raise ApiError(f"Máximo de {MAX_ANEXOS} anexos ativos. Remova anexos antigos antes de enviar novos.",
                       422, "limite_anexos")
    rodada = atual["rodada_cotacao"] + 1
    novos_ids = [
        inserir_anexo(cur, lote, arq, usuario_id=usuario["id"], origem="solicitante",
                      tipo_documento=dados.get("tipo_documento") or "orcamento",
                      solicitacao_id=solicitacao_id, rodada=rodada)
        for arq in novos
    ]
    definir_observacao(cur, (dados.get("observacao") or "").strip() or "Reenviado com nova cotação")
    cur.execute("update rg.solicitacoes set status = 'aguardando_adm' where id = %s", (solicitacao_id,))
    assinaturas.assinar(cur, solicitacao_id=solicitacao_id, usuario_id=usuario["id"], acao="reenvio",
                        ip=ip, user_agent=user_agent)
    return novos_ids


def gestor_cancelar(cur, solicitacao_id: str, motivo: str | None, versao: int | None) -> None:
    atual = _obter(cur, solicitacao_id, "aguardando_adm", "necessita_nova_cotacao")
    _conferir_versao(atual, versao)
    _exigir_texto(motivo, "motivo")
    cur.execute("update rg.solicitacoes set status = 'cancelado', motivo_cancelamento = %s where id = %s",
                (motivo.strip(), solicitacao_id))


def compras_iniciar(cur, solicitacao_id: str, versao: int | None) -> None:
    atual = _obter(cur, solicitacao_id, "aprovado_adm")
    _conferir_versao(atual, versao)
    definir_observacao(cur, "Cotação iniciada pelo setor de Compras")
    cur.execute("update rg.solicitacoes set status = 'em_cotacao' where id = %s", (solicitacao_id,))


def compras_homologar(cur, usuario: dict, solicitacao_id: str, cotacao_id: str, valor_final: Decimal | None,
                      observacao: str | None, versao: int | None, ip: str, user_agent: str) -> None:
    atual = _obter(cur, solicitacao_id, "em_cotacao")
    _conferir_versao(atual, versao)
    cur.execute("select id, valor from rg.cotacoes where id = %s and solicitacao_id = %s",
                (cotacao_id, solicitacao_id))
    cotacao = cur.fetchone()
    if not cotacao:
        raise ApiError("Cotação vencedora inválida", 422, "cotacao_invalida")
    valor = valor_final if valor_final is not None else cotacao["valor"]
    cur.execute("update rg.cotacoes set selecionada = false where solicitacao_id = %s and selecionada",
                (solicitacao_id,))
    cur.execute("update rg.cotacoes set selecionada = true where id = %s", (cotacao_id,))
    definir_observacao(cur, (observacao or "").strip() or "Homologado pelo setor de Compras")
    cur.execute(
        "update rg.solicitacoes set status = 'aprovado', cotacao_vencedora_id = %s, valor_final_aprovado = %s,"
        " justificativa_compras = %s where id = %s",
        (cotacao_id, valor, (observacao or "").strip() or None, solicitacao_id),
    )
    assinaturas.assinar(cur, solicitacao_id=solicitacao_id, usuario_id=usuario["id"], acao="homologacao",
                        ip=ip, user_agent=user_agent)


def compras_rejeitar(cur, usuario: dict, solicitacao_id: str, justificativa: str | None, versao: int | None,
                     ip: str, user_agent: str) -> None:
    atual = _obter(cur, solicitacao_id, "em_cotacao")
    _conferir_versao(atual, versao)
    _exigir_texto(justificativa, "justificativa")
    definir_observacao(cur, justificativa.strip())
    cur.execute("update rg.solicitacoes set status = 'rejeitado_compras', justificativa_compras = %s where id = %s",
                (justificativa.strip(), solicitacao_id))
    assinaturas.assinar(cur, solicitacao_id=solicitacao_id, usuario_id=usuario["id"], acao="rejeicao_compras",
                        ip=ip, user_agent=user_agent)


def _exigir_texto(texto: str | None, campo: str, minimo: int = 10) -> None:
    from ..errors import ValidacaoError
    if len((texto or "").strip()) < minimo:
        raise ValidacaoError({campo: f"Informe ao menos {minimo} caracteres"})


def carregar_detalhe(cur, solicitacao_id: str) -> dict:
    cur.execute("select * from rg.v_solicitacoes where id = %s", (solicitacao_id,))
    s = cur.fetchone()
    if not s:
        raise NaoEncontrado("Solicitação não encontrada ou fora do seu escopo de acesso")
    cur.execute(
        """select a.id, a.origem, a.tipo_documento, a.nome_original, a.mime, a.tamanho, a.sha256,
                  a.rodada_cotacao, a.ocr_status, a.ocr_motor, a.dados_ocr, a.ocr_erro, a.ocr_processado_em,
                  a.removido_em, a.criado_em, u.nome as enviado_por_nome
             from rg.anexos a left join rg.v_usuarios_publico u on u.id = a.enviado_por
            where a.solicitacao_id = %s order by a.criado_em""",
        (solicitacao_id,),
    )
    anexos = cur.fetchall()
    cur.execute(
        """select c.*, f.razao_social, f.nome_fantasia, f.cnpj, u.nome as criado_por_nome
             from rg.cotacoes c
             join rg.fornecedores f on f.id = c.fornecedor_id
             left join rg.v_usuarios_publico u on u.id = c.criado_por
            where c.solicitacao_id = %s order by c.valor""",
        (solicitacao_id,),
    )
    cotacoes = cur.fetchall()
    cur.execute(
        """select a.id, a.tipo, a.acao, a.status_resultante, a.ip, a.assinado_em, a.conteudo_hash,
                  a.hash_autenticidade, a.algoritmo, u.nome as usuario_nome, u.papel as usuario_papel
             from rg.assinaturas a left join rg.v_usuarios_publico u on u.id = a.usuario_id
            where a.solicitacao_id = %s order by a.assinado_em""",
        (solicitacao_id,),
    )
    assinaturas_ = cur.fetchall()
    cur.execute(
        """select h.id, h.acao, h.status_de, h.status_para, h.observacao, h.criado_em,
                  u.nome as autor_nome, u.papel as autor_papel
             from rg.solicitacao_historico h left join rg.v_usuarios_publico u on u.id = h.autor_id
            where h.solicitacao_id = %s order by h.criado_em, h.id""",
        (solicitacao_id,),
    )
    historico = cur.fetchall()
    return {"solicitacao": s, "anexos": anexos, "cotacoes": cotacoes,
            "assinaturas": assinaturas_, "historico": historico}


def acoes_disponiveis(usuario: dict, s: dict) -> list[str]:
    papel, status = usuario["papel"], s["status"]
    acoes: list[str] = []
    if papel == "admin" and status == "aguardando_adm":
        acoes += ["adm_aprovar", "adm_rejeitar", "adm_nova_cotacao", "adm_urgencia"]
    if papel == "admin" and status == "necessita_nova_cotacao":
        acoes.append("adm_urgencia")
    if papel == "gestor" and s["setor_codigo"] == usuario["setor_codigo"]:
        if status == "necessita_nova_cotacao":
            acoes += ["gestor_reenviar", "gestor_cancelar"]
        elif status == "aguardando_adm":
            acoes.append("gestor_cancelar")
    if papel == "compras":
        if status == "aprovado_adm":
            acoes.append("compras_iniciar")
        elif status == "em_cotacao":
            acoes += ["compras_cotacao", "compras_homologar", "compras_rejeitar"]
    return acoes
