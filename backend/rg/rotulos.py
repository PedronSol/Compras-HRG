"""Rótulos em português para os valores enumerados (fonte única para API e relatórios)."""

PAPEL = {"admin": "Administração", "gestor": "Gestor de setor", "compras": "Compras"}
STATUS_USUARIO = {"pendente": "Pendente", "aprovado": "Aprovado", "rejeitado": "Rejeitado", "suspenso": "Suspenso"}
TIPO_SOLICITACAO = {"compra": "Compra", "orcamento": "Orçamento", "contratacao_servico": "Contratação de serviço"}
URGENCIA = {"normal": "Normal", "urgente": "Urgente", "imediato": "Imediato"}
SLA_DIAS = {"imediato": 3, "urgente": 7, "normal": 14}
STATUS_SOLICITACAO = {
    "aguardando_adm": "Aguardando Administração",
    "necessita_nova_cotacao": "Nova cotação solicitada",
    "rejeitado_adm": "Rejeitada pela Administração",
    "aprovado_adm": "Liberada para Compras",
    "em_cotacao": "Em cotação",
    "aprovado": "Homologada",
    "rejeitado_compras": "Rejeitada por Compras",
    "cancelado": "Cancelada",
}
SLA_SITUACAO = {
    "dentro_prazo": "Dentro do prazo",
    "alerta": "Alerta (< 24h)",
    "estourado": "Estourado",
    "cumprido": "Concluída no prazo",
    "cumprido_com_atraso": "Concluída com atraso",
}
TIPO_DOCUMENTO = {"orcamento": "Orçamento", "nota_fiscal": "Nota fiscal", "laudo": "Laudo / certificado",
                  "cotacao": "Proposta de cotação", "outro": "Outro"}
CATEGORIA_SERVICO = {
    "manutencao_preventiva": "Manutenção preventiva",
    "calibracao": "Calibração",
    "higienizacao": "Higienização",
    "ronda": "Ronda",
    "predial": "Predial",
}
PERIODICIDADE = {"unica": "Única", "diaria": "Diária", "semanal": "Semanal", "quinzenal": "Quinzenal",
                 "mensal": "Mensal", "trimestral": "Trimestral", "semestral": "Semestral", "anual": "Anual"}
SITUACAO_SERVICO = {"agendado": "Agendado", "em_andamento": "Em andamento", "concluido": "Concluído",
                    "cancelado": "Cancelado"}
ACAO_ASSINATURA = {
    "submissao": "Submissão (gestor)",
    "reenvio": "Reenvio (gestor)",
    "aprovacao_adm": "Aprovação administrativa",
    "rejeicao_adm": "Rejeição administrativa",
    "nova_cotacao_adm": "Pedido de nova cotação",
    "homologacao": "Homologação (Compras)",
    "rejeicao_compras": "Rejeição (Compras)",
}
