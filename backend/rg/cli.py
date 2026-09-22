"""Comandos administrativos.

  python -m rg.cli gerar-chaves            Gera RG_SECRET_KEY, RG_SIGNATURE_SECRET e RG_ENCRYPTION_KEYS
  python -m rg.cli migrar                  Aplica as migrações SQL pendentes
  python -m rg.cli criar-admin             Cria o primeiro administrador (interativo)
  python -m rg.cli rotacionar-chaves       Re-cifra dados com a chave ativa (após incluir nova chave)
"""
from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from dotenv import load_dotenv


def gerar_chaves() -> None:
    from cryptography.fernet import Fernet
    print(f"RG_SECRET_KEY={secrets.token_urlsafe(48)}")
    print(f"RG_SIGNATURE_SECRET={secrets.token_urlsafe(48)}")
    print(f"RG_ENCRYPTION_KEYS={Fernet.generate_key().decode()}")


def migrar() -> None:
    from .config import Config
    from .db import aplicar_migracoes
    url = Config().DATABASE_URL
    if not url:
        sys.exit("Defina RG_DATABASE_URL (usuário dono do schema, ex.: rg_owner)")
    aplicadas = aplicar_migracoes(url)
    print("Migrações aplicadas: " + (", ".join(aplicadas) if aplicadas else "nenhuma pendente"))


def criar_admin(nome: str | None, email: str | None, setor: str) -> None:
    from . import create_app
    from .db import db
    from .seguranca import senhas

    app = create_app()
    nome = nome or input("Nome completo: ").strip()
    email = (email or input("E-mail: ")).strip().lower()
    senha = getpass.getpass("Senha (mín. 12 caracteres): ")
    if senha != getpass.getpass("Confirme a senha: "):
        sys.exit("As senhas não conferem")
    problemas = senhas.validar_politica(senha, minimo=app.config["SENHA_MIN_CARACTERES"], email=email, nome=nome)
    if problemas:
        sys.exit("; ".join(problemas))
    if app.config["HIBP_ENABLED"] and senhas.senha_vazada(senha, app.config["HIBP_TIMEOUT"]):
        sys.exit("Senha encontrada em vazamentos públicos. Escolha outra.")
    with app.app_context(), db.transacao(sistema=True, ip="cli") as cur:
        cur.execute("select 1 from rg.usuarios where lower(email) = %s", (email,))
        if cur.fetchone():
            sys.exit("Já existe usuário com este e-mail")
        hash_ = senhas.gerar_hash(senha)
        cur.execute(
            """insert into rg.usuarios (email, nome, setor_codigo, papel, status, senha_hash, analisado_em,
                                        consentimento_lgpd_em, consentimento_versao)
               values (%s, %s, %s, 'admin', 'aprovado', %s, now(), now(), %s) returning id""",
            (email, nome, setor, hash_, app.config["LGPD_TERMO_VERSAO"]),
        )
        uid = cur.fetchone()["id"]
        cur.execute("insert into rg.senhas_historico (usuario_id, senha_hash) values (%s, %s)", (uid, hash_))
    print(f"Administrador criado: {email}")


def rotacionar_chaves() -> None:
    from . import create_app
    from .db import db
    from .seguranca.cripto import cofre
    from .servicos.arquivos import armazenamento

    app = create_app()
    with app.app_context():
        with db.transacao(sistema=True, ip="cli") as cur:
            cur.execute("select id, telefone_cript from rg.usuarios where telefone_cript is not null")
            for linha in cur.fetchall():
                cur.execute("update rg.usuarios set telefone_cript = %s where id = %s",
                            (cofre.recifrar_texto(linha["telefone_cript"]), linha["id"]))
            cur.execute("select caminho from rg.anexos")
            caminhos = [r["caminho"] for r in cur.fetchall()]
        total = 0
        for caminho in caminhos:
            destino = armazenamento._resolver(caminho)
            if destino.exists():
                destino.write_bytes(cofre.fernet.rotate(destino.read_bytes()))
                total += 1
    print(f"Dados re-cifrados com a chave ativa ({total} arquivos).")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m rg.cli", description="RG Hospital — administração")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("gerar-chaves")
    sub.add_parser("migrar")
    p_admin = sub.add_parser("criar-admin")
    p_admin.add_argument("--nome")
    p_admin.add_argument("--email")
    p_admin.add_argument("--setor", default="administracao")
    sub.add_parser("rotacionar-chaves")
    args = parser.parse_args(argv)
    if args.comando == "gerar-chaves":
        gerar_chaves()
    elif args.comando == "migrar":
        migrar()
    elif args.comando == "criar-admin":
        import os
        os.environ.setdefault("RG_BACKGROUND_JOBS", "false")
        criar_admin(args.nome, args.email, args.setor)
    elif args.comando == "rotacionar-chaves":
        import os
        os.environ.setdefault("RG_BACKGROUND_JOBS", "false")
        rotacionar_chaves()


if __name__ == "__main__":
    main()
