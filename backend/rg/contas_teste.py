"""Contas de demonstração (dados fictícios). Nunca disponíveis com RG_AMBIENTE=producao."""
from __future__ import annotations

SENHA_TESTE = "Teste@Hospital2026"

# Um usuário por perfil, exibidos no seletor de perfis da tela inicial do ambiente de demonstração.
CONTAS_TESTE = [
    {"papel": "admin", "nome": "Renata Moura", "email": "admin@hrg.demo",
     "setor_codigo": "administracao", "cargo": "Administradora de Sistemas"},
    {"papel": "comprador", "nome": "Carlos Menezes", "email": "comprador@hrg.demo",
     "setor_codigo": "suprimentos", "cargo": "Comprador Sênior"},
    {"papel": "solicitante", "nome": "Juliana Prado", "email": "solicitante@hrg.demo",
     "setor_codigo": "uti_adulto", "cargo": "Enfermeira Supervisora"},
    {"papel": "gestor", "nome": "Fernando Alves", "email": "gestor@hrg.demo",
     "setor_codigo": "uti_adulto", "cargo": "Coordenador Médico da UTI"},
    {"papel": "financeiro", "nome": "Patrícia Lemos", "email": "financeiro@hrg.demo",
     "setor_codigo": "financeiro", "cargo": "Analista Financeira"},
    {"papel": "recebimento", "nome": "Marcos Vieira", "email": "recebimento@hrg.demo",
     "setor_codigo": "suprimentos", "cargo": "Conferente de Almoxarifado"},
    {"papel": "diretoria", "nome": "Helena Castro", "email": "diretoria@hrg.demo",
     "setor_codigo": "diretoria", "cargo": "Diretora Administrativa"},
    {"papel": "auditoria", "nome": "Roberto Nunes", "email": "auditoria@hrg.demo",
     "setor_codigo": "controladoria", "cargo": "Auditor Interno"},
]


def semear(cur, hash_senha: str, termo_versao: str) -> list[str]:
    """Cria as contas de demonstração que ainda não existem. Retorna os e-mails criados."""
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
