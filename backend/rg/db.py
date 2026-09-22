"""Acesso ao PostgreSQL com pool de conexões e contexto de segurança para RLS.

Cada transação executa `SET LOCAL ROLE rg_app` e define `app.user_id`,
`app.ip` e `app.contexto`, de modo que as políticas de Row Level Security
sejam aplicadas mesmo que a conexão de login tenha privilégios maiores.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


class Database:
    def __init__(self) -> None:
        self.pool: ConnectionPool | None = None
        self.url: str = ""
        self.app_role: str | None = None
        self._lock = threading.Lock()

    def init_app(self, app) -> None:
        self.url = app.config["DATABASE_URL"]
        self.app_role = app.config.get("DB_APP_ROLE") or None
        self.pool = ConnectionPool(
            self.url,
            min_size=app.config["DB_POOL_MIN"],
            max_size=app.config["DB_POOL_MAX"],
            kwargs={"row_factory": dict_row, "autocommit": True},
            name="rg-pool",
            open=True,
        )
        app.extensions["rg_db"] = self

    def close(self) -> None:
        if self.pool is not None:
            self.pool.close()
            self.pool = None

    @contextmanager
    def transacao(self, *, usuario_id: str | None = None, sistema: bool = False,
                  ip: str | None = None, observacao: str | None = None) -> Iterator[psycopg.Cursor]:
        """Abre uma transação com o contexto de segurança informado."""
        assert self.pool is not None, "Banco de dados não inicializado"
        with self.pool.connection() as conn:
            with conn.transaction():
                with conn.cursor() as cur:
                    if self.app_role:
                        cur.execute(sql.SQL("set local role {}").format(sql.Identifier(self.app_role)))
                    cur.execute(
                        "select set_config('app.user_id', %s, true), set_config('app.contexto', %s, true),"
                        " set_config('app.ip', %s, true), set_config('app.observacao', %s, true)",
                        (str(usuario_id) if usuario_id else "", "sistema" if sistema else "",
                         ip or "", observacao or ""),
                    )
                    yield cur

    def conexao_dedicada(self) -> psycopg.Connection:
        """Conexão fora do pool (LISTEN/NOTIFY)."""
        return psycopg.connect(self.url, autocommit=True, row_factory=dict_row)


def definir_observacao(cur: psycopg.Cursor, texto: str | None) -> None:
    cur.execute("select set_config('app.observacao', %s, true)", (texto or "",))


def aplicar_migracoes(url: str, diretorio: Path = MIGRATIONS_DIR) -> list[str]:
    """Aplica migrações SQL pendentes em ordem, cada uma em sua transação."""
    aplicadas: list[str] = []
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            "create table if not exists public.schema_migracoes ("
            " versao text primary key, aplicada_em timestamptz not null default now())"
        )
        conn.execute("select pg_advisory_lock(727001)")
        try:
            existentes = {r[0] for r in conn.execute("select versao from public.schema_migracoes")}
            for arquivo in sorted(diretorio.glob("*.sql")):
                if arquivo.name in existentes:
                    continue
                with conn.transaction():
                    conn.execute(arquivo.read_text(encoding="utf-8"))
                    conn.execute("insert into public.schema_migracoes (versao) values (%s)", (arquivo.name,))
                aplicadas.append(arquivo.name)
        finally:
            conn.execute("select pg_advisory_unlock(727001)")
    return aplicadas


db = Database()
