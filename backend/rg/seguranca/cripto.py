"""Criptografia simétrica de dados em repouso (campos pessoais e arquivos)."""
from __future__ import annotations

import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class Cofre:
    def __init__(self) -> None:
        self._fernet: MultiFernet | None = None

    def configurar(self, chaves: list[str]) -> None:
        if not chaves:
            raise ValueError("Nenhuma chave de criptografia configurada")
        self._fernet = MultiFernet([Fernet(k.encode()) for k in chaves])

    @property
    def fernet(self) -> MultiFernet:
        if self._fernet is None:
            raise RuntimeError("Cofre de criptografia não configurado")
        return self._fernet

    def cifrar_bytes(self, dados: bytes) -> bytes:
        return self.fernet.encrypt(dados)

    def decifrar_bytes(self, dados: bytes) -> bytes:
        try:
            return self.fernet.decrypt(dados)
        except InvalidToken as exc:
            raise ValueError("Falha de integridade ao decifrar dados") from exc

    def cifrar_texto(self, texto: str | None) -> str | None:
        if not texto:
            return None
        return self.fernet.encrypt(texto.encode("utf-8")).decode("ascii")

    def decifrar_texto(self, token: str | None) -> str | None:
        if not token:
            return None
        try:
            return self.fernet.decrypt(token.encode("ascii")).decode("utf-8")
        except InvalidToken:
            return None

    def recifrar_texto(self, token: str | None) -> str | None:
        """Rotação de chave: re-cifra com a chave ativa."""
        if not token:
            return None
        return self.fernet.rotate(token.encode("ascii")).decode("ascii")


def sha256_hex(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


cofre = Cofre()
