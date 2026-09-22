"""Canal WebSocket (/ws) autenticado pelo cookie de sessão."""
from __future__ import annotations

import json
import time
from urllib.parse import urlparse

from flask import Flask, current_app, request

from ..extensoes import sock
from ..seguranca.sessao import buscar_sessao
from ..servicos.tempo_real import Conexao, hub

INTERVALO_REVALIDACAO = 60


def _origem_permitida() -> bool:
    origem = request.headers.get("Origin")
    if not origem:
        return False
    return urlparse(origem).netloc == request.host


def registrar(app: Flask) -> None:
    @sock.route("/ws")
    def canal(ws):
        if not current_app.config["REALTIME_ENABLED"] or not _origem_permitida():
            ws.close(1008, "Origem não permitida")
            return
        token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
        resultado = buscar_sessao(token, tocar=False)
        if not resultado:
            ws.close(4401, "Sessão inválida")
            return
        usuario, _ = resultado
        conexao = Conexao(ws, usuario, token)
        hub.registrar(conexao)
        conexao.enviar({"tipo": "conectado", "usuario": usuario["id"]})
        ultima_validacao = time.monotonic()
        try:
            while True:
                mensagem = ws.receive(timeout=25)
                if mensagem is None:
                    conexao.enviar({"tipo": "ping"})
                else:
                    try:
                        dados = json.loads(mensagem)
                    except ValueError:
                        dados = {}
                    if dados.get("tipo") == "ping":
                        conexao.enviar({"tipo": "pong"})
                if time.monotonic() - ultima_validacao > INTERVALO_REVALIDACAO:
                    ultima_validacao = time.monotonic()
                    atual = buscar_sessao(token, tocar=False)
                    if not atual or atual[0]["papel"] != conexao.papel or atual[0]["setor_codigo"] != conexao.setor:
                        ws.close(4401, "Sessão encerrada")
                        break
        except Exception:
            pass
        finally:
            hub.remover(conexao)
