"""Metadados públicos: setores, rótulos e limites usados pelo frontend."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify

from .. import rotulos
from ..contas_teste import CONTAS_TESTE, SENHA_TESTE
from ..db import db

bp = Blueprint("meta", __name__)


@bp.get("/meta")
def meta():
    with db.transacao(sistema=True) as cur:
        cur.execute("select codigo, nome, cor, operacional, ativo from rg.setores order by nome")
        setores = cur.fetchall()
    cfg = current_app.config
    return jsonify({
        "instituicao": cfg["INSTITUICAO"],
        "versao": "1.0.0",
        "setores": setores,
        "rotulos": {
            "papel": rotulos.PAPEL,
            "status_usuario": rotulos.STATUS_USUARIO,
            "tipo_solicitacao": rotulos.TIPO_SOLICITACAO,
            "urgencia": rotulos.URGENCIA,
            "status_solicitacao": rotulos.STATUS_SOLICITACAO,
            "sla_situacao": rotulos.SLA_SITUACAO,
            "tipo_documento": rotulos.TIPO_DOCUMENTO,
            "categoria_servico": rotulos.CATEGORIA_SERVICO,
            "periodicidade": rotulos.PERIODICIDADE,
            "situacao_servico": rotulos.SITUACAO_SERVICO,
            "acao_assinatura": rotulos.ACAO_ASSINATURA,
        },
        "sla_dias": rotulos.SLA_DIAS,
        "limites": {
            "max_anexos": 3,
            "max_upload_mb": cfg["MAX_UPLOAD_MB"],
            "justificativa_min": 20,
            "senha_min": cfg["SENHA_MIN_CARACTERES"],
            "tipos_arquivo": ["application/pdf", "image/png", "image/jpeg", "image/webp", "image/tiff",
                              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
        },
        "lgpd": {"termo_versao": cfg["LGPD_TERMO_VERSAO"]},
        "tempo_real": cfg["REALTIME_ENABLED"],
        "contas_teste": ([{"papel": c["papel"], "nome": c["nome"], "email": c["email"], "senha": SENHA_TESTE}
                          for c in CONTAS_TESTE] if cfg["AMBIENTE"] != "producao" else []),
    })


@bp.get("/saude")
def saude():
    with db.transacao(sistema=True) as cur:
        cur.execute("select 1 as ok")
        cur.fetchone()
    return jsonify({"status": "ok"})
