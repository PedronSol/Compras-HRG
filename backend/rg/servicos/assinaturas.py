"""Assinatura eletrônica das movimentações com HMAC-SHA-256 (não repúdio e integridade).

hash_autenticidade = HMAC-SHA256(chave_secreta,
    solicitacao_id | usuario_id | timestamp ISO-8601 UTC | IP | conteudo_hash | ação | status)

`conteudo_hash` é o SHA-256 do estado canônico da solicitação no momento da
assinatura (dados, anexos ativos com seus hashes e cotações).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal

from flask import current_app

ACOES = {
    "submissao": ("gestor", "aguardando_adm"),
    "reenvio": ("gestor", "aguardando_adm"),
    "aprovacao_adm": ("adm", "aprovado_adm"),
    "rejeicao_adm": ("adm", "rejeitado_adm"),
    "nova_cotacao_adm": ("adm", "necessita_nova_cotacao"),
    "homologacao": ("compras", "aprovado"),
    "rejeicao_compras": ("compras", "rejeitado_compras"),
}


def _normalizar(valor):
    if isinstance(valor, Decimal):
        return f"{valor:.2f}"
    if isinstance(valor, datetime):
        return valor.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor if valor is None or isinstance(valor, (str, int, float, bool)) else str(valor)


def calcular_conteudo_hash(cur, solicitacao_id: str) -> str:
    cur.execute(
        """select id, codigo, tipo, titulo, descricao, justificativa, setor_codigo, urgencia, status,
                  valor_estimado, valor_final_aprovado, gestor_id, cotacao_vencedora_id, rodada_cotacao,
                  justificativa_adm, justificativa_urgencia, motivo_nova_cotacao, justificativa_compras
             from rg.solicitacoes where id = %s""",
        (solicitacao_id,),
    )
    s = cur.fetchone()
    cur.execute(
        "select sha256, nome_original, origem from rg.anexos"
        " where solicitacao_id = %s and removido_em is null order by sha256",
        (solicitacao_id,),
    )
    anexos = cur.fetchall()
    cur.execute(
        """select f.cnpj, c.valor, c.prazo_entrega_dias, c.selecionada
             from rg.cotacoes c join rg.fornecedores f on f.id = c.fornecedor_id
            where c.solicitacao_id = %s order by f.cnpj""",
        (solicitacao_id,),
    )
    cotacoes = cur.fetchall()
    canonico = {
        "solicitacao": {k: _normalizar(v) for k, v in s.items()},
        "anexos": [{k: _normalizar(v) for k, v in a.items()} for a in anexos],
        "cotacoes": [{k: _normalizar(v) for k, v in c.items()} for c in cotacoes],
    }
    texto = json.dumps(canonico, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _payload(solicitacao_id, usuario_id, assinado_em: datetime, ip, conteudo_hash, acao, status) -> bytes:
    carimbo = assinado_em.astimezone(timezone.utc).isoformat(timespec="microseconds")
    return "|".join([str(solicitacao_id), str(usuario_id), carimbo, ip, conteudo_hash, acao, status]).encode("utf-8")


def calcular_hash(segredo: str, *args) -> str:
    return hmac.new(segredo.encode("utf-8"), _payload(*args), hashlib.sha256).hexdigest()


def assinar(cur, *, solicitacao_id: str, usuario_id: str, acao: str, ip: str, user_agent: str) -> dict:
    tipo, status = ACOES[acao]
    conteudo_hash = calcular_conteudo_hash(cur, solicitacao_id)
    cur.execute("select clock_timestamp() as agora")
    assinado_em = cur.fetchone()["agora"]
    segredo = current_app.config["SIGNATURE_SECRET"]
    hash_aut = calcular_hash(segredo, solicitacao_id, usuario_id, assinado_em, ip, conteudo_hash, acao, status)
    cur.execute(
        """insert into rg.assinaturas (solicitacao_id, usuario_id, tipo, acao, status_resultante, ip, user_agent,
                                       assinado_em, conteudo_hash, hash_autenticidade, algoritmo)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'HMAC-SHA-256')
           returning id, assinado_em, hash_autenticidade""",
        (solicitacao_id, usuario_id, tipo, acao, status, ip, user_agent, assinado_em, conteudo_hash, hash_aut),
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
                             a["conteudo_hash"], a["acao"], a["status_resultante"])
    integro = hmac.compare_digest(esperado, a["hash_autenticidade"])
    atual = calcular_conteudo_hash(cur, str(a["solicitacao_id"]))
    return {
        "id": str(a["id"]),
        "solicitacao_codigo": a["codigo"],
        "usuario_nome": a["usuario_nome"],
        "acao": a["acao"],
        "assinado_em": a["assinado_em"],
        "ip": a["ip"],
        "hash_autenticidade": a["hash_autenticidade"],
        "algoritmo": a["algoritmo"],
        "registro_integro": integro,
        "conteudo_inalterado_desde_assinatura": hmac.compare_digest(atual, a["conteudo_hash"]),
    }
