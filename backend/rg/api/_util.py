"""Utilitários comuns às rotas."""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from flask import Response, current_app, request

from ..errors import ApiError, ValidacaoError
from ..validacao import Campo, validar


def corpo_json() -> dict:
    if request.mimetype == "multipart/form-data":
        return request.form.to_dict()
    dados = request.get_json(silent=True)
    if dados is None:
        if request.content_length:
            raise ApiError("JSON inválido", 400, "json_invalido")
        return {}
    if not isinstance(dados, dict):
        raise ApiError("O corpo da requisição deve ser um objeto JSON", 400, "json_invalido")
    return dados


def paginacao(padrao: int = 25, maximo: int = 100) -> tuple[int, int]:
    try:
        pagina = max(1, int(request.args.get("pagina", 1)))
        por_pagina = min(maximo, max(1, int(request.args.get("por_pagina", padrao))))
    except ValueError:
        raise ApiError("Parâmetros de paginação inválidos", 400, "paginacao") from None
    return pagina, por_pagina


def hoje() -> date:
    from datetime import datetime
    return datetime.now(ZoneInfo(current_app.config["TIMEZONE"])).date()


def periodo(dias_padrao: int = 90) -> tuple[date, date]:
    args = validar(request.args.to_dict(), [Campo("inicio", "data"), Campo("fim", "data")])
    fim = args.get("fim") or hoje()
    inicio = args.get("inicio") or (fim - timedelta(days=dias_padrao))
    if inicio > fim:
        raise ValidacaoError({"inicio": "A data inicial deve ser anterior à final"})
    if (fim - inicio).days > 3 * 366:
        raise ValidacaoError({"inicio": "Período máximo de 3 anos"})
    return inicio, fim


def resposta_csv(nome: str, cabecalho: list[str], linhas: list[list]) -> Response:
    buffer = io.StringIO()
    buffer.write("﻿")  # BOM para abertura correta no Excel
    escritor = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    escritor.writerow(cabecalho)
    for linha in linhas:
        escritor.writerow([_celula_segura(c) for c in linha])
    return Response(buffer.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


def _celula_segura(valor) -> str:
    """Neutraliza injeção de fórmulas em planilhas (CSV injection)."""
    if valor is None:
        return ""
    texto = str(valor)
    if texto[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + texto
    return texto


def resposta_pdf(conteudo: bytes, nome: str, inline: bool = False) -> Response:
    disposicao = "inline" if inline else "attachment"
    return Response(conteudo, mimetype="application/pdf",
                    headers={"Content-Disposition": f'{disposicao}; filename="{nome}"'})
