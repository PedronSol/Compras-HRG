"""Registro dos blueprints da API REST (/api/v1)."""
from __future__ import annotations

from flask import Flask


def registrar_api(app: Flask) -> None:
    from . import (anexos, auditoria, auth, busca, fornecedores, meta, notificacoes, painel, servicos,
                   solicitacoes, usuarios, ws)

    for modulo in (meta, auth, usuarios, solicitacoes, anexos, fornecedores, servicos, notificacoes, painel,
                   auditoria, busca):
        app.register_blueprint(modulo.bp, url_prefix="/api/v1")
    ws.registrar(app)
