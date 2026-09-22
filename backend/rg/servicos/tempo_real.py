"""Tempo real: LISTEN/NOTIFY do PostgreSQL → WebSocket dos usuários conectados.

Cada instância da API escuta o canal `rg_eventos` e entrega os eventos apenas
aos seus próprios clientes, respeitando o mesmo escopo de visibilidade do RLS.
Funciona com várias instâncias sem broker adicional.
"""
from __future__ import annotations

import json
import logging
import threading
import time

from ..db import db

log = logging.getLogger("rg.tempo_real")

STATUS_COMPRAS = {"aprovado_adm", "em_cotacao", "aprovado", "rejeitado_compras"}


class Conexao:
    __slots__ = ("ws", "usuario_id", "papel", "setor", "lock", "token")

    def __init__(self, ws, usuario: dict, token: str):
        self.ws = ws
        self.usuario_id = usuario["id"]
        self.papel = usuario["papel"]
        self.setor = usuario["setor_codigo"]
        self.lock = threading.Lock()
        self.token = token

    def enviar(self, mensagem: dict) -> bool:
        try:
            with self.lock:
                self.ws.send(json.dumps(mensagem, default=str))
            return True
        except Exception:
            return False


def pode_ver(conexao: Conexao, evento: dict) -> bool:
    tabela = evento.get("tabela")
    if tabela == "notificacoes":
        return evento.get("destinatario") == conexao.usuario_id
    if tabela == "usuarios":
        return conexao.papel == "admin" or evento.get("usuario") == conexao.usuario_id
    if conexao.papel == "admin":
        return True
    setor = evento.get("setor")
    if tabela == "servicos_programados" or (tabela == "anexos" and evento.get("servico_id")):
        return conexao.papel == "compras" or setor == conexao.setor
    if tabela in ("solicitacoes", "cotacoes", "anexos"):
        if conexao.papel == "gestor":
            return setor == conexao.setor
        if conexao.papel == "compras":
            return evento.get("status") in STATUS_COMPRAS
    return False


class Hub:
    def __init__(self) -> None:
        self._conexoes: set[Conexao] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()

    def registrar(self, conexao: Conexao) -> None:
        with self._lock:
            self._conexoes.add(conexao)

    def remover(self, conexao: Conexao) -> None:
        with self._lock:
            self._conexoes.discard(conexao)

    @property
    def total(self) -> int:
        return len(self._conexoes)

    def despachar(self, evento: dict) -> int:
        with self._lock:
            alvos = [c for c in self._conexoes if pode_ver(c, evento)]
        mensagem = {"tipo": "evento", **evento}
        entregues = 0
        for conexao in alvos:
            if conexao.enviar(mensagem):
                entregues += 1
            else:
                self.remover(conexao)
        return entregues

    def iniciar_escuta(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, name="rg-listen", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()

    def _loop(self) -> None:
        espera = 1.0
        while not self._parar.is_set():
            try:
                with db.conexao_dedicada() as conn:
                    conn.execute("listen rg_eventos")
                    log.info("Escutando eventos em tempo real (LISTEN rg_eventos)")
                    espera = 1.0
                    while not self._parar.is_set():
                        for notificacao in conn.notifies(timeout=5.0):
                            try:
                                self.despachar(json.loads(notificacao.payload))
                            except (ValueError, TypeError):
                                log.warning("Evento inválido: %s", notificacao.payload[:200])
            except Exception as exc:
                log.warning("Conexão LISTEN perdida (%s); nova tentativa em %.0fs", exc, espera)
                self._parar.wait(espera)
                espera = min(espera * 2, 30.0)


hub = Hub()


class Agendador:
    """Rotinas periódicas: alertas de SLA e limpeza de sessões. Usa advisory lock para
    que apenas uma instância execute cada ciclo."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._parar = threading.Event()
        self.intervalo = 300

    def iniciar(self, intervalo: int) -> None:
        self.intervalo = max(30, intervalo)
        if self._thread and self._thread.is_alive():
            return
        self._parar.clear()
        self._thread = threading.Thread(target=self._loop, name="rg-agendador", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()

    def executar_ciclo(self) -> int:
        with db.transacao(sistema=True) as cur:
            cur.execute("select pg_try_advisory_xact_lock(727002) as ok")
            if not cur.fetchone()["ok"]:
                return 0
            cur.execute("select rg.processar_alertas_sla() as qtd")
            qtd = cur.fetchone()["qtd"]
            cur.execute("delete from rg.sessoes where expira_em < now() - interval '30 days'"
                        " or revogada_em < now() - interval '30 days'")
        return qtd

    def _loop(self) -> None:
        self._parar.wait(10)
        while not self._parar.is_set():
            inicio = time.monotonic()
            try:
                qtd = self.executar_ciclo()
                if qtd:
                    log.info("Alertas de SLA emitidos: %s", qtd)
            except Exception:
                log.exception("Falha no ciclo do agendador")
            self._parar.wait(max(5.0, self.intervalo - (time.monotonic() - inicio)))


agendador = Agendador()
