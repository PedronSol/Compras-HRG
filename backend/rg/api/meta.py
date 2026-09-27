"""Metadados públicos: setores, rótulos, fluxo, limites e perfis de demonstração."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from .. import __version__, rotulos
from ..contas_teste import CONTAS_TESTE, SENHA_TESTE
from ..db import db

bp = Blueprint("meta", __name__)


@bp.get("/meta")
def meta():
    with db.transacao(sistema=True) as cur:
        cur.execute("select codigo, nome, cor, centro_custo, operacional, ativo from rg.setores order by nome")
        setores = cur.fetchall()
    cfg = current_app.config
    demo = cfg["MODO_DEMO"] and cfg["AMBIENTE"] != "producao"
    return jsonify({
        "instituicao": cfg["INSTITUICAO"],
        "sistema": "Compras RG",
        "versao": __version__,
        "setores": setores,
        "rotulos": rotulos.todos(),
        "etapas": rotulos.ETAPAS,
        "sla_dias": rotulos.SLA_DIAS,
        "limites": {
            "max_anexos": 5,
            "max_upload_mb": cfg["MAX_UPLOAD_MB"],
            "justificativa_min": 20,
            "senha_min": cfg["SENHA_MIN_CARACTERES"],
            "tipos_arquivo": ["application/pdf", "image/png", "image/jpeg", "image/webp", "image/tiff",
                              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
        },
        "lgpd": {"termo_versao": cfg["LGPD_TERMO_VERSAO"]},
        "tempo_real": cfg["REALTIME_ENABLED"],
        "demo": demo,
        "contas_teste": ([{"papel": c["papel"], "nome": c["nome"], "email": c["email"], "setor": c["setor_codigo"],
                           "cargo": c["cargo"], "senha": SENHA_TESTE} for c in CONTAS_TESTE] if demo else []),
    })


@bp.get("/saude")
def saude():
    with db.transacao(sistema=True) as cur:
        cur.execute("select 1 as ok")
        cur.fetchone()
    return jsonify({"status": "ok"})
