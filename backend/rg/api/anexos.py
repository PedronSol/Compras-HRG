"""Download de anexos (decifrados sob demanda) e remoção lógica. Nenhum conteúdo é lido automaticamente."""
from __future__ import annotations

from urllib.parse import quote

from flask import Blueprint, Response, g, jsonify, request

from ..errors import ApiError, NaoEncontrado
from ..seguranca.sessao import registrar_evento, requer_login, tx
from ..servicos.arquivos import armazenamento

bp = Blueprint("anexos", __name__)


def _obter(cur, anexo_id: str) -> dict:
    cur.execute("""select a.*, u.nome as enviado_por_nome from rg.anexos a
                   left join rg.v_usuarios_publico u on u.id = a.enviado_por where a.id = %s""", (anexo_id,))
    a = cur.fetchone()
    if not a:
        raise NaoEncontrado("Anexo não encontrado ou fora do seu escopo de acesso")
    return a


@bp.get("/anexos/<uuid:anexo_id>")
@requer_login
def detalhar(anexo_id):
    with tx() as cur:
        a = _obter(cur, str(anexo_id))
    a.pop("caminho", None)
    return jsonify(a)


@bp.get("/anexos/<uuid:anexo_id>/arquivo")
@requer_login
def baixar(anexo_id):
    with tx() as cur:
        a = _obter(cur, str(anexo_id))
        registrar_evento(cur, "DOWNLOAD_ANEXO", "rg.anexos", str(anexo_id), {"arquivo": a["nome_original"]})
    try:
        conteudo = armazenamento.ler(a["caminho"])
    except FileNotFoundError:
        raise ApiError("Arquivo indisponível no armazenamento", 410, "arquivo_indisponivel") from None
    disposicao = "inline" if request.args.get("inline") == "1" and a["mime"] in (
        "application/pdf", "image/png", "image/jpeg", "image/webp") else "attachment"
    nome = quote(a["nome_original"])
    return Response(conteudo, mimetype=a["mime"], headers={
        "Content-Disposition": f"{disposicao}; filename*=UTF-8''{nome}",
        "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'",
        "X-Content-SHA256": a["sha256"],
    })


@bp.delete("/anexos/<uuid:anexo_id>")
@requer_login
def remover(anexo_id):
    with tx() as cur:
        a = _obter(cur, str(anexo_id))
        if a["removido_em"]:
            raise ApiError("Anexo já removido", 422, "anexo_removido")
        cur.execute("select 1 from rg.cotacoes where anexo_id = %s", (str(anexo_id),))
        if cur.fetchone():
            raise ApiError("O documento está vinculado a uma proposta", 422, "anexo_vinculado")
        cur.execute("update rg.anexos set removido_em = now() where id = %s", (str(anexo_id),))
        if cur.rowcount != 1:
            raise ApiError("Você não pode remover este anexo nesta etapa", 403, "proibido")
    return jsonify({"ok": True})
