"""Matriz de permissões por perfil (fonte única para API, menu do frontend e tela de perfis).

A API verifica estas capacidades antes de cada operação; o banco repete as regras
com RLS e triggers, de modo que nenhuma camada dependa apenas da outra.
"""
from __future__ import annotations

from .errors import Proibido

TODOS = ("admin", "comprador", "solicitante", "gestor", "financeiro", "recebimento", "diretoria", "auditoria")

# capacidade: (grupo, descrição, perfis)
CAPACIDADES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "painel.ver": ("Visão geral", "Ver o painel de indicadores", TODOS),
    "solicitacao.ver": ("Solicitações", "Consultar solicitações (conforme o escopo do perfil)", TODOS),
    "solicitacao.criar": ("Solicitações", "Abrir solicitações de compra do setor", ("solicitante", "gestor")),
    "solicitacao.aprovar_gestor": ("Aprovações", "Aprovar, devolver ou reprovar solicitações do setor", ("gestor",)),
    "solicitacao.aprovar_diretoria": ("Aprovações", "Aprovar solicitações acima da alçada", ("diretoria",)),
    "solicitacao.cancelar": ("Solicitações", "Cancelar solicitações (com justificativa)",
                             ("solicitante", "gestor", "comprador", "admin")),
    "cotacao.gerenciar": ("Cotações", "Conduzir cotações, registrar propostas e definir o fornecedor", ("comprador",)),
    "pedido.ver": ("Pedidos", "Consultar pedidos de compra",
                   ("admin", "comprador", "financeiro", "recebimento", "diretoria", "auditoria", "gestor", "solicitante")),
    "pedido.emitir": ("Pedidos", "Emitir, enviar e cancelar pedidos de compra", ("comprador",)),
    "pedido.aprovar_financeiro": ("Aprovações", "Aprovar pedidos de compra (orçamento)", ("financeiro",)),
    "pedido.aprovar_diretoria": ("Aprovações", "Aprovar pedidos acima da alçada", ("diretoria",)),
    "recebimento.registrar": ("Recebimento", "Registrar entregas e conferir itens", ("recebimento",)),
    "recebimento.ver": ("Recebimento", "Consultar recebimentos",
                        ("admin", "comprador", "financeiro", "recebimento", "diretoria", "auditoria")),
    "fornecedor.ver": ("Fornecedores", "Consultar fornecedores e desempenho",
                       ("admin", "comprador", "financeiro", "diretoria", "auditoria", "recebimento")),
    "fornecedor.gerenciar": ("Fornecedores", "Cadastrar e editar fornecedores", ("comprador", "admin")),
    "material.ver": ("Catálogo", "Consultar materiais e categorias", TODOS),
    "material.gerenciar": ("Catálogo", "Cadastrar e editar materiais e categorias", ("comprador", "admin")),
    "alerta.ver": ("Visão geral", "Ver alertas operacionais", TODOS),
    "relatorio.ver": ("Relatórios", "Emitir relatórios e indicadores",
                      ("admin", "comprador", "financeiro", "diretoria", "auditoria", "gestor")),
    "auditoria.ver": ("Governança", "Consultar a trilha de auditoria", ("admin", "auditoria")),
    "usuario.gerenciar": ("Governança", "Gerenciar usuários, perfis e setores", ("admin",)),
    "configuracao.gerenciar": ("Governança", "Alterar alçadas e parâmetros", ("admin",)),
}


def pode(usuario: dict | None, capacidade: str) -> bool:
    return bool(usuario) and usuario["papel"] in CAPACIDADES[capacidade][2]


def exigir(usuario: dict, capacidade: str) -> None:
    if not pode(usuario, capacidade):
        raise Proibido()


def capacidades_do_papel(papel: str) -> list[str]:
    return [c for c, (_, _, papeis) in CAPACIDADES.items() if papel in papeis]


def matriz() -> list[dict]:
    return [{"capacidade": c, "grupo": g, "descricao": d, "perfis": list(p)} for c, (g, d, p) in CAPACIDADES.items()]
