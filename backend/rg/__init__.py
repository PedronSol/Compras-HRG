"""RG Hospital — Plataforma corporativa de solicitações, aprovações e serviços programados."""
from __future__ import annotations

import atexit
import logging
import os

from flask import Flask, abort, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .db import db
from .errors import registrar_handlers
from .extensoes import ProvedorJSON, limiter, sock
from .seguranca.cabecalhos import aplicar_cabecalhos
from .seguranca.cripto import cofre
from .seguranca.sessao import carregar_contexto
from .servicos.arquivos import armazenamento
from .servicos.ocr import fila_ocr
from .servicos.tempo_real import agendador, hub

__version__ = "1.0.0"


def create_app(config: Config | None = None) -> Flask:
    config = config or Config()
    config.validar()

    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(config.as_dict())
    app.json = ProvedorJSON(app)
    app.config["RATELIMIT_ENABLED"] = not config.TESTING or getattr(config, "RATELIMIT_ENABLED", False)

    logging.basicConfig(
        level=logging.INFO if not config.TESTING else logging.WARNING,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    if config.TRUSTED_PROXIES:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=config.TRUSTED_PROXIES, x_proto=config.TRUSTED_PROXIES,
                                x_host=config.TRUSTED_PROXIES)

    cofre.configurar(config.ENCRYPTION_KEYS)
    armazenamento.configurar(config.STORAGE_DIR)
    db.init_app(app)
    limiter.init_app(app)
    sock.init_app(app)
    fila_ocr.configurar(habilitado=config.OCR_ENABLED, workers=config.OCR_WORKERS,
                        max_paginas=config.OCR_MAX_PAGINAS, tesseract_cmd=config.TESSERACT_CMD,
                        sincrono=getattr(config, "OCR_SINCRONO", False))

    registrar_handlers(app)
    app.before_request(carregar_contexto)
    app.after_request(aplicar_cabecalhos)

    from .api import registrar_api
    registrar_api(app)

    if config.SERVE_FRONTEND:
        _servir_frontend(app)

    if config.BACKGROUND_JOBS and not config.TESTING and _processo_principal():
        if config.REALTIME_ENABLED:
            hub.iniciar_escuta()
        agendador.iniciar(config.SLA_JOB_INTERVAL_SECONDS)
        try:
            fila_ocr.recuperar_pendentes()
        except Exception:
            logging.getLogger("rg").exception("Falha ao recuperar OCR pendente")

        def _encerrar():
            hub.parar()
            agendador.parar()
            fila_ocr.encerrar()
            db.close()
        atexit.register(_encerrar)

    return app


def _processo_principal() -> bool:
    """Evita iniciar rotinas duas vezes com o reloader do servidor de desenvolvimento."""
    return os.environ.get("WERKZEUG_RUN_MAIN") != "false"


def _servir_frontend(app: Flask) -> None:
    raiz = app.config["FRONTEND_DIR"]

    @app.get("/", defaults={"caminho": ""})
    @app.get("/<path:caminho>")
    def frontend(caminho: str):
        if caminho.startswith("api/") or caminho == "ws":
            abort(404)
        alvo = (raiz / caminho).resolve() if caminho else None
        if alvo and alvo.is_file() and raiz.resolve() in alvo.parents:
            resposta = send_from_directory(raiz, caminho)
            if caminho == "sw.js":
                resposta.headers["Service-Worker-Allowed"] = "/"
            return resposta
        if caminho and "." in caminho.rsplit("/", 1)[-1]:
            abort(404)
        return send_from_directory(raiz, "index.html")
