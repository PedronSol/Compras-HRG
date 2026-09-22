"""Erros de API e tradução de erros do PostgreSQL para respostas HTTP."""
from __future__ import annotations

import logging

import psycopg
from flask import jsonify
from psycopg import errors as pgerr
from werkzeug.exceptions import HTTPException

log = logging.getLogger("rg.errors")


class ApiError(Exception):
    def __init__(self, mensagem: str, status: int = 400, codigo: str = "erro", campos: dict | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.codigo = codigo
        self.campos = campos or {}

    def to_response(self):
        corpo = {"erro": {"codigo": self.codigo, "mensagem": self.mensagem}}
        if self.campos:
            corpo["erro"]["campos"] = self.campos
        return jsonify(corpo), self.status


class ValidacaoError(ApiError):
    def __init__(self, campos: dict[str, str], mensagem: str = "Verifique os campos destacados"):
        super().__init__(mensagem, 422, "validacao", campos)


class NaoEncontrado(ApiError):
    def __init__(self, mensagem: str = "Registro não encontrado ou sem permissão de acesso"):
        super().__init__(mensagem, 404, "nao_encontrado")


class Proibido(ApiError):
    def __init__(self, mensagem: str = "Você não tem permissão para esta ação"):
        super().__init__(mensagem, 403, "proibido")


class Conflito(ApiError):
    def __init__(self, mensagem: str):
        super().__init__(mensagem, 409, "conflito")


def _mensagem_pg(exc: psycopg.Error) -> str:
    diag = getattr(exc, "diag", None)
    return (diag.message_primary if diag and diag.message_primary else str(exc)).strip()


def traduzir_erro_pg(exc: psycopg.Error) -> ApiError:
    if isinstance(exc, pgerr.RaiseException):
        return ApiError(_mensagem_pg(exc), 422, "regra_negocio")
    if isinstance(exc, pgerr.InsufficientPrivilege):
        msg = _mensagem_pg(exc)
        if "row-level security" in msg:
            msg = "Operação não permitida para o seu perfil ou setor"
        return Proibido(msg)
    if isinstance(exc, pgerr.UniqueViolation):
        return Conflito("Registro duplicado: já existe um cadastro com estes dados")
    if isinstance(exc, pgerr.ForeignKeyViolation):
        return ApiError("Referência inválida a outro registro", 422, "referencia_invalida")
    if isinstance(exc, (pgerr.CheckViolation, pgerr.NotNullViolation, pgerr.InvalidTextRepresentation,
                        pgerr.NumericValueOutOfRange, pgerr.StringDataRightTruncation)):
        return ApiError("Dados inválidos: " + _mensagem_pg(exc), 422, "dados_invalidos")
    if isinstance(exc, pgerr.SerializationFailure) or isinstance(exc, pgerr.DeadlockDetected):
        return Conflito("Conflito de concorrência. Tente novamente.")
    log.exception("Erro de banco não tratado", exc_info=exc)
    return ApiError("Erro interno ao acessar o banco de dados", 500, "erro_banco")


def registrar_handlers(app) -> None:
    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError):
        return exc.to_response()

    @app.errorhandler(psycopg.Error)
    def _pg_error(exc: psycopg.Error):
        return traduzir_erro_pg(exc).to_response()

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        mensagens = {
            400: "Requisição inválida",
            401: "Autenticação necessária",
            403: "Acesso negado",
            404: "Recurso não encontrado",
            405: "Método não permitido",
            413: "Arquivo ou requisição excede o tamanho máximo permitido",
            429: "Muitas requisições. Aguarde alguns instantes e tente novamente.",
        }
        corpo = {"erro": {"codigo": f"http_{exc.code}", "mensagem": mensagens.get(exc.code, exc.description)}}
        return jsonify(corpo), exc.code

    @app.errorhandler(Exception)
    def _erro_generico(exc: Exception):
        log.exception("Erro não tratado", exc_info=exc)
        return jsonify({"erro": {"codigo": "erro_interno", "mensagem": "Erro interno inesperado"}}), 500
