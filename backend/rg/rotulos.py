"""Rótulos em português para os valores enumerados (fonte única para API, frontend e relatórios)."""

PAPEL = {
    "admin": "Administrador",
    "comprador": "Comprador",
    "solicitante": "Solicitante",
    "gestor": "Gestor de setor",
    "financeiro": "Financeiro",
    "recebimento": "Recebimento",
    "diretoria": "Diretoria",
    "auditoria": "Auditoria",
}
PAPEL_DESCRICAO = {
    "admin": "Administra usuários, setores, catálogo, fornecedores e parâmetros. Visão completa, sem aprovar compras.",
    "comprador": "Conduz cotações, registra propostas, define o fornecedor e emite e envia pedidos de compra.",
    "solicitante": "Abre solicitações de compra do seu setor e acompanha cada etapa até a entrega.",
    "gestor": "Aprova, devolve ou reprova as solicitações do seu setor.",
    "financeiro": "Aprova os pedidos de compra sob a ótica orçamentária e acompanha os gastos.",
    "recebimento": "Registra entregas, confere quantidades e anexa notas fiscais.",
    "diretoria": "Aprova solicitações e pedidos acima da alçada e acompanha os indicadores.",
    "auditoria": "Acesso somente leitura a todos os registros, histórico e trilha de auditoria.",
}
STATUS_USUARIO = {"pendente": "Pendente", "aprovado": "Ativo", "rejeitado": "Rejeitado", "suspenso": "Suspenso"}
TIPO_SOLICITACAO = {"material": "Materiais e insumos", "equipamento": "Equipamentos", "servico": "Serviços"}
URGENCIA = {"normal": "Normal", "urgente": "Urgente", "imediato": "Imediata"}
SLA_DIAS = {"imediato": 3, "urgente": 7, "normal": 14}
STATUS_SOLICITACAO = {
    "aguardando_gestor": "Aguardando gestor",
    "aguardando_diretoria": "Aguardando Diretoria",
    "devolvida": "Devolvida para ajustes",
    "reprovada": "Reprovada",
    "aprovada": "Aprovada",
    "em_cotacao": "Em cotação",
    "aguardando_pedido": "Fornecedor definido",
    "em_pedido": "Pedido emitido",
    "recebida_parcial": "Recebida parcialmente",
    "concluida": "Concluída",
    "cancelada": "Cancelada",
}
STATUS_PEDIDO = {
    "aguardando_financeiro": "Aguardando Financeiro",
    "aguardando_diretoria": "Aguardando Diretoria",
    "aprovado": "Aprovado",
    "enviado": "Enviado ao fornecedor",
    "entregue_parcial": "Entregue parcialmente",
    "entregue": "Entregue",
    "reprovado": "Reprovado",
    "cancelado": "Cancelado",
}
SITUACAO_RECEBIMENTO = {"conforme": "Conforme", "divergente": "Com divergência", "recusado": "Recusado"}
SLA_SITUACAO = {
    "dentro_prazo": "No prazo",
    "alerta": "Vence em < 24 h",
    "estourado": "Prazo estourado",
    "cumprido": "Atendida no prazo",
    "cumprido_com_atraso": "Atendida com atraso",
}
TIPO_DOCUMENTO = {"orcamento": "Orçamento", "proposta": "Proposta comercial", "nota_fiscal": "Nota fiscal",
                  "laudo": "Laudo / certificado", "foto": "Fotografia", "outro": "Outro"}
NIVEL_APROVACAO = {"gestor": "Gestor do setor", "diretoria": "Diretoria", "financeiro": "Financeiro"}
DECISAO_APROVACAO = {"aprovado": "Aprovado", "reprovado": "Reprovado", "devolvido": "Devolvido"}
UNIDADES = {
    "UN": "Unidade", "CX": "Caixa", "PCT": "Pacote", "FR": "Frasco", "AMP": "Ampola", "BL": "Bolsa",
    "KG": "Quilograma", "G": "Grama", "L": "Litro", "ML": "Mililitro", "M": "Metro", "RL": "Rolo",
    "PAR": "Par", "KIT": "Kit", "GL": "Galão", "SV": "Serviço", "MES": "Mês", "H": "Hora", "RM": "Resma",
}
ACAO_ASSINATURA = {
    "submissao": "Abertura da solicitação",
    "reenvio": "Reenvio após ajustes",
    "aprovacao_gestor": "Aprovação do gestor",
    "aprovacao_diretoria": "Aprovação da Diretoria",
    "reprovacao": "Reprovação",
    "devolucao": "Devolução para ajustes",
    "definicao_fornecedor": "Definição do fornecedor",
    "emissao_pedido": "Emissão do pedido de compra",
    "aprovacao_financeiro": "Aprovação financeira do pedido",
    "reprovacao_financeiro": "Reprovação financeira do pedido",
    "aprovacao_diretoria_pedido": "Aprovação do pedido pela Diretoria",
    "reprovacao_diretoria_pedido": "Reprovação do pedido pela Diretoria",
    "envio_pedido": "Envio do pedido ao fornecedor",
    "recebimento": "Recebimento e conferência",
    "encerramento_pedido": "Encerramento do pedido com pendência",
}
ETAPAS = ["Solicitação", "Aprovação", "Cotação", "Fornecedor", "Pedido", "Recebimento", "Conclusão"]


def todos() -> dict:
    return {
        "papel": PAPEL, "papel_descricao": PAPEL_DESCRICAO, "status_usuario": STATUS_USUARIO,
        "tipo_solicitacao": TIPO_SOLICITACAO, "urgencia": URGENCIA, "status_solicitacao": STATUS_SOLICITACAO,
        "status_pedido": STATUS_PEDIDO, "situacao_recebimento": SITUACAO_RECEBIMENTO, "sla_situacao": SLA_SITUACAO,
        "tipo_documento": TIPO_DOCUMENTO, "nivel_aprovacao": NIVEL_APROVACAO, "decisao_aprovacao": DECISAO_APROVACAO,
        "unidade": UNIDADES, "acao_assinatura": ACAO_ASSINATURA,
    }
