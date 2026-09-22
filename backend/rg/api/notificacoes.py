"""Central de notificações do usuário."""
from __future__ import annotations

from flask import Blueprint, g, jsonify, request

from ..errors import NaoEncontrado
from ..seguranca.sessao import requer_login, tx

bp = Blueprint("notificacoes", __name__)


@bp.get("/notificacoes")
@requer_login
def listar():
    somente_nao_lidas = request.args.get("nao_lidas") == "1"
    try:
        limite = min(100, max(1, int(request.args.get("limite", 30))))
    except ValueError:
        limite = 30
    with tx() as cur:
        cur.execute("select id, tipo, titulo, mensagem, link, lida, criado_em from rg.notificacoes"
                    " where destinatario_id = %s and (not %s or not lida) order by criado_em desc limit %s",
                    (g.usuario["id"], somente_nao_lidas, limite))
        itens = cur.fetchall()
        cur.execute("select count(*) as n from rg.notificacoes where destinatario_id = %s and not lida",
                    (g.usuario["id"],))
        nao_lidas = cur.fetchone()["n"]
    return jsonify({"itens": itens, "nao_lidas": nao_lidas})


@bp.post("/notificacoes/<uuid:notificacao_id>/lida")
@requer_login
def marcar(notificacao_id):
    with tx() as cur:
        cur.execute("update rg.notificacoes set lida = true, lida_em = now() where id = %s and not lida",
                    (str(notificacao_id),))
        if cur.rowcount == 0:
            cur.execute("select 1 from rg.notificacoes where id = %s", (str(notificacao_id),))
            if not cur.fetchone():
                raise NaoEncontrado("Notificação não encontrada")
    return jsonify({"ok": True})


@bp.post("/notificacoes/lidas")
@requer_login
def marcar_todas():
    with tx() as cur:
        cur.execute("update rg.notificacoes set lida = true, lida_em = now() where destinatario_id = %s and not lida",
                    (g.usuario["id"],))
        total = cur.rowcount
    return jsonify({"atualizadas": total})
