"""Ambiente de desenvolvimento local em um comando (sem instalar PostgreSQL).

    python dev.py                 # inicia PostgreSQL embutido, migra, carrega a demonstração e sobe em http://127.0.0.1:8000
    python dev.py --so-banco      # apenas prepara o banco e imprime a URL
    python dev.py --criar-admin   # cria o administrador inicial (interativo)
    python dev.py --recriar       # apaga o banco de desenvolvimento e recria com dados de demonstração
    python dev.py --sem-demo      # não carrega os dados fictícios de demonstração

Para usar um PostgreSQL já instalado (em vez do embutido), defina RG_DEV_DATABASE_URL com um
usuário superusuário, por exemplo: postgresql://postgres@localhost:5432/postgres

Requer as dependências de desenvolvimento (requirements-dev.txt). Em produção, use um
PostgreSQL gerenciado e `python -m rg.cli migrar` (ver README).
"""
from __future__ import annotations

import argparse
import os
import secrets
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
DADOS_PG = RAIZ / ".pgdata"
ARQUIVO_ENV = RAIZ / ".env"


def garantir_env() -> None:
    if ARQUIVO_ENV.exists():
        return
    from cryptography.fernet import Fernet
    conteudo = (RAIZ / ".env.example").read_text(encoding="utf-8")
    conteudo = conteudo.replace("RG_SECRET_KEY=\n", f"RG_SECRET_KEY={secrets.token_urlsafe(48)}\n")
    conteudo = conteudo.replace("RG_SIGNATURE_SECRET=\n", f"RG_SIGNATURE_SECRET={secrets.token_urlsafe(48)}\n")
    conteudo = conteudo.replace("RG_ENCRYPTION_KEYS=\n", f"RG_ENCRYPTION_KEYS={Fernet.generate_key().decode()}\n")
    ARQUIVO_ENV.write_text(conteudo, encoding="utf-8")
    print(f"Arquivo {ARQUIVO_ENV.name} criado com chaves aleatórias (não versionar).")


def instalar_fusos(pgembed_mod) -> None:
    destino = Path(pgembed_mod.__file__).parent / "pginstall" / "share" / "postgresql" / "timezone"
    if destino.exists():
        return
    import tzdata
    shutil.copytree(Path(tzdata.__file__).parent / "zoneinfo", destino,
                    ignore=shutil.ignore_patterns("__init__.py", "__pycache__"))


AJUSTES_DEV = "\n# --- RG Hospital (somente desenvolvimento) ---\nfsync = off\nsynchronous_commit = off\nfull_page_writes = off\n"


def preparar_config_dev() -> None:
    """Banco descartável de desenvolvimento: sem fsync.

    Quando o servidor de desenvolvimento é interrompido, o PostgreSQL filho também é encerrado
    abruptamente. Na recuperação seguinte ele sincroniza todos os arquivos da pasta de dados,
    inclusive o arquivo de log que o próprio pg_ctl mantém aberto; no Windows isso gera
    "sharing violation" e trava a inicialização. Com fsync=off essa etapa é dispensada.
    """
    conf = DADOS_PG / "postgresql.conf"
    if conf.exists() and "RG Hospital (somente desenvolvimento)" not in conf.read_text(encoding="utf-8"):
        with open(conf, "a", encoding="utf-8") as fh:
            fh.write(AJUSTES_DEV)


def obter_servidor(pgembed_mod, tentativas: int = 12):
    """Inicia (ou reaproveita) o PostgreSQL embutido, aguardando recuperações em andamento."""
    import time
    ultimo_erro: Exception | None = None
    for _ in range(tentativas):
        try:
            return pgembed_mod.get_server(str(DADOS_PG), cleanup_mode=None)
        except AssertionError as exc:  # postmaster ainda em "starting" (recuperação)
            ultimo_erro = exc
            print("PostgreSQL ainda iniciando (recuperação em andamento); aguardando…")
            time.sleep(5)
    raise RuntimeError("O PostgreSQL de desenvolvimento não ficou pronto. Veja backend/.pgdata/log") from ultimo_erro


def _base_postgres() -> str:
    externo = os.environ.get("RG_DEV_DATABASE_URL")
    if externo:
        return externo
    try:
        import pgembed
    except ImportError:
        sys.exit("Instale as dependências de desenvolvimento (pip install -r requirements-dev.txt) "
                 "ou defina RG_DEV_DATABASE_URL apontando para um PostgreSQL local.")
    import psycopg
    instalar_fusos(pgembed)
    DADOS_PG.mkdir(exist_ok=True)
    preparar_config_dev()
    base = obter_servidor(pgembed).get_uri()
    with psycopg.connect(base, autocommit=True) as c:
        if c.execute("show fsync").fetchone()[0] != "off":
            c.execute("alter system set fsync = off")
            c.execute("alter system set synchronous_commit = off")
            c.execute("select pg_reload_conf()")
    return base


def _estrutura_antiga(c) -> bool:
    """Bancos criados pela versão 1.x (sem pedidos de compra) precisam ser recriados."""
    migrado = c.execute("select to_regclass('public.schema_migracoes') is not null").fetchone()[0]
    return migrado and not c.execute("select to_regclass('rg.pedidos') is not null").fetchone()[0]


def iniciar_banco(recriar: bool = False) -> str:
    import psycopg
    base = _base_postgres()
    url = base.rsplit("/", 1)[0] + "/rg_hospital"
    with psycopg.connect(base, autocommit=True) as c:
        existe = c.execute("select 1 from pg_database where datname = 'rg_hospital'").fetchone()
        if existe and not recriar:
            with psycopg.connect(url, autocommit=True) as alvo:
                if _estrutura_antiga(alvo):
                    print("Banco de desenvolvimento da versão anterior detectado: recriando com a nova estrutura.")
                    recriar = True
        if existe and recriar:
            c.execute("select pg_terminate_backend(pid) from pg_stat_activity where datname = 'rg_hospital'")
            c.execute("drop database rg_hospital")
            existe = None
        if not existe:
            c.execute("create database rg_hospital")
    from rg.db import aplicar_migracoes
    aplicadas = aplicar_migracoes(url)
    if aplicadas:
        print("Migrações aplicadas:", ", ".join(aplicadas))
    return url


def semear_demonstracao(url: str) -> None:
    """Carrega os dados fictícios (uma única vez, em banco vazio)."""
    import psycopg
    from psycopg.rows import dict_row
    from rg.config import Config
    from rg.contas_teste import SENHA_TESTE
    from rg.demo import semear_demo
    from rg.seguranca import senhas
    cfg = Config()
    with psycopg.connect(url, row_factory=dict_row) as conn:
        n = semear_demo(conn, segredo=cfg.SIGNATURE_SECRET, hash_senha=senhas.gerar_hash(SENHA_TESTE),
                        termo_versao=cfg.LGPD_TERMO_VERSAO)
    if n:
        print(f"Dados de demonstração carregados: {n} solicitações fictícias. Senha dos perfis: {SENHA_TESTE}")


def semear_contas_teste(app) -> None:
    from rg.contas_teste import SENHA_TESTE, semear
    from rg.db import db
    from rg.seguranca import senhas
    with app.app_context(), db.transacao(sistema=True, ip="dev") as cur:
        criadas = semear(cur, senhas.gerar_hash(SENHA_TESTE), app.config["LGPD_TERMO_VERSAO"])
    if criadas:
        print("Contas de teste criadas:", ", ".join(criadas))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--so-banco", action="store_true")
    parser.add_argument("--criar-admin", action="store_true")
    parser.add_argument("--recriar", action="store_true")
    parser.add_argument("--sem-demo", action="store_true")
    parser.add_argument("--porta", type=int, default=int(os.environ.get("RG_PORTA", "8000")))
    args = parser.parse_args()

    sys.path.insert(0, str(RAIZ))
    garantir_env()
    from dotenv import load_dotenv
    load_dotenv(ARQUIVO_ENV)
    url = iniciar_banco(recriar=args.recriar)
    os.environ["RG_DATABASE_URL"] = url
    if not args.sem_demo:
        semear_demonstracao(url)
    print(f"PostgreSQL de desenvolvimento: {url}")
    if args.so_banco:
        return
    if args.criar_admin:
        from rg.cli import main as cli
        cli(["criar-admin"])
        return
    from rg import create_app
    app = create_app()
    semear_contas_teste(app)
    print(f"Hospital Rio Grande · Compras em http://127.0.0.1:{args.porta}")
    app.run(host="127.0.0.1", port=args.porta, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
