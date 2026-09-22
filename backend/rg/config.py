"""Configuração da aplicação, carregada de variáveis de ambiente."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_DIR = BASE_DIR.parent                               # raiz do repositório


def _bool(nome: str, padrao: bool) -> bool:
    valor = os.environ.get(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


def _int(nome: str, padrao: int) -> int:
    valor = os.environ.get(nome)
    return int(valor) if valor not in (None, "") else padrao


class ConfiguracaoInvalida(RuntimeError):
    pass


class Config:
    def __init__(self, **sobrescritas):
        env = os.environ.get
        self.AMBIENTE = env("RG_AMBIENTE", "desenvolvimento")
        self.TESTING = False

        self.SECRET_KEY = env("RG_SECRET_KEY", "")
        self.SIGNATURE_SECRET = env("RG_SIGNATURE_SECRET", "")
        # Chaves Fernet separadas por vírgula; a primeira é a ativa (rotação via MultiFernet).
        self.ENCRYPTION_KEYS = [k.strip() for k in env("RG_ENCRYPTION_KEYS", "").split(",") if k.strip()]

        self.DATABASE_URL = env("RG_DATABASE_URL", "")
        self.DB_APP_ROLE = env("RG_DB_APP_ROLE", "rg_app")
        self.DB_POOL_MIN = _int("RG_DB_POOL_MIN", 2)
        self.DB_POOL_MAX = _int("RG_DB_POOL_MAX", 20)

        self.SESSION_COOKIE_NAME = env("RG_SESSION_COOKIE", "rg_sessao")
        self.SESSION_COOKIE_SECURE = _bool("RG_SESSION_COOKIE_SECURE", self.AMBIENTE == "producao")
        self.SESSION_IDLE_MINUTES = _int("RG_SESSION_IDLE_MINUTES", 60)
        self.SESSION_ABSOLUTE_HOURS = _int("RG_SESSION_ABSOLUTE_HOURS", 12)

        self.LOGIN_MAX_TENTATIVAS = _int("RG_LOGIN_MAX_TENTATIVAS", 5)
        self.LOGIN_BLOQUEIO_MINUTOS = _int("RG_LOGIN_BLOQUEIO_MINUTOS", 15)
        self.SENHA_MIN_CARACTERES = _int("RG_SENHA_MIN_CARACTERES", 12)
        self.SENHA_HISTORICO = 5
        self.HIBP_ENABLED = _bool("RG_HIBP_ENABLED", True)
        self.HIBP_TIMEOUT = float(env("RG_HIBP_TIMEOUT", "3"))

        self.STORAGE_DIR = Path(env("RG_STORAGE_DIR", str(BASE_DIR / "storage")))
        self.MAX_UPLOAD_MB = _int("RG_MAX_UPLOAD_MB", 10)
        self.MAX_CONTENT_LENGTH = (self.MAX_UPLOAD_MB * 3 + 1) * 1024 * 1024  # até 3 arquivos + campos

        self.OCR_ENABLED = _bool("RG_OCR_ENABLED", True)
        self.OCR_WORKERS = _int("RG_OCR_WORKERS", 2)
        self.OCR_MAX_PAGINAS = _int("RG_OCR_MAX_PAGINAS", 8)
        self.TESSERACT_CMD = env("RG_TESSERACT_CMD", "")

        self.RATELIMIT_STORAGE_URI = env("RG_RATELIMIT_STORAGE_URI", "memory://")
        self.RATELIMIT_DEFAULT = env("RG_RATELIMIT_DEFAULT", "900 per minute")
        self.TRUSTED_PROXIES = _int("RG_TRUSTED_PROXIES", 0)

        self.FRONTEND_DIR = Path(env("RG_FRONTEND_DIR", str(PROJECT_DIR / "frontend")))
        self.SERVE_FRONTEND = _bool("RG_SERVE_FRONTEND", True)

        self.BACKGROUND_JOBS = _bool("RG_BACKGROUND_JOBS", True)
        self.REALTIME_ENABLED = _bool("RG_REALTIME_ENABLED", True)
        self.SLA_JOB_INTERVAL_SECONDS = _int("RG_SLA_JOB_INTERVAL_SECONDS", 300)

        self.TIMEZONE = env("RG_TIMEZONE", "America/Sao_Paulo")
        self.LGPD_TERMO_VERSAO = env("RG_LGPD_TERMO_VERSAO", "2026.1")
        self.INSTITUICAO = env("RG_INSTITUICAO", "Hospital Rio Grande")

        for chave, valor in sobrescritas.items():
            setattr(self, chave, valor)

    def validar(self) -> None:
        faltando = [nome for nome in ("SECRET_KEY", "SIGNATURE_SECRET", "DATABASE_URL")
                    if not getattr(self, nome)]
        if not self.ENCRYPTION_KEYS:
            faltando.append("ENCRYPTION_KEYS")
        if faltando:
            raise ConfiguracaoInvalida(
                "Variáveis obrigatórias ausentes: " + ", ".join("RG_" + f for f in faltando)
                + ". Gere as chaves com: python -m rg.cli gerar-chaves"
            )
        if len(self.SECRET_KEY) < 32 or len(self.SIGNATURE_SECRET) < 32:
            raise ConfiguracaoInvalida("RG_SECRET_KEY e RG_SIGNATURE_SECRET devem ter ao menos 32 caracteres")
        if self.AMBIENTE == "producao" and not self.SESSION_COOKIE_SECURE:
            raise ConfiguracaoInvalida("Em produção o cookie de sessão deve ser Secure (HTTPS)")

    def as_dict(self) -> dict:
        return {k: v for k, v in vars(self).items() if k.isupper()}
