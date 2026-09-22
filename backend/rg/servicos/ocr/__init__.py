"""Fila de processamento de OCR em segundo plano."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from psycopg.types.json import Jsonb

from ...db import db
from ..arquivos import armazenamento
from .analise import analisar
from .extracao import MotorIndisponivel, extrair_texto, motor

log = logging.getLogger("rg.ocr")


class FilaOCR:
    def __init__(self) -> None:
        self._executor: ThreadPoolExecutor | None = None
        self.habilitado = True
        self.sincrono = False
        self.max_paginas = 8

    def configurar(self, *, habilitado: bool, workers: int, max_paginas: int, tesseract_cmd: str,
                   sincrono: bool = False) -> None:
        self.habilitado = habilitado
        self.sincrono = sincrono
        self.max_paginas = max_paginas
        motor.configurar(tesseract_cmd)
        if habilitado and not sincrono and self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="rg-ocr")

    def enfileirar(self, anexo_ids: list[str]) -> None:
        for anexo_id in anexo_ids:
            if self.sincrono or self._executor is None:
                self.processar(anexo_id)
            else:
                self._executor.submit(self._seguro, anexo_id)

    def _seguro(self, anexo_id: str) -> None:
        try:
            self.processar(anexo_id)
        except Exception:  # falhas não podem derrubar o worker
            log.exception("Falha inesperada no OCR do anexo %s", anexo_id)

    def processar(self, anexo_id: str) -> None:
        with db.transacao(sistema=True) as cur:
            cur.execute(
                "update rg.anexos set ocr_status = 'processando', ocr_erro = null"
                " where id = %s and removido_em is null returning caminho, mime",
                (anexo_id,),
            )
            anexo = cur.fetchone()
        if not anexo:
            return
        if not self.habilitado:
            self._finalizar(anexo_id, "nao_suportado", erro="OCR desativado nesta instalação")
            return
        try:
            dados = armazenamento.ler(anexo["caminho"])
            resultado = extrair_texto(dados, anexo["mime"], self.max_paginas)
            campos = analisar(resultado.texto)
            campos["paginas_processadas"] = resultado.paginas
            self._finalizar(anexo_id, "concluido", texto=resultado.texto[:200_000], dados=campos,
                            motor_nome=resultado.motor)
        except MotorIndisponivel as exc:
            self._finalizar(anexo_id, "nao_suportado", erro=str(exc))
        except Exception as exc:
            log.exception("Erro ao processar OCR do anexo %s", anexo_id)
            self._finalizar(anexo_id, "falhou", erro=f"Não foi possível ler o documento: {exc.__class__.__name__}")

    def _finalizar(self, anexo_id: str, status: str, *, texto: str | None = None, dados: dict | None = None,
                   motor_nome: str | None = None, erro: str | None = None) -> None:
        with db.transacao(sistema=True) as cur:
            cur.execute(
                """update rg.anexos set ocr_status = %s, ocr_texto = %s, dados_ocr = %s, ocr_motor = %s,
                          ocr_erro = %s, ocr_processado_em = now()
                    where id = %s""",
                (status, texto, Jsonb(dados) if dados is not None else None, motor_nome, erro, anexo_id),
            )

    def recuperar_pendentes(self) -> int:
        """Reprocessa anexos que ficaram pendentes (ex.: reinício do servidor)."""
        with db.transacao(sistema=True) as cur:
            cur.execute("select id from rg.anexos where ocr_status in ('pendente', 'processando')"
                        " and removido_em is null and criado_em > now() - interval '7 days'")
            ids = [str(r["id"]) for r in cur.fetchall()]
        self.enfileirar(ids)
        return len(ids)

    def encerrar(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None


fila_ocr = FilaOCR()
