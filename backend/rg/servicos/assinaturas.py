"""Assinatura eletrônica das movimentações com HMAC-SHA-256 (não repúdio e integridade).

hash_autenticidade = HMAC-SHA256(chave_secreta,
    solicitação | usuário | data/hora UTC | IP | conteudo_hash | ação | status da solicitação | status do pedido
    | pedido | recebimento)

`conteudo_hash` é o SHA-256 do estado canônico no momento da assinatura: dados e itens da
solicitação, documentos ativos (com seus SHA-256), propostas, pedidos e recebimentos.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal

from flask import current_app


def _normalizar(valor):
    if isinstance(valor, Decimal):
        return f"{valor:.3f}"
    if isinstance(valor, datetime):
        return valor.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor if valor is None or isinstance(valor, (str, int, float, bool)) else str(valor)


def _linhas(cur, sql: str, params: tuple) -> list[dict]:
    cur.execute(sql, params)
    return [{k: _normalizar(v) for k, v in linha.items()} for linha in cur.fetchall()]


def calcular_conteudo_hash(cur, solicitacao_id: str) -> str:
    canonico = {
        "solicitacao": _linhas(cur, """
            select id, codigo, tipo, titulo, descricao, justificativa, setor_codigo, urgencia, status, local_entrega,
                   data_necessidade, solicitante_id, comprador_id, cotacao_vencedora_id, valor_final, rodada,
                   justificativa_escolha, motivo_devolucao, motivo_reprovacao, motivo_cancelamento
              from rg.solicitacoes where id = %s""", (solicitacao_id,)),
        "itens": _linhas(cur, """
            select id, material_id, descricao, unidade, quantidade, valor_unitario_estimado
              from rg.solicitacao_itens where solicitacao_id = %s order by id""", (solicitacao_id,)),
        "anexos": _linhas(cur, """
            select sha256, nome_original, origem from rg.anexos
             where solicitacao_id = %s and removido_em is null order by sha256""", (solicitacao_id,)),
        "propostas": _linhas(cur, """
            select f.cnpj, c.frete, c.desconto, c.valor_total, c.prazo_entrega_dias, c.selecionada,
                   (select string_agg(ci.solicitacao_item_id || ':' || ci.quantidade || ':' || ci.valor_unitario, ','
                                      order by ci.solicitacao_item_id) from rg.cotacao_itens ci where ci.cotacao_id = c.id) as itens
              from rg.cotacoes c join rg.fornecedores f on f.id = c.fornecedor_id
             where c.solicitacao_id = %s order by f.cnpj""", (solicitacao_id,)),
        "pedidos": _linhas(cur, """
            select codigo, status, valor_total, fornecedor_id, data_prevista_entrega
              from rg.pedidos where solicitacao_id = %s order by codigo""", (solicitacao_id,)),
        "recebimentos": _linhas(cur, """
            select r.codigo, r.nota_fiscal, r.situacao,
                   (select string_agg(ri.pedido_item_id || ':' || ri.quantidade_recebida || ':' || ri.quantidade_aceita, ','
                                      order by ri.pedido_item_id) from rg.recebimento_itens ri where ri.recebimento_id = r.id) as itens
              from rg.recebimentos r where r.solicitacao_id = %s order by r.codigo""", (solicitacao_id,)),
    }
    texto = json.dumps(canonico, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _payload(solicitacao_id, usuario_id, assinado_em: datetime, ip, conteudo_hash, acao, status_solicitacao,
             status_pedido, pedido_id, recebimento_id) -> bytes:
    carimbo = assinado_em.astimezone(timezone.utc).isoformat(timespec="microseconds")
    partes = [solicitacao_id, usuario_id, carimbo, ip, conteudo_hash, acao, status_solicitacao,
              status_pedido or "", pedido_id or "", recebimento_id or ""]
    return "|".join(str(p) for p in partes).encode("utf-8")


def calcular_hash(segredo: str, *args) -> str:
    return hmac.new(segredo.encode("utf-8"), _payload(*args), hashlib.sha256).hexdigest()


def assinar(cur, *, solicitacao_id: str, usuario: dict, acao: str, ip: str, user_agent: str,
            pedido_id: str | None = None, recebimento_id: str | None = None) -> dict:
    """Registra a assinatura com os status resultantes lidos do banco (após as triggers)."""
    cur.execute("select status::text as s from rg.solicitacoes where id = %s", (solicitacao_id,))
    status_solicitacao = cur.fetchone()["s"]
    status_pedido = None
    if pedido_id:
        cur.execute("select status::text as s from rg.pedidos where id = %s", (pedido_id,))
        status_pedido = cur.fetchone()["s"]
    conteudo_hash = calcular_conteudo_hash(cur, solicitacao_id)
    cur.execute("select clock_timestamp() as agora")
    assinado_em = cur.fetchone()["agora"]
    segredo = current_app.config["SIGNATURE_SECRET"]
    hash_aut = calcular_hash(segredo, solicitacao_id, usuario["id"], assinado_em, ip, conteudo_hash, acao,
                             status_solicitacao, status_pedido, pedido_id, recebimento_id)
    cur.execute(
        """insert into rg.assinaturas (solicitacao_id, pedido_id, recebimento_id, usuario_id, papel, acao,
                                       status_solicitacao, status_pedido, ip, user_agent, assinado_em, conteudo_hash,
                                       hash_autenticidade)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           returning id, assinado_em, hash_autenticidade""",
        (solicitacao_id, pedido_id, recebimento_id, usuario["id"], usuario["papel"], acao, status_solicitacao,
         status_pedido, ip, user_agent, assinado_em, conteudo_hash, hash_aut),
    )
    return cur.fetchone()


def verificar(cur, assinatura_id: str) -> dict | None:
    cur.execute(
        """select a.*, u.nome as usuario_nome, s.codigo
             from rg.assinaturas a
             join rg.solicitacoes s on s.id = a.solicitacao_id
             left join rg.v_usuarios_publico u on u.id = a.usuario_id
            where a.id = %s""",
        (assinatura_id,),
    )
    a = cur.fetchone()
    if not a:
        return None
    segredo = current_app.config["SIGNATURE_SECRET"]
    esperado = calcular_hash(segredo, a["solicitacao_id"], a["usuario_id"], a["assinado_em"], a["ip"],
                             a["conteudo_hash"], a["acao"], a["status_solicitacao"], a["status_pedido"],
                             a["pedido_id"], a["recebimento_id"])
    atual = calcular_conteudo_hash(cur, str(a["solicitacao_id"]))
    return {
        "id": str(a["id"]),
        "solicitacao_codigo": a["codigo"],
        "usuario_nome": a["usuario_nome"],
        "papel": a["papel"],
        "acao": a["acao"],
        "assinado_em": a["assinado_em"],
        "ip": a["ip"],
        "hash_autenticidade": a["hash_autenticidade"],
        "algoritmo": a["algoritmo"],
        "registro_integro": hmac.compare_digest(esperado, a["hash_autenticidade"]),
        "conteudo_inalterado_desde_assinatura": hmac.compare_digest(atual, a["conteudo_hash"]),
    }
