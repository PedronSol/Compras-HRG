"""Sessões server-side com cookie HttpOnly, proteção CSRF e controle de acesso por papel (RBAC)."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from functools import wraps

from flask import current_app, g, request

from ..db import db
from ..errors import ApiError, Proibido

METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}
ENDPOINTS_TROCA_SENHA = {"auth.me", "auth.trocar_senha", "auth.logout", "meta.meta"}


def ip_cliente() -> str:
    return (request.remote_addr or "desconhecido")[:64]


def user_agent() -> str:
    return (request.headers.get("User-Agent") or "")[:300]


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar_sessao(cur, usuario_id: str) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    cur.execute(
        "insert into rg.sessoes (usuario_id, token_hash, csrf_token, ip, user_agent, expira_em)"
        " values (%s, %s, %s, %s, %s, now() + make_interval(hours => %s))",
        (usuario_id, hash_token(token), csrf, ip_cliente(), user_agent(),
         current_app.config["SESSION_ABSOLUTE_HOURS"]),
    )
    return token, csrf


def definir_cookie(resposta, token: str) -> None:
    cfg = current_app.config
    resposta.set_cookie(
        cfg["SESSION_COOKIE_NAME"], token,
        max_age=cfg["SESSION_ABSOLUTE_HOURS"] * 3600,
        httponly=True, secure=cfg["SESSION_COOKIE_SECURE"], samesite="Strict", path="/",
    )


def remover_cookie(resposta) -> None:
    cfg = current_app.config
    resposta.delete_cookie(cfg["SESSION_COOKIE_NAME"], path="/", secure=cfg["SESSION_COOKIE_SECURE"],
                           httponly=True, samesite="Strict")


def buscar_sessao(token: str | None, *, tocar: bool = True) -> tuple[dict, dict] | None:
    """Valida o token e retorna (usuario, sessao) ou None."""
    if not token or len(token) > 128:
        return None
    cfg = current_app.config
    with db.transacao(sistema=True, ip=ip_cliente()) as cur:
        cur.execute(
            """
            select s.id as sessao_id, s.csrf_token, s.criado_em as sessao_criada_em,
                   (now() - s.ultimo_acesso_em) > interval '60 seconds' as precisa_tocar,
                   u.id, u.nome, u.email, u.papel, u.setor_codigo, u.status, u.cargo,
                   u.troca_senha_obrigatoria, st.nome as setor_nome, st.cor as setor_cor
              from rg.sessoes s
              join rg.usuarios u on u.id = s.usuario_id
              join rg.setores st on st.codigo = u.setor_codigo
             where s.token_hash = %s
               and s.revogada_em is null
               and s.expira_em > now()
               and s.ultimo_acesso_em > now() - make_interval(mins => %s)
            """,
            (hash_token(token), cfg["SESSION_IDLE_MINUTES"]),
        )
        linha = cur.fetchone()
        if not linha:
            return None
        if linha["status"] != "aprovado":
            cur.execute("update rg.sessoes set revogada_em = now() where id = %s", (linha["sessao_id"],))
            return None
        if tocar and linha["precisa_tocar"]:
            cur.execute("update rg.sessoes set ultimo_acesso_em = now() where id = %s", (linha["sessao_id"],))
    usuario = {
        "id": str(linha["id"]), "nome": linha["nome"], "email": linha["email"], "papel": linha["papel"],
        "setor_codigo": linha["setor_codigo"], "setor_nome": linha["setor_nome"], "setor_cor": linha["setor_cor"],
        "cargo": linha["cargo"], "troca_senha_obrigatoria": linha["troca_senha_obrigatoria"],
    }
    sessao = {"id": str(linha["sessao_id"]), "csrf_token": linha["csrf_token"]}
    return usuario, sessao


def carregar_contexto() -> None:
    """before_request: identifica o usuário e valida CSRF em métodos de escrita."""
    g.usuario = None
    g.sessao = None
    if not request.path.startswith("/api/"):
        return
    token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    resultado = buscar_sessao(token)
    if resultado:
        g.usuario, g.sessao = resultado

    if request.method not in METODOS_SEGUROS:
        tipo = (request.mimetype or "").lower()
        if request.content_length and tipo not in ("application/json", "multipart/form-data"):
            raise ApiError("Tipo de conteúdo não suportado", 415, "tipo_conteudo")
        if g.sessao:
            enviado = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(enviado, g.sessao["csrf_token"]):
                raise ApiError("Token CSRF inválido ou ausente. Recarregue a página.", 403, "csrf")


def requer_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not g.get("usuario"):
            raise ApiError("Sessão expirada ou inexistente. Faça login novamente.", 401, "nao_autenticado")
        if g.usuario["troca_senha_obrigatoria"] and request.endpoint not in ENDPOINTS_TROCA_SENHA:
            raise ApiError("Defina uma nova senha para continuar", 403, "troca_senha_obrigatoria")
        return fn(*args, **kwargs)
    return wrapper


def requer_papel(*papeis: str):
    def decorador(fn):
        @requer_login
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.usuario["papel"] not in papeis:
                raise Proibido()
            return fn(*args, **kwargs)
        return wrapper
    return decorador


def tx(observacao: str | None = None):
    """Transação no contexto do usuário autenticado (RLS aplicado)."""
    return db.transacao(usuario_id=g.usuario["id"], ip=ip_cliente(), observacao=observacao)


def tx_sistema():
    usuario_id = g.usuario["id"] if g.get("usuario") else None
    return db.transacao(usuario_id=usuario_id, sistema=True, ip=ip_cliente())


def registrar_evento(cur, operacao: str, tabela: str, registro: str | None, detalhes: dict | None = None) -> None:
    from psycopg.types.json import Jsonb
    cur.execute("select audit.registrar_evento(%s, %s, %s, %s)",
                (operacao, tabela, registro, Jsonb(detalhes) if detalhes is not None else None))
