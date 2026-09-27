"""Dados de demonstração 100% fictícios para apresentação do sistema.

Gera fornecedores, catálogo, usuários dos 8 perfis e solicitações em todas as etapas do fluxo
(com itens, aprovações, propostas, pedidos, recebimentos, assinaturas, histórico, notificações e
auditoria), distribuídas nos últimos meses para que painéis e relatórios tenham conteúdo realista.

Executado com uma conexão de dono do schema: as triggers de usuário são desativadas dentro de uma
única transação (o estado final é coerente com as regras) e reativadas ao final. Nunca roda em produção.
"""
from __future__ import annotations

import random
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from .contas_teste import CONTAS_TESTE
from .servicos.assinaturas import calcular_conteudo_hash, calcular_hash

TZ = ZoneInfo("America/Sao_Paulo")
UTC = timezone.utc
H = timedelta(hours=1)
D = timedelta(days=1)

TABELAS = ["rg.usuarios", "rg.senhas_historico", "rg.categorias", "rg.materiais", "rg.fornecedores",
           "rg.solicitacoes", "rg.solicitacao_itens", "rg.cotacoes", "rg.cotacao_itens", "rg.pedidos",
           "rg.pedido_itens", "rg.recebimentos", "rg.recebimento_itens", "rg.anexos", "rg.aprovacoes",
           "rg.assinaturas", "rg.solicitacao_historico", "rg.notificacoes", "audit.eventos"]

USUARIOS_EXTRAS = [
    ("solicitante", "Aline Duarte", "centro_cirurgico", "Enfermeira do Centro Cirúrgico"),
    ("gestor", "Ricardo Farias", "centro_cirurgico", "Coordenador do Centro Cirúrgico"),
    ("solicitante", "Bruno Siqueira", "pronto_socorro", "Enfermeiro Assistencial"),
    ("gestor", "Luciana Teixeira", "pronto_socorro", "Coordenadora do Pronto Socorro"),
    ("solicitante", "Camila Rocha", "laboratorio", "Biomédica"),
    ("gestor", "Eduardo Pinheiro", "laboratorio", "Responsável Técnico do Laboratório"),
    ("solicitante", "Tatiane Gomes", "farmacia", "Farmacêutica"),
    ("gestor", "Sérgio Lopes", "farmacia", "Farmacêutico Responsável"),
    ("solicitante", "Diego Martins", "engenharia_clinica", "Técnico em Equipamentos"),
    ("gestor", "Mônica Ribeiro", "engenharia_clinica", "Engenheira Clínica"),
    ("solicitante", "Paulo Henrique Costa", "tecnologia", "Analista de Suporte"),
    ("gestor", "André Barros", "tecnologia", "Coordenador de TI"),
    ("solicitante", "Vanessa Freitas", "hotelaria", "Supervisora de Higienização"),
    ("gestor", "Gabriela Nogueira", "hotelaria", "Gerente de Hotelaria"),
    ("solicitante", "Rafael Antunes", "uti_neonatal", "Enfermeiro da UTI Neonatal"),
    ("gestor", "Cláudia Vasconcelos", "uti_neonatal", "Coordenadora da UTI Neonatal"),
    ("solicitante", "Letícia Moraes", "nutricao", "Nutricionista"),
    ("gestor", "Márcia Campos", "nutricao", "Coordenadora de Nutrição"),
    ("solicitante", "Otávio Rezende", "manutencao", "Técnico de Manutenção"),
    ("gestor", "Jorge Almeida", "manutencao", "Supervisor de Manutenção"),
    ("solicitante", "Simone Carvalho", "administracao", "Assistente Administrativa"),
    ("gestor", "Luiz Fernando Sá", "administracao", "Gerente Administrativo"),
    ("comprador", "Beatriz Rocha", "suprimentos", "Compradora"),
    ("recebimento", "Wagner Souza", "suprimentos", "Almoxarife"),
]

CATEGORIAS = [
    ("Medicamentos", "#16A34A", "Medicamentos de uso hospitalar e soluções parenterais"),
    ("Materiais médico-hospitalares", "#0891B2", "Descartáveis e materiais de assistência"),
    ("Equipamentos médicos", "#1D4ED8", "Equipamentos assistenciais e de monitorização"),
    ("Laboratório e diagnóstico", "#7C3AED", "Reagentes, tubos e insumos laboratoriais"),
    ("Higiene e limpeza", "#0D9488", "Saneantes e materiais de higienização"),
    ("Nutrição e dietas", "#CA8A04", "Dietas enterais, suplementos e gêneros"),
    ("Material de escritório", "#64748B", "Papelaria e suprimentos de impressão"),
    ("Tecnologia da informação", "#334155", "Equipamentos de informática e periféricos"),
    ("Manutenção predial", "#A16207", "Materiais elétricos, hidráulicos e de pintura"),
    ("EPIs e rouparia", "#DB2777", "Equipamentos de proteção individual e enxoval"),
    ("Serviços técnicos", "#9333EA", "Manutenção, calibração e serviços especializados"),
]

MATERIAIS = {
    "Medicamentos": [("Dipirona sódica 500 mg/ml — ampola 2 ml", "AMP", "1.85"),
                     ("Cloreto de sódio 0,9% — bolsa 500 ml", "BL", "4.90"),
                     ("Omeprazol 40 mg injetável", "FR", "12.40"), ("Ceftriaxona 1 g injetável", "FR", "9.80"),
                     ("Heparina sódica 5.000 UI/0,25 ml", "AMP", "14.60"), ("Midazolam 5 mg/ml — ampola 10 ml", "AMP", "8.75"),
                     ("Noradrenalina 4 mg/4 ml", "AMP", "11.30")],
    "Materiais médico-hospitalares": [("Seringa descartável 10 ml com agulha", "UN", "0.58"),
                                      ("Luva de procedimento nitrílica M — caixa 100", "CX", "38.90"),
                                      ("Cateter intravenoso periférico 20G", "UN", "2.35"),
                                      ("Equipo macrogotas com injetor lateral", "UN", "3.10"),
                                      ("Compressa de gaze estéril 7,5 × 7,5 cm", "PCT", "1.20"),
                                      ("Sonda de aspiração traqueal nº 12", "UN", "1.45"),
                                      ("Máscara cirúrgica tripla — caixa 50", "CX", "22.00"),
                                      ("Curativo transparente 10 × 12 cm", "UN", "4.80")],
    "Equipamentos médicos": [("Monitor multiparamétrico 12\"", "UN", "18500.00"),
                             ("Bomba de infusão volumétrica", "UN", "9800.00"),
                             ("Oxímetro de pulso portátil", "UN", "890.00"),
                             ("Cama hospitalar elétrica 3 movimentos", "UN", "14200.00"),
                             ("Desfibrilador externo automático (DEA)", "UN", "11900.00"),
                             ("Aspirador cirúrgico portátil", "UN", "3650.00")],
    "Laboratório e diagnóstico": [("Tubo de coleta a vácuo EDTA 4 ml — caixa 100", "CX", "62.00"),
                                  ("Kit reagente glicose — 500 testes", "KIT", "385.00"),
                                  ("Ponteira 200 µl — pacote 1.000", "PCT", "28.50"),
                                  ("Lâmina para microscopia — caixa 50", "CX", "16.90")],
    "Higiene e limpeza": [("Desinfetante hospitalar quaternário — galão 5 L", "GL", "48.00"),
                          ("Álcool em gel 70% — frasco 1 L", "FR", "11.90"),
                          ("Papel toalha interfolhado — pacote 1.000", "PCT", "14.20"),
                          ("Saco para resíduo infectante 100 L — pacote 100", "PCT", "39.00")],
    "Nutrição e dietas": [("Dieta enteral normocalórica 1 L", "UN", "42.00"),
                          ("Fórmula infantil de partida 400 g", "UN", "38.50"),
                          ("Suplemento hiperproteico 200 ml", "UN", "9.90")],
    "Material de escritório": [("Papel A4 75 g — resma 500 folhas", "RM", "27.50"),
                               ("Toner para impressora laser monocromática", "UN", "320.00"),
                               ("Pasta suspensa — caixa 50", "CX", "45.00")],
    "Tecnologia da informação": [("Notebook corporativo i5, 16 GB, SSD 512 GB", "UN", "5400.00"),
                                 ("Monitor LED 24\" Full HD", "UN", "980.00"),
                                 ("Leitor de código de barras 2D", "UN", "420.00"),
                                 ("Nobreak 1.500 VA", "UN", "1350.00")],
    "Manutenção predial": [("Lâmpada LED tubular 18 W", "UN", "19.90"), ("Tinta acrílica branca — lata 18 L", "GL", "385.00"),
                           ("Válvula reguladora de oxigênio", "UN", "460.00")],
    "EPIs e rouparia": [("Avental descartável manga longa", "UN", "3.40"), ("Óculos de proteção incolor", "UN", "12.80"),
                        ("Lençol hospitalar 100% algodão", "UN", "38.00")],
    "Serviços técnicos": [("Manutenção preventiva de equipamentos biomédicos", "SV", "4500.00"),
                          ("Calibração de equipamentos biomédicos", "SV", "2800.00"),
                          ("Controle integrado de pragas", "SV", "1900.00")],
}

FORNECEDORES = [
    ("MedSul Distribuidora Hospitalar Ltda", "MedSul", "Porto Alegre", "RS", "Adriana Kunz",
     ["Medicamentos", "Materiais médico-hospitalares", "EPIs e rouparia"]),
    ("Farmavida Comércio de Medicamentos Ltda", "Farmavida", "Pelotas", "RS", "Gilberto Sena", ["Medicamentos"]),
    ("BioEquip Tecnologia Médica S.A.", "BioEquip", "São Paulo", "SP", "Mariana Toledo",
     ["Equipamentos médicos", "Serviços técnicos"]),
    ("Lagoa Produtos Hospitalares Ltda", "Lagoa Hospitalar", "Rio Grande", "RS", "Élton Brum",
     ["Materiais médico-hospitalares", "Medicamentos", "Higiene e limpeza"]),
    ("Pampa Diagnósticos e Reagentes Ltda", "Pampa Diagnósticos", "Porto Alegre", "RS", "Fabiana Lopes",
     ["Laboratório e diagnóstico"]),
    ("CleanMax Higiene Profissional Ltda", "CleanMax", "Caxias do Sul", "RS", "Rogério Pasa",
     ["Higiene e limpeza", "EPIs e rouparia"]),
    ("NutriCare Alimentos Especiais Ltda", "NutriCare", "Curitiba", "PR", "Silvia Maranhão", ["Nutrição e dietas"]),
    ("Papelaria Central do Sul Ltda", "Central do Sul", "Rio Grande", "RS", "Renato Ávila",
     ["Material de escritório"]),
    ("TecnoData Informática Ltda", "TecnoData", "Porto Alegre", "RS", "Cíntia Bragança",
     ["Tecnologia da informação", "Material de escritório"]),
    ("Construfácil Materiais de Construção Ltda", "Construfácil", "Pelotas", "RS", "Anderson Pires",
     ["Manutenção predial"]),
    ("ProtegeMed EPIs e Uniformes Ltda", "ProtegeMed", "Novo Hamburgo", "RS", "Débora Klein",
     ["EPIs e rouparia", "Materiais médico-hospitalares"]),
    ("Vitalis Engenharia Clínica Ltda", "Vitalis", "Porto Alegre", "RS", "Henrique Maciel",
     ["Serviços técnicos", "Equipamentos médicos"]),
    ("Cirúrgica Atlântico Ltda", "Cirúrgica Atlântico", "Florianópolis", "SC", "Paula Werner",
     ["Materiais médico-hospitalares", "Equipamentos médicos", "Laboratório e diagnóstico"]),
    ("Hospitalar Minuano Comércio Ltda", "Minuano", "Santa Maria", "RS", "Vinícius Tavares",
     ["Medicamentos", "Nutrição e dietas", "Materiais médico-hospitalares"]),
    ("Sulpar Serviços Ambientais Ltda", "Sulpar", "Canoas", "RS", "Mauro Gehlen",
     ["Serviços técnicos", "Manutenção predial", "Higiene e limpeza"]),
]

SETOR_CATEGORIAS = {
    "uti_adulto": ["Medicamentos", "Materiais médico-hospitalares", "Equipamentos médicos"],
    "centro_cirurgico": ["Materiais médico-hospitalares", "Equipamentos médicos", "Medicamentos"],
    "pronto_socorro": ["Medicamentos", "Materiais médico-hospitalares", "Equipamentos médicos"],
    "uti_neonatal": ["Materiais médico-hospitalares", "Nutrição e dietas", "Equipamentos médicos"],
    "laboratorio": ["Laboratório e diagnóstico"],
    "farmacia": ["Medicamentos"],
    "nutricao": ["Nutrição e dietas"],
    "hotelaria": ["Higiene e limpeza", "EPIs e rouparia"],
    "tecnologia": ["Tecnologia da informação"],
    "manutencao": ["Manutenção predial"],
    "engenharia_clinica": ["Serviços técnicos", "Equipamentos médicos"],
    "administracao": ["Material de escritório", "Tecnologia da informação"],
}

TITULOS = {
    "Medicamentos": ["Reposição de estoque de medicamentos", "Medicamentos para protocolo assistencial",
                     "Reposição de soluções parenterais"],
    "Materiais médico-hospitalares": ["Reposição de materiais descartáveis", "Materiais para procedimentos",
                                      "Abastecimento mensal de descartáveis"],
    "Equipamentos médicos": ["Aquisição de {item}", "Substituição de {item}", "Ampliação do parque de equipamentos"],
    "Laboratório e diagnóstico": ["Reagentes e insumos laboratoriais", "Reposição de tubos de coleta"],
    "Higiene e limpeza": ["Saneantes para higienização hospitalar", "Reposição de materiais de higiene"],
    "Nutrição e dietas": ["Dietas enterais e suplementos", "Fórmulas e suplementos nutricionais"],
    "Material de escritório": ["Material de escritório — reposição trimestral", "Suprimentos de impressão"],
    "Tecnologia da informação": ["Renovação de estações de trabalho", "Equipamentos de informática"],
    "Manutenção predial": ["Materiais para manutenção predial", "Reforma e pintura de ambientes"],
    "EPIs e rouparia": ["Equipamentos de proteção individual", "Reposição de enxoval hospitalar"],
    "Serviços técnicos": ["Contratação de {item}", "Serviço de {item}"],
}

JUSTIFICATIVAS = {
    "material": [
        "Estoque atual abaixo do nível mínimo de segurança, com risco de desabastecimento nas próximas semanas.",
        "Aumento da taxa de ocupação do setor exige reposição antecipada para manter a continuidade assistencial.",
        "Consumo médio mensal superior ao previsto; a reposição evita compras emergenciais com preço maior.",
        "Substituição de itens com validade próxima do vencimento e padronização de marca junto ao setor.",
        "Adequação do setor ao novo protocolo institucional aprovado pela comissão de qualidade.",
    ],
    "equipamento": [
        "Equipamento atual apresenta falhas recorrentes e custo de manutenção elevado, comprometendo a segurança do paciente.",
        "Atendimento a exigência de acreditação hospitalar e às normas vigentes da vigilância sanitária.",
        "Ampliação da capacidade de atendimento do setor prevista no planejamento anual.",
    ],
    "servico": [
        "Manutenção preventiva prevista no plano anual, obrigatória para manter a certificação dos equipamentos.",
        "Atendimento a exigência de acreditação hospitalar e às normas vigentes da vigilância sanitária.",
        "Contrato anterior encerrado; o serviço é necessário para a continuidade da operação do setor.",
    ],
}
PAGAMENTOS = ["28 dias", "30 dias", "30/60 dias", "À vista com 3% de desconto", "45 dias", "30/60/90 dias"]
MOTIVOS_DEVOLUCAO = ["Detalhar a especificação técnica dos itens e anexar ao menos um orçamento de referência.",
                     "Revisar as quantidades: o consumo dos últimos 3 meses indica volume menor."]
MOTIVOS_REPROVACAO = ["Aquisição não prevista no orçamento do trimestre; reapresentar no próximo planejamento.",
                      "Existe contrato vigente que atende esta demanda; utilizar o fornecimento contratado."]
MOTIVOS_CANCELAMENTO = ["Demanda atendida por remanejamento de estoque entre setores.",
                        "Solicitação aberta em duplicidade com outra já em andamento."]

# (setor, status final, urgência, dias atrás aproximados, marcador opcional)
CENARIOS = [
    # Pendências da conta de demonstração do gestor/solicitante (UTI Adulto)
    ("uti_adulto", "aguardando_gestor", "urgente", 0.2, "equipamento"),
    ("uti_adulto", "aguardando_gestor", "normal", 1.5, None),
    ("uti_adulto", "devolvida", "normal", 3, None),
    ("uti_adulto", "em_cotacao", "urgente", 4, None),
    ("uti_adulto", "enviado", "normal", 12, None),
    ("uti_adulto", "concluida", "normal", 35, None),
    ("uti_adulto", "concluida", "imediato", 70, None),
    ("uti_adulto", "concluida", "normal", 120, None),
    # Diretoria
    ("engenharia_clinica", "aguardando_diretoria", "urgente", 1, "gestor"),
    ("tecnologia", "aguardando_diretoria", "normal", 2, "caro"),
    ("centro_cirurgico", "aguardando_diretoria", "imediato", 0.5, "equipamento"),
    ("pronto_socorro", "ped_aguardando_diretoria", "urgente", 9, "caro"),
    # Financeiro
    ("farmacia", "ped_aguardando_financeiro", "urgente", 7, None),
    ("laboratorio", "ped_aguardando_financeiro", "normal", 10, None),
    ("hotelaria", "ped_aguardando_financeiro", "normal", 6, None),
    # Comprador
    ("pronto_socorro", "aprovada", "imediato", 1, None),
    ("nutricao", "aprovada", "normal", 2, None),
    ("administracao", "aprovada", "normal", 4, None),
    ("centro_cirurgico", "em_cotacao", "urgente", 9, None),
    ("manutencao", "em_cotacao", "normal", 8, "sem_propostas"),
    ("uti_neonatal", "em_cotacao", "urgente", 6, None),
    ("laboratorio", "aguardando_pedido", "normal", 9, None),
    ("farmacia", "aguardando_pedido", "urgente", 8, None),
    ("tecnologia", "ped_aprovado", "normal", 13, None),
    # Recebimento
    ("centro_cirurgico", "enviado", "urgente", 11, None),
    ("farmacia", "enviado", "normal", 30, "atrasado"),
    ("nutricao", "entregue_parcial", "normal", 22, None),
    ("hotelaria", "entregue_parcial", "urgente", 25, None),
    # Encerradas
    ("laboratorio", "reprovada", "normal", 40, None),
    ("administracao", "reprovada", "normal", 75, None),
    ("tecnologia", "cancelada", "normal", 55, None),
    ("pronto_socorro", "cancelada", "urgente", 95, None),
    ("centro_cirurgico", "concluida", "urgente", 18, None),
    ("pronto_socorro", "concluida", "imediato", 26, None),
    ("farmacia", "concluida", "normal", 45, None),
    ("laboratorio", "concluida", "normal", 52, None),
    ("engenharia_clinica", "concluida", "normal", 60, "equipamento"),
    ("hotelaria", "concluida", "normal", 66, None),
    ("tecnologia", "concluida", "normal", 80, "caro"),
    ("nutricao", "concluida", "urgente", 88, None),
    ("uti_neonatal", "concluida", "normal", 100, None),
    ("manutencao", "concluida", "normal", 110, "gestor"),
    ("administracao", "concluida", "normal", 130, None),
    ("farmacia", "concluida", "urgente", 145, None),
    ("centro_cirurgico", "concluida", "normal", 160, None),
    ("pronto_socorro", "concluida", "normal", 175, None),
    ("laboratorio", "concluida", "normal", 190, None),
    ("engenharia_clinica", "concluida", "normal", 205, None),
    ("uti_neonatal", "concluida", "imediato", 150, "divergente"),
    ("farmacia", "concluida", "normal", 215, None),
    ("tecnologia", "concluida", "normal", 230, None),
    ("hotelaria", "concluida", "normal", 240, None),
]

ORDEM = ["aguardando_gestor", "devolvida", "reprovada", "cancelada", "aguardando_diretoria", "aprovada", "em_cotacao",
         "aguardando_pedido", "ped_aguardando_financeiro", "ped_aguardando_diretoria", "ped_aprovado", "enviado",
         "entregue_parcial", "concluida"]


def _d(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def cnpj_ficticio(r: random.Random) -> str:
    base = [r.randint(0, 9) for _ in range(8)] + [0, 0, 0, 1]

    def dv(nums, pesos):
        s = sum(n * p for n, p in zip(nums, pesos)) % 11
        return 0 if s < 2 else 11 - s
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(base, p1)
    d2 = dv(base + [d1], [6] + p1)
    return "".join(map(str, base + [d1, d2]))


class Semeador:
    def __init__(self, cur, segredo: str, hash_senha: str, termo_versao: str):
        self.cur = cur
        self.segredo = segredo
        self.hash_senha = hash_senha
        self.termo = termo_versao
        self.r = random.Random(20260927)
        self.agora = datetime.now(UTC).replace(microsecond=0)
        self.usuarios: dict[str, dict] = {}
        self.por_papel: dict[str, list[dict]] = {}
        self.assinaturas_pendentes: list[tuple] = []
        self.eventos: list[tuple] = []
        self.notificacoes: list[tuple] = []

    # ------------------------------------------------------------------ base
    def exec(self, sql, params=()):
        self.cur.execute(sql, params)

    def usuario(self, papel, nome, setor, cargo, email=None):
        email = email or (nome.lower().split()[0] + "." + nome.lower().split()[-1] + "@hrg.demo")
        email = (email.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
                 .replace("â", "a").replace("ê", "e").replace("ô", "o").replace("ã", "a").replace("õ", "o")
                 .replace("ç", "c").replace("ú", "u"))
        self.exec("select id from rg.usuarios where lower(email) = %s", (email,))
        linha = self.cur.fetchone()
        criado = self.agora - timedelta(days=self.r.randint(250, 400))
        if linha:
            uid = str(linha["id"])
            self.exec("update rg.usuarios set criado_em = %s, ultimo_login_em = %s where id = %s",
                      (criado, self.agora - timedelta(hours=self.r.randint(1, 72)), uid))
        else:
            uid = str(uuid.uuid4())
            self.exec("""insert into rg.usuarios (id, email, nome, setor_codigo, cargo, papel, status, senha_hash,
                            analisado_em, consentimento_lgpd_em, consentimento_versao, criado_em, ultimo_login_em)
                         values (%s, %s, %s, %s, %s, %s, 'aprovado', %s, %s, %s, %s, %s, %s)""",
                      (uid, email, nome, setor, cargo, papel, self.hash_senha, criado, criado, self.termo, criado,
                       self.agora - timedelta(hours=self.r.randint(1, 400))))
            self.exec("insert into rg.senhas_historico (usuario_id, senha_hash) values (%s, %s)", (uid, self.hash_senha))
        u = {"id": uid, "nome": nome, "papel": papel, "setor": setor}
        self.usuarios[uid] = u
        self.por_papel.setdefault(papel, []).append(u)
        return u

    def de(self, papel, setor=None):
        lista = [u for u in self.por_papel.get(papel, []) if setor is None or u["setor"] == setor]
        return lista[0] if lista else None

    def evento(self, quando, usuario, tabela, registro, operacao, campos=None, antes=None, depois=None):
        self.eventos.append((quando, usuario["id"] if usuario else None, "10.20.1." + str(self.r.randint(10, 250)),
                             tabela, registro, operacao, campos, antes, depois))

    def notificar(self, quando, usuario, tipo, titulo, mensagem, link, lida=None):
        if not usuario:
            return
        if lida is None:
            lida = (self.agora - quando) > timedelta(days=3)
        self.notificacoes.append((usuario["id"], tipo, titulo, mensagem, link, lida, quando))

    # ------------------------------------------------------------------ catálogo
    def catalogo(self):
        self.categorias, self.materiais = {}, {}
        for nome, cor, desc in CATEGORIAS:
            cid = str(uuid.uuid4())
            self.exec("insert into rg.categorias (id, nome, descricao, cor, criado_em) values (%s, %s, %s, %s, %s)",
                      (cid, nome, desc, cor, self.agora - timedelta(days=380)))
            self.categorias[nome] = cid
            self.materiais[nome] = []
            for mnome, un, preco in MATERIAIS[nome]:
                mid = str(uuid.uuid4())
                self.exec("""insert into rg.materiais (id, codigo, nome, categoria_id, unidade, preco_referencia, criado_em)
                             values (%s, 'MAT-' || lpad(nextval('rg.material_codigo_seq')::text, 5, '0'), %s, %s, %s, %s, %s)""",
                          (mid, mnome, cid, un, _d(preco), self.agora - timedelta(days=370)))
                self.materiais[nome].append({"id": mid, "nome": mnome, "unidade": un, "preco": _d(preco), "categoria": nome})

    def fornecedores_(self):
        self.fornecedores, self.forn_por_cat = [], {}
        for i, (razao, fantasia, cidade, uf, contato, cats) in enumerate(FORNECEDORES):
            fid = str(uuid.uuid4())
            cnpj = cnpj_ficticio(self.r)
            dominio = unicodedata.normalize("NFKD", fantasia.lower()).encode("ascii", "ignore").decode().replace(" ", "")
            self.exec("""insert into rg.fornecedores (id, razao_social, nome_fantasia, cnpj, email, telefone, contato, cidade,
                            uf, ativo, criado_em) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                      (fid, razao, fantasia, cnpj, f"vendas@{dominio}.demo", f"(5{self.r.randint(1, 4)}) 3{self.r.randint(100, 999)}-{self.r.randint(1000, 9999)}",
                       contato, cidade, uf, True, self.agora - timedelta(days=360 - i * 5)))
            f = {"id": fid, "nome": fantasia, "cats": cats, "qualidade": self.r.uniform(0.9, 1.08)}
            self.fornecedores.append(f)
            for c in cats:
                self.forn_por_cat.setdefault(c, []).append(f)
        # Um fornecedor inativo para ilustrar o cadastro
        self.exec("""insert into rg.fornecedores (razao_social, nome_fantasia, cnpj, cidade, uf, ativo, observacoes, criado_em)
                     values ('Oxigás Gases Medicinais Ltda', 'Oxigás', %s, 'Canoas', 'RS', false,
                             'Inativado após rescisão contratual (dados fictícios).', %s)""",
                  (cnpj_ficticio(self.r), self.agora - timedelta(days=300)))

    # ------------------------------------------------------------------ fluxo
    def assinar(self, sid, usuario, acao, quando, status_sol, pedido_id=None, status_ped=None, recebimento_id=None):
        self.assinaturas_pendentes.append((sid, usuario, acao, quando, status_sol, pedido_id, status_ped, recebimento_id))

    def historico(self, sid, quando, autor, acao, de, para, obs=None, pedido_id=None):
        self.exec("""insert into rg.solicitacao_historico (solicitacao_id, pedido_id, autor_id, acao, status_de, status_para,
                        observacao, criado_em) values (%s, %s, %s, %s, %s, %s, %s, %s)""",
                  (sid, pedido_id, autor["id"] if autor else None, acao, de, para, obs, quando))
        tabela = "rg.pedidos" if acao.startswith("pedido") else "rg.solicitacoes"
        self.evento(quando, autor, tabela, pedido_id or sid, "INSERT" if acao in ("criacao", "pedido_emitido") else "UPDATE",
                    ["status"] if de else None, {"status": de} if de else None, {"status": para})

    def cenario(self, n, setor, final, urgencia, dias, marcador):
        r = self.r
        cats = SETOR_CATEGORIAS[setor]
        categoria = "Equipamentos médicos" if marcador == "equipamento" and "Equipamentos médicos" in cats else r.choice(cats)
        if marcador == "caro" and setor == "tecnologia":
            categoria = "Tecnologia da informação"
        if marcador == "caro" and setor == "pronto_socorro":
            categoria = "Equipamentos médicos"
        materiais = self.materiais[categoria]
        caro = categoria in ("Equipamentos médicos", "Tecnologia da informação", "Serviços técnicos")
        qtd_itens = r.randint(1, 2) if caro else r.randint(2, 5)
        escolhidos = r.sample(materiais, min(qtd_itens, len(materiais)))
        itens = []
        for ordem, m in enumerate(escolhidos, start=1):
            if caro:
                qtd = Decimal(r.choice([1, 1, 2, 3, 4])) if m["unidade"] != "SV" else Decimal(r.choice([1, 2, 4]))
                if marcador == "caro":
                    qtd = Decimal(r.choice([6, 8, 10]))
            else:
                base = 100 if m["preco"] < 5 else 30 if m["preco"] < 50 else 6
                qtd = Decimal(r.randint(1, 8) * base)
            estimado = _d(m["preco"] * Decimal(str(r.uniform(0.95, 1.18))))
            itens.append({"id": str(uuid.uuid4()), "ordem": ordem, "material": m, "quantidade": qtd, "estimado": estimado})
        alcada = Decimal("25000")
        ajuste_proposta = 1.0
        if final in ("aguardando_diretoria", "ped_aguardando_diretoria"):
            m = max(materiais, key=lambda x: x["preco"])
            alvo = 34000 if final == "aguardando_diretoria" else 21000
            qtd = Decimal(max(1, -(-alvo // int(m["preco"])) if final == "aguardando_diretoria" else alvo // int(m["preco"])))
            itens = [{"id": str(uuid.uuid4()), "ordem": 1, "material": m, "quantidade": qtd,
                      "estimado": _d(m["preco"] * Decimal("0.97"))}]
            if final == "ped_aguardando_diretoria":
                ajuste_proposta = max(1.0, 25500 / (float(qtd * m["preco"]) * 0.84 * 0.9))
        valor_estimado = sum(_d(i["quantidade"] * i["estimado"]) for i in itens)

        solicitante = self.de("solicitante", setor) or self.de("gestor", setor)
        if marcador == "gestor":
            solicitante = self.de("gestor", setor)
        gestor = self.de("gestor", setor)
        diretoria = self.de("diretoria")
        comprador = self.por_papel["comprador"][n % len(self.por_papel["comprador"])]
        financeiro = self.de("financeiro")
        receb = self.por_papel["recebimento"][n % len(self.por_papel["recebimento"])]
        exige_dir = valor_estimado >= alcada

        # Linha do tempo relativa (horas desde a abertura)
        t = {"criacao": 0.0}
        t["gestor"] = r.uniform(3, 30)
        t["diretoria"] = t["gestor"] + r.uniform(4, 36)
        t["aprovada"] = t["diretoria"] if exige_dir else t["gestor"]
        t["cotacao"] = t["aprovada"] + r.uniform(1, 20)
        t["fornecedor"] = t["cotacao"] + r.uniform(24, 96)
        t["pedido"] = t["fornecedor"] + r.uniform(2, 20)
        t["financeiro"] = t["pedido"] + r.uniform(3, 30)
        prazo = r.choice([3, 5, 7, 10, 15]) if not caro else r.choice([10, 15, 20, 30])
        t["ped_diretoria"] = t["financeiro"] + r.uniform(3, 24)
        t["enviado"] = t["financeiro"] + r.uniform(1, 10)
        t["receb1"] = t["enviado"] + prazo * 24 + (r.uniform(-60, 6) if r.random() < 0.85 else r.uniform(30, 90))
        t["receb2"] = t["receb1"] + r.uniform(48, 120)
        etapa_final = {"aguardando_gestor": "criacao", "devolvida": "gestor", "reprovada": "gestor", "cancelada": "criacao",
                       "aguardando_diretoria": "gestor", "aprovada": "aprovada", "em_cotacao": "cotacao",
                       "aguardando_pedido": "fornecedor", "ped_aguardando_financeiro": "pedido",
                       "ped_aguardando_diretoria": "financeiro", "ped_aprovado": "financeiro", "enviado": "enviado",
                       "entregue_parcial": "receb1", "concluida": "receb2"}[final]
        if final == "concluida" and marcador != "divergente":
            t["receb2"] = t["receb1"]
        duracao = t[etapa_final] + (r.uniform(20, 60) if final == "em_cotacao" else 0)
        inicio = self.agora - timedelta(days=dias)
        if inicio + timedelta(hours=duracao) > self.agora - timedelta(minutes=20):
            inicio = self.agora - timedelta(hours=duracao) - timedelta(minutes=r.randint(20, 240))
        if marcador == "atrasado":
            alvo = self.agora - timedelta(days=4) - timedelta(hours=(t["enviado"] + prazo * 24))
            inicio = min(inicio, alvo)
        T = lambda chave: inicio + timedelta(hours=t[chave])  # noqa: E731

        aberta_gestor = solicitante["papel"] == "gestor"
        sid = str(uuid.uuid4())
        titulo_modelo = r.choice(TITULOS[categoria])
        nome_curto = itens[0]["material"]["nome"].split(" — ")[0].split(" (")[0]
        titulo = titulo_modelo.format(item=nome_curto[0].lower() + nome_curto[1:])
        tipo = "servico" if categoria == "Serviços técnicos" else "equipamento" if caro else "material"
        sla = {"imediato": 3, "urgente": 7, "normal": 14}[urgencia]
        s = {"id": sid, "status": None, "criado": T("criacao"), "titulo": titulo}
        ordem = ORDEM.index(final)

        def chegou(status):
            return ordem >= ORDEM.index(status)

        # ---- solicitação (linha inicial; o estado final é gravado ao término do cenário)
        status = "aguardando_diretoria" if aberta_gestor else "aguardando_gestor"
        self.exec("""insert into rg.solicitacoes (id, codigo, tipo, titulo, justificativa, setor_codigo, urgencia, status,
                       local_entrega, data_necessidade, solicitante_id, aberta_por_gestor, sla_prazo_limite, criado_em,
                       atualizado_em)
                     values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                  (sid, "TMP-" + sid[:12], tipo, titulo, r.choice(JUSTIFICATIVAS[tipo]), setor, urgencia, status,
                   r.choice([None, "Almoxarifado central", f"Posto de enfermagem — {setor.replace('_', ' ')}"]),
                   T("criacao").astimezone(TZ).date() + timedelta(days=sla + r.randint(3, 20)), solicitante["id"],
                   aberta_gestor, T("criacao") + timedelta(days=sla), T("criacao"), T("criacao")))
        for i in itens:
            m = i["material"]
            self.exec("""insert into rg.solicitacao_itens (id, solicitacao_id, ordem, material_id, descricao, unidade, quantidade,
                            valor_unitario_estimado, criado_em) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                      (i["id"], sid, i["ordem"], m["id"], m["nome"], m["unidade"], i["quantidade"], i["estimado"], T("criacao")))
        campos = dict(aprovado_gestor_por=None, aprovado_gestor_em=None, aprovado_diretoria_por=None,
                      aprovado_diretoria_em=None, aprovado_em=None, comprador_id=None, cotacao_iniciada_em=None,
                      fornecedor_definido_em=None, pedido_emitido_em=None, finalizado_em=None, sla_concluido_em=None,
                      motivo_devolucao=None, motivo_reprovacao=None, motivo_cancelamento=None, valor_final=None,
                      justificativa_escolha=None)
        historico = [(T("criacao"), solicitante, "criacao", None, status, None)]
        assinaturas = [(solicitante, "submissao", T("criacao"), status)]

        if final in ("devolvida", "reprovada") or chegou("aprovada") or final == "aguardando_diretoria":
            decisor = gestor if not aberta_gestor else diretoria
            if final in ("devolvida", "reprovada"):
                novo = final.replace("reprovada", "reprovada")
                motivo = r.choice(MOTIVOS_DEVOLUCAO if final == "devolvida" else MOTIVOS_REPROVACAO)
                campos["motivo_devolucao" if final == "devolvida" else "motivo_reprovacao"] = motivo
                historico.append((T("gestor"), decisor, "mudanca_status", status, final, motivo))
                assinaturas.append((decisor, "devolucao" if final == "devolvida" else "reprovacao", T("gestor"), final))
                self._aprovacao(sid, None, "gestor" if not aberta_gestor else "diretoria",
                                "devolvido" if final == "devolvida" else "reprovado", decisor, motivo, valor_estimado, T("gestor"))
                status = final
                if final == "reprovada":
                    campos["finalizado_em"] = campos["sla_concluido_em"] = T("gestor")
            else:
                if not aberta_gestor:
                    campos["aprovado_gestor_por"], campos["aprovado_gestor_em"] = gestor["id"], T("gestor")
                    proximo = "aguardando_diretoria" if (exige_dir or final == "aguardando_diretoria") else "aprovada"
                    historico.append((T("gestor"), gestor, "mudanca_status", status, proximo, "Aprovada pelo gestor do setor"))
                    assinaturas.append((gestor, "aprovacao_gestor", T("gestor"), proximo))
                    self._aprovacao(sid, None, "gestor", "aprovado", gestor, "De acordo com a necessidade do setor.",
                                    valor_estimado, T("gestor"))
                    status = proximo
                if status == "aguardando_diretoria" and final != "aguardando_diretoria":
                    campos["aprovado_diretoria_por"], campos["aprovado_diretoria_em"] = diretoria["id"], T("diretoria")
                    historico.append((T("diretoria"), diretoria, "mudanca_status", status, "aprovada",
                                      "Aprovada pela Diretoria: investimento previsto no plano anual."))
                    assinaturas.append((diretoria, "aprovacao_diretoria", T("diretoria"), "aprovada"))
                    self._aprovacao(sid, None, "diretoria", "aprovado", diretoria, "Investimento previsto no plano anual.",
                                    valor_estimado, T("diretoria"))
                    status = "aprovada"
                if status == "aprovada":
                    campos["aprovado_em"] = T("aprovada")
        if final == "cancelada":
            motivo = r.choice(MOTIVOS_CANCELAMENTO)
            quando = T("criacao") + timedelta(hours=r.uniform(4, 30))
            historico.append((quando, solicitante, "mudanca_status", status, "cancelada", motivo))
            campos.update(motivo_cancelamento=motivo, finalizado_em=quando, sla_concluido_em=quando)
            status = "cancelada"

        cotacoes, vencedora = [], None
        if chegou("em_cotacao") and status == "aprovada":
            campos["comprador_id"], campos["cotacao_iniciada_em"] = comprador["id"], T("cotacao")
            historico.append((T("cotacao"), comprador, "mudanca_status", "aprovada", "em_cotacao", "Cotação iniciada pelo comprador"))
            status = "em_cotacao"
            fornecedores = list(self.forn_por_cat.get(categoria, self.fornecedores))
            r.shuffle(fornecedores)
            n_prop = 0 if marcador == "sem_propostas" else min(len(fornecedores), r.choice([2, 3, 3, 4]))
            if final == "em_cotacao" and marcador != "sem_propostas":
                n_prop = min(n_prop, r.choice([1, 2, 3]))
            for k, f in enumerate(fornecedores[:n_prop]):
                cotacoes.append(self._proposta(sid, f, itens, comprador, T("cotacao") + timedelta(hours=6 + k * r.uniform(5, 20)),
                                               prazo, ajuste_proposta))
        if chegou("aguardando_pedido") and status == "em_cotacao" and cotacoes:
            completas = sorted(cotacoes, key=lambda c: c["total"])
            vencedora = completas[0]
            justificativa = None
            if len(cotacoes) >= 2 and r.random() < 0.25:
                vencedora = min(completas[:2], key=lambda c: c["prazo"])
                if vencedora is not completas[0]:
                    justificativa = "Menor prazo de entrega, essencial para a continuidade do atendimento."
            if len(cotacoes) < 3 and not justificativa:
                justificativa = "Fornecedores homologados para os itens são restritos; propostas recebidas dentro do prazo."
            self.exec("update rg.cotacoes set selecionada = true where id = %s", (vencedora["id"],))
            campos.update(cotacao_vencedora_id=vencedora["id"], justificativa_escolha=justificativa,
                          valor_final=vencedora["total"], fornecedor_definido_em=T("fornecedor"))
            historico.append((T("fornecedor"), comprador, "mudanca_status", "em_cotacao", "aguardando_pedido",
                              justificativa or f"Menor preço global: {vencedora['forn']['nome']}"))
            assinaturas.append((comprador, "definicao_fornecedor", T("fornecedor"), "aguardando_pedido"))
            status = "aguardando_pedido"

        pedido = None
        if chegou("ped_aguardando_financeiro") and vencedora:
            pedido = self._pedido(sid, vencedora, itens, comprador, T("pedido"), prazo, exige_dir, campos)
            campos.update(pedido_emitido_em=T("pedido"), sla_concluido_em=T("pedido"))
            historico.append((T("pedido"), comprador, "mudanca_status", "aguardando_pedido", "em_pedido", "Pedido de compra emitido"))
            status = "em_pedido"
            assinaturas.append((comprador, "emissao_pedido", T("pedido"), "em_pedido", pedido["id"], "aguardando_financeiro"))
            pstatus = "aguardando_financeiro"
            pcampos = {}
            precisa_dir_ped = pedido["valor"] >= alcada and not campos["aprovado_diretoria_em"]
            if chegou("ped_aguardando_diretoria") and final != "ped_aguardando_financeiro":
                prox = "aguardando_diretoria" if precisa_dir_ped else "aprovado"
                pcampos.update(aprovado_financeiro_por=financeiro["id"], aprovado_financeiro_em=T("financeiro"),
                               parecer_financeiro="Dotação orçamentária confirmada no centro de custo do setor.")
                self._hist_pedido(sid, pedido, T("financeiro"), financeiro, pstatus, prox, "Dotação orçamentária confirmada")
                assinaturas.append((financeiro, "aprovacao_financeiro", T("financeiro"), "em_pedido", pedido["id"], prox))
                self._aprovacao(sid, pedido["id"], "financeiro", "aprovado", financeiro,
                                "Dotação orçamentária confirmada no centro de custo do setor.", pedido["valor"], T("financeiro"))
                pstatus = prox
                if pstatus == "aguardando_diretoria" and final != "ped_aguardando_diretoria":
                    pcampos.update(aprovado_diretoria_por=diretoria["id"], aprovado_diretoria_em=T("ped_diretoria"),
                                   parecer_diretoria="Aprovado.")
                    self._hist_pedido(sid, pedido, T("ped_diretoria"), diretoria, pstatus, "aprovado", "Aprovado pela Diretoria")
                    assinaturas.append((diretoria, "aprovacao_diretoria_pedido", T("ped_diretoria"), "em_pedido",
                                        pedido["id"], "aprovado"))
                    self._aprovacao(sid, pedido["id"], "diretoria", "aprovado", diretoria, "Aprovado.", pedido["valor"],
                                    T("ped_diretoria"))
                    pstatus = "aprovado"
                    t["enviado"] = max(t["enviado"], t["ped_diretoria"] + 2)
            if chegou("enviado") and pstatus == "aprovado":
                previsao = (T("enviado").astimezone(TZ).date() + timedelta(days=prazo))
                pcampos.update(enviado_por=comprador["id"], enviado_em=T("enviado"), data_prevista_entrega=previsao)
                self._hist_pedido(sid, pedido, T("enviado"), comprador, "aprovado", "enviado", "Pedido enviado ao fornecedor")
                assinaturas.append((comprador, "envio_pedido", T("enviado"), "em_pedido", pedido["id"], "enviado"))
                pstatus = "enviado"
                self.notificar(T("enviado"), receb, "info", "Entrega prevista",
                               f"{titulo} · previsão {previsao:%d/%m/%Y}", f"/pedidos/{pedido['id']}")
            if chegou("entregue_parcial") and pstatus == "enviado":
                parcial = final == "entregue_parcial" or marcador == "divergente"
                rid, sit = self._recebimento(sid, pedido, receb, T("receb1"), parcial, marcador == "divergente")
                novo_p = "entregue_parcial" if parcial else "entregue"
                novo_s = "recebida_parcial" if parcial else "concluida"
                self._hist_pedido(sid, pedido, T("receb1"), receb, pstatus, novo_p, None)
                historico.append((T("receb1"), receb, "mudanca_status", "em_pedido", novo_s, None))
                assinaturas.append((receb, "recebimento", T("receb1"), novo_s, pedido["id"], novo_p, rid))
                pstatus, status = novo_p, novo_s
                if final == "concluida" and parcial:
                    rid2, _ = self._recebimento(sid, pedido, receb, T("receb2"), False, False)
                    self._hist_pedido(sid, pedido, T("receb2"), receb, pstatus, "entregue", None)
                    historico.append((T("receb2"), receb, "mudanca_status", status, "concluida", None))
                    assinaturas.append((receb, "recebimento", T("receb2"), "concluida", pedido["id"], "entregue", rid2))
                    pstatus, status = "entregue", "concluida"
                if pstatus == "entregue":
                    pcampos["concluido_em"] = T("receb2")
                    campos["finalizado_em"] = T("receb2")
            sets = ", ".join(f"{k} = %s" for k in pcampos)
            self.exec(f"update rg.pedidos set status = %s{', ' + sets if sets else ''} where id = %s",
                      (pstatus, *pcampos.values(), pedido["id"]))

        sets = ", ".join(f"{k} = %s" for k in campos)
        self.exec(f"update rg.solicitacoes set status = %s, versao = %s, atualizado_em = %s, {sets} where id = %s",
                  (status, len(historico), historico[-1][0], *campos.values(), sid))
        for h in historico:
            self.historico(sid, h[0], h[1], h[2], h[3], h[4], h[5])
        for a in assinaturas:
            self.assinar(sid, a[0], a[1], a[2], a[3], *(a[4:] if len(a) > 4 else ()))
        self._notificacoes_cenario(sid, titulo, status, solicitante, gestor, diretoria, comprador, historico[-1][0], setor)
        return {"id": sid, "criado": T("criacao"), "status": status}

    def _aprovacao(self, sid, pedido_id, nivel, decisao, usuario, parecer, valor, quando):
        self.aprovacoes.append((sid, pedido_id, nivel, decisao, usuario["id"], parecer, valor, quando))

    def _proposta(self, sid, f, itens, comprador, quando, prazo_base, ajuste=1.0):
        r = self.r
        cid = str(uuid.uuid4())
        linhas, total_itens = [], Decimal("0")
        for i in itens:
            unit = _d(i["material"]["preco"] * Decimal(str(r.uniform(0.84, 1.16) * f["qualidade"] * ajuste)))
            linhas.append((str(uuid.uuid4()), cid, i["id"], i["quantidade"], unit, r.choice([None, "Marca A", "Marca B", "Nacional", "Importado"])))
            total_itens += _d(i["quantidade"] * unit)
        frete = Decimal("0") if total_itens > 3000 or r.random() < 0.4 else _d(r.choice([45, 80, 120, 180]))
        desconto = _d(total_itens * Decimal("0.02")) if r.random() < 0.2 else Decimal("0")
        prazo = max(1, prazo_base + r.randint(-3, 5))
        total = total_itens + frete - desconto
        data = quando.astimezone(TZ).date()
        self.exec("""insert into rg.cotacoes (id, solicitacao_id, fornecedor_id, numero_proposta, data_proposta, validade_proposta,
                        prazo_entrega_dias, condicoes_pagamento, frete, desconto, valor_itens, valor_total, criado_por,
                        criado_em, atualizado_em) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                  (cid, sid, f["id"], f"{r.randint(1000, 9999)}/{data:%Y}", data, data + timedelta(days=r.choice([10, 15, 30])),
                   prazo, r.choice(PAGAMENTOS), frete, desconto, total_itens, total, comprador["id"], quando, quando))
        for linha in linhas:
            self.exec("""insert into rg.cotacao_itens (id, cotacao_id, solicitacao_item_id, quantidade, valor_unitario, marca)
                         values (%s, %s, %s, %s, %s, %s)""", linha)
        return {"id": cid, "total": total, "prazo": prazo, "forn": f, "itens": linhas, "frete": frete,
                "desconto": desconto, "valor_itens": total_itens}

    def _pedido(self, sid, cot, itens, comprador, quando, prazo, exige_dir, campos):
        pid = str(uuid.uuid4())
        self.exec("""insert into rg.pedidos (id, codigo, solicitacao_id, cotacao_id, fornecedor_id, status, valor_itens, frete,
                        desconto, valor_total, condicoes_pagamento, prazo_entrega_dias, local_entrega, comprador_id,
                        exige_diretoria, criado_em, atualizado_em)
                     select %s, 'TMP-' || left(%s::text, 12), %s, c.id, c.fornecedor_id, 'aguardando_financeiro', c.valor_itens, c.frete, c.desconto,
                            c.valor_total, c.condicoes_pagamento, c.prazo_entrega_dias, 'Almoxarifado central', %s, %s, %s, %s
                       from rg.cotacoes c where c.id = %s""",
                  (pid, pid, sid, comprador["id"], cot["total"] >= 25000 and not campos["aprovado_diretoria_em"], quando, quando,
                   cot["id"]))
        self.pedidos_criados.append((quando, pid))
        itens_por_id = {i["id"]: i for i in itens}
        self.pedido_itens[pid] = []
        for (_, _, si_id, qtd, unit, marca) in cot["itens"]:
            m = itens_por_id[si_id]["material"]
            piid = str(uuid.uuid4())
            self.exec("""insert into rg.pedido_itens (id, pedido_id, solicitacao_item_id, material_id, ordem, descricao, unidade,
                            marca, quantidade, valor_unitario) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                      (piid, pid, si_id, m["id"], itens_por_id[si_id]["ordem"], m["nome"], m["unidade"], marca, qtd, unit))
            self.pedido_itens[pid].append({"id": piid, "quantidade": qtd, "recebido": Decimal("0"), "material": m,
                                           "unit": unit})
            self.exec("update rg.materiais set ultimo_preco = %s, ultima_compra_em = %s where id = %s", (unit, quando, m["id"]))
        self.exec("""insert into rg.solicitacao_historico (solicitacao_id, pedido_id, autor_id, acao, status_para, observacao,
                        criado_em) values (%s, %s, %s, 'pedido_emitido', 'aguardando_financeiro', %s, %s)""",
                  (sid, pid, comprador["id"], "Pedido de compra emitido", quando))
        return {"id": pid, "valor": cot["total"], "codigo": "pedido"}

    def _hist_pedido(self, sid, pedido, quando, autor, de, para, obs):
        self.historico(sid, quando, autor, "pedido_status", de, para, obs, pedido_id=pedido["id"])

    def _recebimento(self, sid, pedido, receb, quando, parcial, divergente):
        r = self.r
        rid = str(uuid.uuid4())
        nf = str(r.randint(10000, 99999))
        itens = self.pedido_itens[pedido["id"]]
        linhas, valor, situacao = [], Decimal("0"), "conforme"
        for k, it in enumerate(itens):
            saldo = it["quantidade"] - it["recebido"]
            if saldo <= 0:
                continue
            recebida = saldo
            if parcial and (k == 0 or len(itens) == 1):
                recebida = (saldo / 2).quantize(Decimal("1")) or saldo
            aceita, motivo = recebida, None
            if divergente and k == 0:
                aceita = max(Decimal("0"), recebida - max(Decimal("1"), (recebida * Decimal("0.1")).quantize(Decimal("1"))))
                motivo = "Embalagens avariadas no transporte; itens devolvidos ao fornecedor."
                situacao = "divergente"
            it["recebido"] += aceita
            linhas.append((str(uuid.uuid4()), rid, it["id"], recebida, aceita, motivo))
            valor += _d(recebida * it["unit"])
        self.exec("""insert into rg.recebimentos (id, codigo, pedido_id, solicitacao_id, nota_fiscal, data_emissao_nf, valor_nf,
                        situacao, observacoes, processado, recebido_por, recebido_em, criado_em)
                     values (%s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s, %s, %s)""",
                  (rid, "TMP-" + rid[:12], pedido["id"], sid, nf, (quando - D).astimezone(TZ).date(), valor, situacao,
                   "Avaria em parte da carga." if situacao != "conforme" else None, receb["id"], quando, quando))
        self.recebimentos_criados.append((quando, rid))
        for linha in linhas:
            self.exec("""insert into rg.recebimento_itens (id, recebimento_id, pedido_item_id, quantidade_recebida,
                            quantidade_aceita, motivo_divergencia) values (%s, %s, %s, %s, %s, %s)""", linha)
            self.exec("update rg.pedido_itens set quantidade_recebida = quantidade_recebida + %s where id = %s",
                      (linha[4], linha[2]))
        self.exec("""insert into rg.solicitacao_historico (solicitacao_id, pedido_id, autor_id, acao, status_para, observacao,
                        criado_em) values (%s, %s, %s, 'recebimento', %s, %s, %s)""",
                  (sid, pedido["id"], receb["id"], situacao, f"NF {nf}" + (" · Avaria em parte da carga" if situacao != "conforme" else ""),
                   quando))
        return rid, situacao

    def _notificacoes_cenario(self, sid, titulo, status, solicitante, gestor, diretoria, comprador, quando, setor):
        link = f"/solicitacoes/{sid}"
        if status == "aguardando_gestor":
            self.notificar(quando, gestor, "info", "Solicitação aguardando sua aprovação", titulo, link, lida=False)
        elif status == "aguardando_diretoria":
            self.notificar(quando, diretoria, "info", "Solicitação aguardando aprovação da Diretoria", titulo, link, lida=False)
        elif status == "devolvida":
            self.notificar(quando, solicitante, "alerta", "Solicitação devolvida para ajustes", titulo, link, lida=False)
        elif status == "aprovada":
            for c in self.por_papel["comprador"]:
                self.notificar(quando, c, "info", "Nova solicitação aprovada para cotação", titulo, link, lida=False)
        elif status == "concluida":
            self.notificar(quando, solicitante, "sucesso", "Solicitação concluída", titulo + ": itens recebidos e conferidos.", link)
        elif status == "reprovada":
            self.notificar(quando, solicitante, "erro", "Solicitação reprovada", titulo, link)

    # ------------------------------------------------------------------ execução
    def executar(self):
        for c in CONTAS_TESTE:
            self.usuario(c["papel"], c["nome"], c["setor_codigo"], c["cargo"], c["email"])
        for papel, nome, setor, cargo in USUARIOS_EXTRAS:
            self.usuario(papel, nome, setor, cargo)
        # Cadastros aguardando análise do Administrador
        for nome, email, setor, papel, cargo in (("Fábio Quintana", "fabio.quintana@hrg.demo", "imagem", "solicitante",
                                                  "Técnico em Radiologia"),
                                                 ("Isabela Duarte", "isabela.duarte@hrg.demo", "cme", "solicitante",
                                                  "Enfermeira da CME")):
            quando = self.agora - timedelta(hours=self.r.randint(3, 40))
            uid = str(uuid.uuid4())
            self.exec("""insert into rg.usuarios (id, email, nome, setor_codigo, cargo, papel, status, senha_hash,
                            consentimento_lgpd_em, consentimento_versao, criado_em)
                         values (%s, %s, %s, %s, %s, %s, 'pendente', %s, %s, %s, %s)""",
                      (uid, email, nome, setor, cargo, papel, self.hash_senha, quando, self.termo, quando))
            self.notificar(quando, self.de("admin"), "alerta", "Novo cadastro aguardando aprovação",
                           f"{nome} ({email}) solicitou acesso.", "/usuarios?status=pendente", lida=False)
        self.catalogo()
        self.fornecedores_()
        self.aprovacoes, self.pedidos_criados, self.recebimentos_criados, self.pedido_itens = [], [], [], {}
        criadas = [self.cenario(n, *c) for n, c in enumerate(CENARIOS)]

        # Códigos sequenciais na ordem cronológica
        for s in sorted(criadas, key=lambda x: x["criado"]):
            self.exec("update rg.solicitacoes set codigo = 'SC-' || to_char(criado_em at time zone 'America/Sao_Paulo', 'YYYY')"
                      " || '-' || lpad(nextval('rg.solicitacao_codigo_seq')::text, 5, '0') where id = %s", (s["id"],))
        for _, pid in sorted(self.pedidos_criados):
            self.exec("update rg.pedidos set codigo = 'PC-' || to_char(criado_em at time zone 'America/Sao_Paulo', 'YYYY')"
                      " || '-' || lpad(nextval('rg.pedido_codigo_seq')::text, 5, '0') where id = %s", (pid,))
        for _, rid in sorted(self.recebimentos_criados):
            self.exec("update rg.recebimentos set codigo = 'RC-' || to_char(recebido_em at time zone 'America/Sao_Paulo', 'YYYY')"
                      " || '-' || lpad(nextval('rg.recebimento_codigo_seq')::text, 5, '0') where id = %s", (rid,))
        self.exec("""update rg.solicitacao_historico h set observacao = 'Pedido ' || p.codigo || ' emitido · '
                        || to_char(p.valor_total, 'FM"R$ "999G999G990D00')
                       from rg.pedidos p where h.pedido_id = p.id and h.acao = 'pedido_emitido'""")
        self.exec("""update rg.solicitacao_historico h set observacao = r.codigo || ' · ' || h.observacao
                       from rg.recebimentos r where r.pedido_id = h.pedido_id and h.acao = 'recebimento'
                        and r.recebido_em = h.criado_em""")

        for a in self.aprovacoes:
            self.exec("""insert into rg.aprovacoes (solicitacao_id, pedido_id, nivel, decisao, usuario_id, parecer, valor, criado_em)
                         values (%s, %s, %s, %s, %s, %s, %s, %s)""", a)

        # Assinaturas: HMAC calculado com a mesma rotina da aplicação
        hashes = {}
        for (sid, usuario, acao, quando, status_sol, pedido_id, status_ped, rid) in self.assinaturas_pendentes:
            if sid not in hashes:
                hashes[sid] = calcular_conteudo_hash(self.cur, sid)
            ip = "10.20.1." + str(self.r.randint(10, 250))
            h = calcular_hash(self.segredo, sid, usuario["id"], quando, ip, hashes[sid], acao, status_sol, status_ped,
                              pedido_id, rid)
            self.exec("""insert into rg.assinaturas (solicitacao_id, pedido_id, recebimento_id, usuario_id, papel, acao,
                            status_solicitacao, status_pedido, ip, user_agent, assinado_em, conteudo_hash, hash_autenticidade,
                            txid, criado_em)
                         values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s)""",
                      (sid, pedido_id, rid, usuario["id"], usuario["papel"], acao, status_sol, status_ped, ip,
                       "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Estação HRG", quando, hashes[sid], h, quando))

        # Notificações dos pedidos pendentes de aprovação
        self.exec("select id, codigo, status, criado_em, atualizado_em from rg.pedidos where status in ('aguardando_financeiro', 'aguardando_diretoria', 'aprovado')")
        for p in self.cur.fetchall():
            if p["status"] == "aguardando_financeiro":
                self.notificar(p["criado_em"], self.de("financeiro"), "info", "Pedido aguardando aprovação financeira",
                               p["codigo"], f"/pedidos/{p['id']}", lida=False)
            elif p["status"] == "aguardando_diretoria":
                self.notificar(p["criado_em"], self.de("diretoria"), "info", "Pedido aguardando aprovação da Diretoria",
                               p["codigo"], f"/pedidos/{p['id']}", lida=False)
        for n in self.notificacoes:
            self.exec("""insert into rg.notificacoes (destinatario_id, tipo, titulo, mensagem, link, lida, lida_em, criado_em)
                         values (%s, %s, %s, %s, %s, %s, case when %s then %s + interval '2 hours' end, %s)""",
                      (n[0], n[1], n[2], n[3], n[4], n[5], n[5], n[6], n[6]))

        # Trilha de auditoria: acessos e movimentações
        for u in self.usuarios.values():
            for _ in range(self.r.randint(2, 6)):
                self.evento(self.agora - timedelta(hours=self.r.uniform(1, 24 * 20)), u, "rg.usuarios", u["id"], "LOGIN")
        for e in sorted(self.eventos, key=lambda x: x[0]):
            self.exec("""insert into audit.eventos (ocorrido_em, usuario_id, ip, tabela, registro_id, operacao, campos_alterados,
                            dados_antes, dados_depois) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                      (e[0], e[1], e[2], e[3], e[4], e[5], e[6], Jsonb(e[7]) if e[7] else None, Jsonb(e[8]) if e[8] else None))
        return len(criadas)


def ja_semeado(cur) -> bool:
    cur.execute("select exists (select 1 from rg.solicitacoes) as s")
    return cur.fetchone()["s"]


def semear_demo(conn, *, segredo: str, hash_senha: str, termo_versao: str) -> int:
    """Popula o banco com dados fictícios. Retorna a quantidade de solicitações criadas (0 se já havia dados)."""
    with conn.transaction():
        cur = conn.cursor()
        if ja_semeado(cur):
            return 0
        for tabela in TABELAS:
            cur.execute(f"alter table {tabela} disable trigger user")
        try:
            quantidade = Semeador(cur, segredo, hash_senha, termo_versao).executar()
        finally:
            for tabela in TABELAS:
                cur.execute(f"alter table {tabela} enable trigger user")
    return quantidade


