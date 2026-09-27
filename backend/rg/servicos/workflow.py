"""Fluxo de compras: Solicitação → Aprovação → Cotação → Fornecedor → Pedido → Recebimento → Conclusão.

As regras são garantidas em duas camadas: aqui (mensagens claras e ordem das operações)
e no banco (máquinas de estado em triggers + RLS + assinatura exigida na mesma transação).
"""
from __future__ import annotations

from decimal import Decimal

from ..db import definir_observacao
from ..errors import ApiError, Conflito, NaoEncontrado, Proibido, ValidacaoError
from . import assinaturas
from .arquivos import ArquivoValidado, LoteArquivos, inserir_anexo

MAX_ANEXOS_SOLICITANTE = 5
EDITAVEIS = ("tipo", "titulo", "descricao", "justificativa", "urgencia", "local_entrega", "data_necessidade")


# ---------------------------------------------------------------------------
# utilitários
# ---------------------------------------------------------------------------
def _obter(cur, solicitacao_id: str, *permitidos: str) -> dict:
    """Carrega a solicitação, confere o status e bloqueia a linha.

    Sob RLS, SELECT ... FOR UPDATE também aplica a política de UPDATE; por isso a
    visibilidade e o status são conferidos antes do bloqueio, para mensagens precisas.
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
        raise Conflito("Este registro foi alterado por outro usuário. Recarregue a página para ver a versão atual.")


def _exigir_status(atual: dict, *permitidos: str) -> None:
    if permitidos and atual["status"] not in permitidos:
        raise ApiError("Ação indisponível na etapa atual", 422, "status_invalido")


def exigir_texto(texto: str | None, campo: str = "texto", minimo: int = 10) -> str:
    if len((texto or "").strip()) < minimo:
        raise ValidacaoError({campo: f"Informe ao menos {minimo} caracteres"})
    return texto.strip()


def _inserir_itens(cur, solicitacao_id: str, itens: list[dict]) -> None:
    if not itens:
        raise ValidacaoError({"itens": "Inclua ao menos um item"})
    for ordem, item in enumerate(itens, start=1):
        descricao, unidade = item.get("descricao"), item.get("unidade")
        if item.get("material_id"):
            cur.execute("select nome, unidade from rg.materiais where id = %s and ativo", (item["material_id"],))
            material = cur.fetchone()
            if not material:
                raise ValidacaoError({"itens": f"Item {ordem}: material inexistente ou inativo"})
            descricao = descricao or material["nome"]
            unidade = unidade or material["unidade"]
        if not descricao or not unidade:
            raise ValidacaoError({"itens": f"Item {ordem}: informe a descrição e a unidade"})
        cur.execute(
            """insert into rg.solicitacao_itens (solicitacao_id, ordem, material_id, descricao, unidade, quantidade,
                                                 valor_unitario_estimado, observacao)
               values (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (solicitacao_id, ordem, item.get("material_id"), descricao, unidade, item["quantidade"],
             item.get("valor_unitario_estimado") or Decimal("0"), item.get("observacao")),
        )


# ---------------------------------------------------------------------------
# solicitação
# ---------------------------------------------------------------------------
def criar(cur, usuario: dict, dados: dict, itens: list[dict], arquivos: list[ArquivoValidado], lote: LoteArquivos,
          ip: str, user_agent: str) -> str:
    if len(arquivos) > MAX_ANEXOS_SOLICITANTE:
        raise ValidacaoError({"arquivos": f"Envie no máximo {MAX_ANEXOS_SOLICITANTE} documentos"})
    cur.execute(
        """insert into rg.solicitacoes (tipo, titulo, descricao, justificativa, setor_codigo, urgencia, local_entrega,
                                        data_necessidade, solicitante_id)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s) returning id""",
        (dados["tipo"], dados["titulo"], dados.get("descricao"), dados["justificativa"], usuario["setor_codigo"],
         dados.get("urgencia") or "normal", dados.get("local_entrega"), dados.get("data_necessidade"), usuario["id"]),
    )
    solicitacao_id = str(cur.fetchone()["id"])
    _inserir_itens(cur, solicitacao_id, itens)
    for arq in arquivos:
        inserir_anexo(cur, lote, arq, usuario_id=usuario["id"], origem="solicitante",
                      tipo_documento=dados.get("tipo_documento") or "orcamento", solicitacao_id=solicitacao_id)
    assinaturas.assinar(cur, solicitacao_id=solicitacao_id, usuario=usuario, acao="submissao", ip=ip,
                        user_agent=user_agent)
    return solicitacao_id


def decidir_aprovacao(cur, usuario: dict, sid: str, decisao: str, texto: str | None, versao: int | None,
                      ip: str, user_agent: str) -> None:
    """Gestor (nível 1) ou Diretoria (nível 2): aprovar, devolver ou reprovar."""
    status_esperado = {"gestor": "aguardando_gestor", "diretoria": "aguardando_diretoria"}.get(usuario["papel"])
    if not status_esperado:
        raise Proibido("Seu perfil não aprova solicitações")
    atual = _obter(cur, sid, status_esperado)
    _conferir_versao(atual, versao)
    if usuario["papel"] == "gestor":
        if atual["setor_codigo"] != usuario["setor_codigo"]:
            raise Proibido("Você só aprova solicitações do seu setor")
        if atual["solicitante_id"] == usuario["id"]:
            raise ApiError("Segregação de funções: você não pode aprovar a própria solicitação", 422, "segregacao")
    texto = (texto or "").strip() or None
    if decisao == "aprovar":
        definir_observacao(cur, texto or "Aprovada")
        cur.execute("update rg.solicitacoes set status = 'aprovada' where id = %s", (sid,))
        acao = "aprovacao_gestor" if usuario["papel"] == "gestor" else "aprovacao_diretoria"
    elif decisao == "devolver":
        texto = exigir_texto(texto)
        definir_observacao(cur, texto)
        cur.execute("update rg.solicitacoes set status = 'devolvida', motivo_devolucao = %s where id = %s", (texto, sid))
        acao = "devolucao"
    elif decisao == "reprovar":
        texto = exigir_texto(texto)
        definir_observacao(cur, texto)
        cur.execute("update rg.solicitacoes set status = 'reprovada', motivo_reprovacao = %s where id = %s", (texto, sid))
        acao = "reprovacao"
    else:
        raise ApiError("Decisão inválida", 422, "decisao_invalida")
    assinaturas.assinar(cur, solicitacao_id=sid, usuario=usuario, acao=acao, ip=ip, user_agent=user_agent)


def reenviar(cur, usuario: dict, sid: str, dados: dict, itens: list[dict] | None, novos: list[ArquivoValidado],
             remover: list[str], lote: LoteArquivos, versao: int | None, ip: str, user_agent: str) -> None:
    atual = _obter(cur, sid, "devolvida")
    _conferir_versao(atual, versao)
    campos = {k: dados[k] for k in EDITAVEIS if k in dados and dados[k] is not None}
    if campos:
        definir_observacao(cur, "Conteúdo ajustado pelo setor")
        sets = ", ".join(f"{k} = %s" for k in campos)
        cur.execute(f"update rg.solicitacoes set {sets} where id = %s", (*campos.values(), sid))
    if itens is not None:
        cur.execute("delete from rg.solicitacao_itens where solicitacao_id = %s", (sid,))
        _inserir_itens(cur, sid, itens)
    for anexo_id in remover:
        cur.execute("update rg.anexos set removido_em = now() where id = %s and solicitacao_id = %s"
                    " and origem = 'solicitante' and removido_em is null", (anexo_id, sid))
        if cur.rowcount != 1:
            raise ApiError("Documento a remover não encontrado", 422, "anexo_invalido")
    for arq in novos:
        inserir_anexo(cur, lote, arq, usuario_id=usuario["id"], origem="solicitante",
                      tipo_documento=dados.get("tipo_documento") or "orcamento", solicitacao_id=sid)
    definir_observacao(cur, (dados.get("observacao") or "").strip() or "Reenviada após ajustes")
    cur.execute("update rg.solicitacoes set status = 'aguardando_gestor' where id = %s", (sid,))
    assinaturas.assinar(cur, solicitacao_id=sid, usuario=usuario, acao="reenvio", ip=ip, user_agent=user_agent)


def cancelar(cur, usuario: dict, sid: str, motivo: str | None, versao: int | None, ip: str, user_agent: str) -> None:
    atual = _obter(cur, sid, "aguardando_gestor", "aguardando_diretoria", "devolvida", "aprovada", "em_cotacao",
                   "aguardando_pedido")
    _conferir_versao(atual, versao)
    motivo = exigir_texto(motivo, "texto")
    definir_observacao(cur, motivo)
    cur.execute("update rg.solicitacoes set status = 'cancelada', motivo_cancelamento = %s where id = %s", (motivo, sid))


def iniciar_cotacao(cur, sid: str, versao: int | None) -> None:
    atual = _obter(cur, sid, "aprovada")
    _conferir_versao(atual, versao)
    definir_observacao(cur, "Cotação iniciada pelo comprador")
    cur.execute("update rg.solicitacoes set status = 'em_cotacao' where id = %s", (sid,))


def definir_fornecedor(cur, usuario: dict, sid: str, cotacao_id: str, justificativa: str | None,
                       versao: int | None, ip: str, user_agent: str) -> None:
    atual = _obter(cur, sid, "em_cotacao")
    _conferir_versao(atual, versao)
    cur.execute("select id from rg.cotacoes where id = %s and solicitacao_id = %s", (cotacao_id, sid))
    if not cur.fetchone():
        raise ValidacaoError({"cotacao_id": "Proposta inválida"})
    cur.execute("update rg.cotacoes set selecionada = false where solicitacao_id = %s and selecionada", (sid,))
    cur.execute("update rg.cotacoes set selecionada = true where id = %s", (cotacao_id,))
    justificativa = (justificativa or "").strip() or None
    definir_observacao(cur, justificativa or "Fornecedor definido pelo comprador")
    cur.execute("update rg.solicitacoes set status = 'aguardando_pedido', cotacao_vencedora_id = %s,"
                " justificativa_escolha = %s where id = %s", (cotacao_id, justificativa, sid))
    assinaturas.assinar(cur, solicitacao_id=sid, usuario=usuario, acao="definicao_fornecedor", ip=ip,
                        user_agent=user_agent)


def reabrir_cotacao(cur, sid: str, motivo: str | None, versao: int | None) -> None:
    atual = _obter(cur, sid, "aguardando_pedido")
    _conferir_versao(atual, versao)
    definir_observacao(cur, exigir_texto(motivo))
    cur.execute("update rg.solicitacoes set status = 'em_cotacao' where id = %s", (sid,))


# ---------------------------------------------------------------------------
# propostas (cotação) — preenchimento manual
# ---------------------------------------------------------------------------
def salvar_proposta(cur, usuario: dict, sid: str, dados: dict, itens: list[dict], cotacao_id: str | None = None) -> str:
    _obter(cur, sid, "em_cotacao")
    if not itens:
        raise ValidacaoError({"itens": "Informe o preço de ao menos um item"})
    cur.execute("select id from rg.solicitacao_itens where solicitacao_id = %s", (sid,))
    validos = {str(r["id"]) for r in cur.fetchall()}
    for item in itens:
        if item["solicitacao_item_id"] not in validos:
            raise ValidacaoError({"itens": "Item não pertence a esta solicitação"})
    campos = ("numero_proposta", "data_proposta", "validade_proposta", "prazo_entrega_dias", "condicoes_pagamento",
              "frete", "desconto", "observacoes", "anexo_id")
    valores = [dados.get(c) if c not in ("frete", "desconto") else (dados.get(c) or Decimal("0")) for c in campos]
    if cotacao_id:
        cur.execute("select id from rg.cotacoes where id = %s and solicitacao_id = %s", (cotacao_id, sid))
        if not cur.fetchone():
            raise NaoEncontrado("Proposta não encontrada")
        sets = ", ".join(f"{c} = %s" for c in campos)
        cur.execute(f"update rg.cotacoes set {sets} where id = %s", (*valores, cotacao_id))
        cur.execute("delete from rg.cotacao_itens where cotacao_id = %s", (cotacao_id,))
    else:
        cur.execute("select 1 from rg.cotacoes where solicitacao_id = %s and fornecedor_id = %s",
                    (sid, dados["fornecedor_id"]))
        if cur.fetchone():
            raise ValidacaoError({"fornecedor_id": "Já existe proposta deste fornecedor nesta cotação"})
        cur.execute(
            f"""insert into rg.cotacoes (solicitacao_id, fornecedor_id, criado_por, {", ".join(campos)})
                values (%s, %s, %s, {", ".join(["%s"] * len(campos))}) returning id""",
            (sid, dados["fornecedor_id"], usuario["id"], *valores),
        )
        cotacao_id = str(cur.fetchone()["id"])
    for item in itens:
        cur.execute(
            """insert into rg.cotacao_itens (cotacao_id, solicitacao_item_id, quantidade, valor_unitario, marca, observacao)
               values (%s, %s, %s, %s, %s, %s)""",
            (cotacao_id, item["solicitacao_item_id"], item["quantidade"], item["valor_unitario"], item.get("marca"),
             item.get("observacao")),
        )
    return cotacao_id


def remover_proposta(cur, cotacao_id: str) -> str:
    cur.execute("select solicitacao_id, selecionada from rg.cotacoes where id = %s", (cotacao_id,))
    c = cur.fetchone()
    if not c:
        raise NaoEncontrado("Proposta não encontrada")
    sid = str(c["solicitacao_id"])
    _obter(cur, sid, "em_cotacao")
    cur.execute("delete from rg.cotacoes where id = %s", (cotacao_id,))
    return sid


# ---------------------------------------------------------------------------
# pedido de compra
# ---------------------------------------------------------------------------
def emitir_pedido(cur, usuario: dict, sid: str, dados: dict, versao: int | None, ip: str, user_agent: str) -> str:
    atual = _obter(cur, sid, "aguardando_pedido")
    _conferir_versao(atual, versao)
    definir_observacao(cur, "Pedido de compra emitido")
    cur.execute(
        """insert into rg.pedidos (solicitacao_id, cotacao_id, fornecedor_id, comprador_id, condicoes_pagamento,
                                   local_entrega, observacoes)
           values (%s, %s, (select fornecedor_id from rg.cotacoes where id = %s), %s, %s, %s, %s) returning id""",
        (sid, atual["cotacao_vencedora_id"], atual["cotacao_vencedora_id"], usuario["id"],
         dados.get("condicoes_pagamento"), dados.get("local_entrega"), dados.get("observacoes")),
    )
    pedido_id = str(cur.fetchone()["id"])
    assinaturas.assinar(cur, solicitacao_id=sid, usuario=usuario, acao="emissao_pedido", ip=ip,
                        user_agent=user_agent, pedido_id=pedido_id)
    return pedido_id


def _obter_pedido(cur, pedido_id: str, *permitidos: str, bloquear: bool = True) -> dict:
    cur.execute("select * from rg.pedidos where id = %s", (pedido_id,))
    p = cur.fetchone()
    if not p:
        raise NaoEncontrado("Pedido não encontrado ou fora do seu escopo de acesso")
    _exigir_status(p, *permitidos)
    if not bloquear:
        return p
    cur.execute("select * from rg.pedidos where id = %s for update", (pedido_id,))
    bloqueado = cur.fetchone()
    if not bloqueado:
        raise Proibido("Seu perfil não pode alterar este pedido")
    _exigir_status(bloqueado, *permitidos)
    return bloqueado


def decidir_pedido(cur, usuario: dict, pedido_id: str, decisao: str, texto: str | None, versao: int | None,
                   ip: str, user_agent: str) -> None:
    papel = usuario["papel"]
    status_esperado = {"financeiro": "aguardando_financeiro", "diretoria": "aguardando_diretoria"}.get(papel)
    if not status_esperado:
        raise Proibido("Seu perfil não aprova pedidos de compra")
    p = _obter_pedido(cur, pedido_id, status_esperado)
    _conferir_versao(p, versao)
    texto = (texto or "").strip() or None
    coluna_parecer = "parecer_financeiro" if papel == "financeiro" else "parecer_diretoria"
    if decisao == "aprovar":
        definir_observacao(cur, texto or "Pedido aprovado")
        cur.execute(f"update rg.pedidos set status = 'aprovado', {coluna_parecer} = %s where id = %s", (texto, pedido_id))
        acao = "aprovacao_financeiro" if papel == "financeiro" else "aprovacao_diretoria_pedido"
    elif decisao == "reprovar":
        texto = exigir_texto(texto)
        definir_observacao(cur, texto)
        cur.execute(f"update rg.pedidos set status = 'reprovado', motivo_reprovacao = %s, {coluna_parecer} = %s"
                    " where id = %s", (texto, texto, pedido_id))
        acao = "reprovacao_financeiro" if papel == "financeiro" else "reprovacao_diretoria_pedido"
    else:
        raise ApiError("Decisão inválida", 422, "decisao_invalida")
    assinaturas.assinar(cur, solicitacao_id=str(p["solicitacao_id"]), usuario=usuario, acao=acao, ip=ip,
                        user_agent=user_agent, pedido_id=pedido_id)


def enviar_pedido(cur, usuario: dict, pedido_id: str, data_prevista, versao: int | None, ip: str, user_agent: str) -> None:
    p = _obter_pedido(cur, pedido_id, "aprovado")
    _conferir_versao(p, versao)
    definir_observacao(cur, "Pedido enviado ao fornecedor")
    cur.execute("update rg.pedidos set status = 'enviado', data_prevista_entrega = %s where id = %s",
                (data_prevista, pedido_id))
    assinaturas.assinar(cur, solicitacao_id=str(p["solicitacao_id"]), usuario=usuario, acao="envio_pedido", ip=ip,
                        user_agent=user_agent, pedido_id=pedido_id)


def cancelar_pedido(cur, usuario: dict, pedido_id: str, motivo: str | None, versao: int | None,
                    ip: str, user_agent: str) -> None:
    p = _obter_pedido(cur, pedido_id, "aguardando_financeiro", "aguardando_diretoria", "aprovado", "enviado")
    _conferir_versao(p, versao)
    motivo = exigir_texto(motivo)
    definir_observacao(cur, motivo)
    cur.execute("update rg.pedidos set status = 'cancelado', motivo_cancelamento = %s where id = %s", (motivo, pedido_id))


def encerrar_pedido(cur, usuario: dict, pedido_id: str, justificativa: str | None, versao: int | None,
                    ip: str, user_agent: str) -> None:
    p = _obter_pedido(cur, pedido_id, "entregue_parcial")
    _conferir_versao(p, versao)
    justificativa = exigir_texto(justificativa)
    definir_observacao(cur, justificativa)
    cur.execute("update rg.pedidos set status = 'entregue', justificativa_encerramento = %s where id = %s",
                (justificativa, pedido_id))
    assinaturas.assinar(cur, solicitacao_id=str(p["solicitacao_id"]), usuario=usuario, acao="encerramento_pedido",
                        ip=ip, user_agent=user_agent, pedido_id=pedido_id)


def atualizar_previsao(cur, pedido_id: str, data_prevista, observacao: str | None) -> None:
    p = _obter_pedido(cur, pedido_id, "enviado", "entregue_parcial")
    cur.execute("update rg.pedidos set data_prevista_entrega = %s, atraso_notificado_em = null where id = %s",
                (data_prevista, p["id"]))


def registrar_recebimento(cur, usuario: dict, pedido_id: str, dados: dict, itens: list[dict],
                          arquivos: list[ArquivoValidado], lote: LoteArquivos, ip: str, user_agent: str) -> str:
    # O Recebimento não altera o pedido diretamente: o bloqueio é feito por rg.processar_recebimento
    p = _obter_pedido(cur, pedido_id, "enviado", "entregue_parcial", bloquear=False)
    if not any(i["quantidade_recebida"] > 0 for i in itens):
        raise ValidacaoError({"itens": "Informe a quantidade recebida de ao menos um item"})
    cur.execute(
        """insert into rg.recebimentos (pedido_id, solicitacao_id, nota_fiscal, data_emissao_nf, valor_nf, observacoes,
                                        recebido_por)
           values (%s, %s, %s, %s, %s, %s, %s) returning id""",
        (pedido_id, p["solicitacao_id"], dados["nota_fiscal"], dados.get("data_emissao_nf"), dados.get("valor_nf"),
         dados.get("observacoes"), usuario["id"]),
    )
    rid = str(cur.fetchone()["id"])
    for item in itens:
        if item["quantidade_recebida"] <= 0:
            continue
        if item["quantidade_aceita"] > item["quantidade_recebida"]:
            raise ValidacaoError({"itens": "A quantidade aceita não pode superar a recebida"})
        if item["quantidade_aceita"] < item["quantidade_recebida"] and len((item.get("motivo_divergencia") or "").strip()) < 5:
            raise ValidacaoError({"itens": "Descreva a divergência dos itens não aceitos"})
        cur.execute(
            """insert into rg.recebimento_itens (recebimento_id, pedido_item_id, quantidade_recebida, quantidade_aceita,
                                                 motivo_divergencia) values (%s, %s, %s, %s, %s)""",
            (rid, item["pedido_item_id"], item["quantidade_recebida"], item["quantidade_aceita"],
             item.get("motivo_divergencia")),
        )
    for arq in arquivos:
        inserir_anexo(cur, lote, arq, usuario_id=usuario["id"], origem="recebimento",
                      tipo_documento=dados.get("tipo_documento") or "nota_fiscal",
                      solicitacao_id=str(p["solicitacao_id"]), recebimento_id=rid)
    cur.execute("select rg.processar_recebimento(%s)", (rid,))
    assinaturas.assinar(cur, solicitacao_id=str(p["solicitacao_id"]), usuario=usuario, acao="recebimento", ip=ip,
                        user_agent=user_agent, pedido_id=pedido_id, recebimento_id=rid)
    return rid


# ---------------------------------------------------------------------------
# leitura
# ---------------------------------------------------------------------------
def comparar_propostas(itens: list[dict], cotacoes: list[dict], minimo: int) -> dict:
    """Mapa de comparação item × fornecedor com menor preço por item e ranking geral."""
    completos = [c for c in cotacoes if len(c["itens"]) >= len(itens)]
    menor_total = min((c["valor_total"] for c in completos), default=None)
    linhas = []
    for item in itens:
        precos = {}
        for c in cotacoes:
            ci = next((x for x in c["itens"] if str(x["solicitacao_item_id"]) == str(item["id"])), None)
            if ci:
                precos[str(c["id"])] = {"valor_unitario": ci["valor_unitario"], "quantidade": ci["quantidade"],
                                        "total": round(ci["valor_unitario"] * ci["quantidade"], 2), "marca": ci["marca"]}
        menor = min((p["valor_unitario"] for p in precos.values()), default=None)
        linhas.append({"item_id": str(item["id"]), "descricao": item["descricao"], "unidade": item["unidade"],
                       "quantidade": item["quantidade"], "estimado": item["valor_unitario_estimado"],
                       "precos": precos, "menor_unitario": menor})
    ranking = sorted(cotacoes, key=lambda c: (len(c["itens"]) < len(itens), c["valor_total"]))
    return {
        "linhas": linhas,
        "ranking": [str(c["id"]) for c in ranking],
        "menor_total": menor_total,
        "melhor_prazo": min((c["prazo_entrega_dias"] for c in cotacoes), default=None),
        "minimo_cotacoes": minimo,
        "abaixo_do_minimo": len(cotacoes) < minimo,
    }


def carregar_detalhe(cur, solicitacao_id: str) -> dict:
    cur.execute("select * from rg.v_solicitacoes where id = %s", (solicitacao_id,))
    s = cur.fetchone()
    if not s:
        raise NaoEncontrado("Solicitação não encontrada ou fora do seu escopo de acesso")
    cur.execute("""select i.*, m.codigo as material_codigo, (i.quantidade * i.valor_unitario_estimado) as total_estimado
                     from rg.solicitacao_itens i left join rg.materiais m on m.id = i.material_id
                    where i.solicitacao_id = %s order by i.ordem, i.criado_em""", (solicitacao_id,))
    itens = cur.fetchall()
    cur.execute("""select a.id, a.origem, a.tipo_documento, a.nome_original, a.mime, a.tamanho, a.sha256, a.rodada,
                          a.recebimento_id, a.removido_em, a.criado_em, u.nome as enviado_por_nome
                     from rg.anexos a left join rg.v_usuarios_publico u on u.id = a.enviado_por
                    where a.solicitacao_id = %s order by a.criado_em""", (solicitacao_id,))
    anexos = cur.fetchall()
    cur.execute("""select c.*, f.razao_social, f.nome_fantasia, f.cnpj, u.nome as criado_por_nome
                     from rg.cotacoes c join rg.fornecedores f on f.id = c.fornecedor_id
                     left join rg.v_usuarios_publico u on u.id = c.criado_por
                    where c.solicitacao_id = %s order by c.valor_total""", (solicitacao_id,))
    cotacoes = cur.fetchall()
    for c in cotacoes:
        cur.execute("select * from rg.cotacao_itens where cotacao_id = %s", (c["id"],))
        c["itens"] = cur.fetchall()
    cur.execute("select * from rg.v_pedidos where solicitacao_id = %s order by criado_em desc", (solicitacao_id,))
    pedidos = cur.fetchall()
    cur.execute("select * from rg.v_recebimentos where solicitacao_id = %s order by recebido_em", (solicitacao_id,))
    recebimentos = cur.fetchall()
    cur.execute("""select a.*, u.nome as usuario_nome, u.cargo as usuario_cargo
                     from rg.aprovacoes a left join rg.v_usuarios_publico u on u.id = a.usuario_id
                    where a.solicitacao_id = %s order by a.criado_em""", (solicitacao_id,))
    aprovacoes = cur.fetchall()
    cur.execute("""select a.id, a.papel, a.acao, a.status_solicitacao, a.status_pedido, a.pedido_id, a.recebimento_id,
                          a.ip, a.assinado_em, a.conteudo_hash, a.hash_autenticidade, a.algoritmo, u.nome as usuario_nome
                     from rg.assinaturas a left join rg.v_usuarios_publico u on u.id = a.usuario_id
                    where a.solicitacao_id = %s order by a.assinado_em""", (solicitacao_id,))
    assinaturas_ = cur.fetchall()
    cur.execute("""select h.id, h.acao, h.status_de, h.status_para, h.observacao, h.criado_em, h.pedido_id,
                          u.nome as autor_nome, u.papel as autor_papel
                     from rg.solicitacao_historico h left join rg.v_usuarios_publico u on u.id = h.autor_id
                    where h.solicitacao_id = %s order by h.criado_em, h.id""", (solicitacao_id,))
    historico = cur.fetchall()
    cur.execute("select rg.config_num('minimo_cotacoes') as m, rg.config_num('alcada_diretoria') as a")
    cfg = cur.fetchone()
    return {"solicitacao": s, "itens": itens, "anexos": anexos, "cotacoes": cotacoes,
            "comparacao": comparar_propostas(itens, cotacoes, int(cfg["m"] or 1)),
            "pedidos": pedidos, "recebimentos": recebimentos, "aprovacoes": aprovacoes,
            "assinaturas": assinaturas_, "historico": historico, "alcada_diretoria": cfg["a"]}


def acoes_disponiveis(usuario: dict, s: dict) -> list[str]:
    papel, status = usuario["papel"], s["status"]
    do_setor = papel in ("solicitante", "gestor") and s["setor_codigo"] == usuario["setor_codigo"]
    acoes: list[str] = []
    if papel == "gestor" and status == "aguardando_gestor" and do_setor and str(s["solicitante_id"]) != usuario["id"]:
        acoes += ["aprovar", "devolver", "reprovar"]
    if papel == "diretoria" and status == "aguardando_diretoria":
        acoes += ["aprovar", "devolver", "reprovar"]
    if do_setor and status == "devolvida" and (papel == "solicitante" or s["aberta_por_gestor"]):
        acoes.append("reenviar")
    if do_setor and status in ("aguardando_gestor", "aguardando_diretoria", "devolvida"):
        acoes.append("anexar")
    if (do_setor and status in ("aguardando_gestor", "aguardando_diretoria", "devolvida")) or (
            papel == "admin" and status in ("aguardando_gestor", "aguardando_diretoria", "devolvida", "aprovada",
                                            "em_cotacao", "aguardando_pedido")):
        acoes.append("cancelar")
    if papel == "comprador":
        if status == "aprovada":
            acoes += ["iniciar_cotacao", "cancelar"]
        elif status == "em_cotacao":
            acoes += ["propostas", "definir_fornecedor", "anexar", "cancelar"]
        elif status == "aguardando_pedido":
            acoes += ["emitir_pedido", "reabrir_cotacao", "anexar", "cancelar"]
        elif status in ("em_pedido", "recebida_parcial"):
            acoes.append("anexar")
    return acoes


def acoes_pedido(usuario: dict, p: dict) -> list[str]:
    papel, status = usuario["papel"], p["status"]
    acoes: list[str] = []
    if papel == "financeiro" and status == "aguardando_financeiro":
        acoes += ["aprovar", "reprovar"]
    if papel == "diretoria" and status == "aguardando_diretoria":
        acoes += ["aprovar", "reprovar"]
    if papel == "comprador":
        if status == "aprovado":
            acoes.append("enviar")
        if status in ("enviado", "entregue_parcial"):
            acoes.append("atualizar_previsao")
        if status == "entregue_parcial":
            acoes.append("encerrar")
    if papel in ("comprador", "admin") and status in ("aguardando_financeiro", "aguardando_diretoria", "aprovado") or (
            papel in ("comprador", "admin") and status == "enviado" and not p.get("percentual_recebido")):
        acoes.append("cancelar")
    if papel == "recebimento" and status in ("enviado", "entregue_parcial"):
        acoes.append("receber")
    return acoes
