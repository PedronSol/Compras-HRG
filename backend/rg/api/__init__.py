"""Registro dos blueprints da API REST (/api/v1)."""
from __future__ import annotations

from flask import Flask


def registrar_api(app: Flask) -> None:
    from . import (alertas, anexos, aprovacoes, auditoria, auth, busca, fornecedores, materiais, meta, notificacoes,
                   painel, pedidos, solicitacoes, usuarios, ws)

    for modulo in (meta, auth, usuarios, solicitacoes, pedidos, aprovacoes, anexos, fornecedores, materiais, alertas,
                   notificacoes, painel, auditoria, busca):
        app.register_blueprint(modulo.bp, url_prefix="/api/v1")
    ws.registrar(app)
