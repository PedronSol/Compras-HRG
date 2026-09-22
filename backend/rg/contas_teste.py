"""Contas de demonstração para desenvolvimento (nunca expostas em produção)."""
from __future__ import annotations

SENHA_TESTE = "Teste@Hospital2026"

CONTAS_TESTE = [
    {"papel": "admin", "nome": "Ana Administração (teste)", "email": "admin.teste@rghospital.com.br",
     "setor_codigo": "administracao", "cargo": "Administrador"},
    {"papel": "gestor", "nome": "Gustavo Gestor (teste)", "email": "gestor.teste@rghospital.com.br",
     "setor_codigo": "pronto_socorro", "cargo": "Gestor de setor"},
    {"papel": "compras", "nome": "Carla Compras (teste)", "email": "compras.teste@rghospital.com.br",
     "setor_codigo": "suprimentos", "cargo": "Comprador"},
]


def semear(cur, hash_senha: str, termo_versao: str) -> list[str]:
    """Cria as contas de teste que ainda não existem. Retorna os e-mails criados."""
    criadas = []
    for c in CONTAS_TESTE:
        cur.execute("select 1 from rg.usuarios where lower(email) = %s", (c["email"],))
        if cur.fetchone():
            continue
        cur.execute(
            """insert into rg.usuarios (email, nome, setor_codigo, cargo, papel, status, senha_hash, analisado_em,
                                        consentimento_lgpd_em, consentimento_versao)
               values (%s, %s, %s, %s, %s, 'aprovado', %s, now(), now(), %s) returning id""",
            (c["email"], c["nome"], c["setor_codigo"], c["cargo"], c["papel"], hash_senha, termo_versao),
        )
        cur.execute("insert into rg.senhas_historico (usuario_id, senha_hash) values (%s, %s)",
                    (cur.fetchone()["id"], hash_senha))
        criadas.append(c["email"])
    return criadas
