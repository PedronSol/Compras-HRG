"""Política de senhas, hashing Argon2id, histórico e verificação de vazamentos."""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
import urllib.request

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

log = logging.getLogger("rg.senhas")

_hasher = PasswordHasher()  # Argon2id, parâmetros recomendados RFC 9106 (perfil de baixa memória)
_HASH_FICTICIO = _hasher.hash("rg-hospital-hash-de-temporizacao")

# Senhas triviais frequentes em ambientes corporativos brasileiros
_SENHAS_COMUNS = {
    "123456789012", "senha123456", "senhasenha12", "qwertyuiop12", "hospital1234", "hospitalrg123",
    "riogrande123", "admin1234567", "password1234", "mudar@123456", "trocar@12345", "brasil123456",
    "abcdefghijkl", "123456abcdef", "rghospital123", "rghospital2026", "hospital@2026", "senha@2026",
}


def gerar_hash(senha: str) -> str:
    return _hasher.hash(senha)


def verificar(senha_hash: str | None, senha: str) -> bool:
    if not senha_hash:
        _verificar_ficticio(senha)
        return False
    try:
        return _hasher.verify(senha_hash, senha)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _verificar_ficticio(senha: str) -> None:
    """Executa uma verificação completa para igualar o tempo de resposta (anti-enumeração)."""
    try:
        _hasher.verify(_HASH_FICTICIO, senha)
    except VerifyMismatchError:
        pass


def precisa_rehash(senha_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(senha_hash)
    except InvalidHashError:
        return True


def _normalizar(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def validar_politica(senha: str, *, minimo: int, email: str = "", nome: str = "") -> list[str]:
    """Retorna a lista de violações da política de senha (vazia = senha aceita)."""
    problemas: list[str] = []
    if len(senha) < minimo:
        problemas.append(f"A senha deve ter no mínimo {minimo} caracteres")
    if len(senha) > 128:
        problemas.append("A senha deve ter no máximo 128 caracteres")
    classes = sum(bool(re.search(p, senha)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        problemas.append("Use ao menos 3 destes grupos: minúsculas, maiúsculas, números e símbolos")
    if re.search(r"(.)\1{3,}", senha):
        problemas.append("A senha não pode repetir o mesmo caractere 4 vezes seguidas")
    normalizada = _normalizar(senha)
    if normalizada in _SENHAS_COMUNS:
        problemas.append("Esta senha é muito comum")
    local = _normalizar(email.split("@")[0]) if email else ""
    if len(local) >= 4 and local in normalizada:
        problemas.append("A senha não pode conter o seu e-mail")
    for parte in _normalizar(nome).split():
        if len(parte) >= 4 and parte in normalizada:
            problemas.append("A senha não pode conter o seu nome")
            break
    return problemas


def senha_vazada(senha: str, timeout: float = 3.0) -> bool | None:
    """Consulta a base Have I Been Pwned por k-anonimato (somente 5 caracteres do SHA-1 são enviados).

    Retorna True se vazada, False se não encontrada e None se a verificação falhou.
    """
    sha1 = hashlib.sha1(senha.encode("utf-8")).hexdigest().upper()  # noqa: S324 - exigido pelo protocolo HIBP
    prefixo, sufixo = sha1[:5], sha1[5:]
    req = urllib.request.Request(
        f"https://api.pwnedpasswords.com/range/{prefixo}",
        headers={"User-Agent": "RG-Hospital-Plataforma", "Add-Padding": "true"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URL fixa HTTPS
            corpo = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # rede indisponível não pode impedir a operação
        log.warning("Verificação HIBP indisponível: %s", exc)
        return None
    for linha in corpo.splitlines():
        hash_sufixo, _, contagem = linha.partition(":")
        if hash_sufixo.strip() == sufixo and contagem.strip() not in ("", "0"):
            return True
    return False


def senha_reutilizada(senha: str, hashes_anteriores: list[str]) -> bool:
    return any(verificar(h, senha) for h in hashes_anteriores)
