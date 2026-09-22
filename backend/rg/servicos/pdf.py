"""Relatórios PDF institucionais (ReportLab) com logotipo, metadados e código de verificação."""
from __future__ import annotations

import hashlib
import io
import json
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from .. import marca
from ..rotulos import (CATEGORIA_SERVICO, PERIODICIDADE, SITUACAO_SERVICO, SLA_SITUACAO, STATUS_SOLICITACAO,
                       TIPO_SOLICITACAO, URGENCIA, ACAO_ASSINATURA)

PRIMARIA = colors.HexColor("#2E5C88")
DESTAQUE = colors.HexColor("#8EB7E5")
SUCESSO = colors.HexColor("#2FA84F")
TEXTO = colors.HexColor("#1F2937")
SUAVE = colors.HexColor("#64748B")
LINHA = colors.HexColor("#D8E1EC")
FUNDO_TAB = colors.HexColor("#F1F5FA")
PALETA = ["#2E5C88", "#8EB7E5", "#2FA84F", "#C2410C", "#9333EA", "#0891B2", "#DB2777", "#A16207", "#4F46E5", "#475569"]

_estilos = getSampleStyleSheet()
E = {
    "titulo": ParagraphStyle("titulo", parent=_estilos["Title"], fontName="Helvetica-Bold", fontSize=16,
                             textColor=PRIMARIA, alignment=TA_LEFT, spaceAfter=2, leading=20),
    "subtitulo": ParagraphStyle("subtitulo", parent=_estilos["Normal"], fontSize=9, textColor=SUAVE, spaceAfter=8),
    "h2": ParagraphStyle("h2", parent=_estilos["Heading2"], fontName="Helvetica-Bold", fontSize=11.5,
                         textColor=PRIMARIA, spaceBefore=10, spaceAfter=5),
    "normal": ParagraphStyle("normal", parent=_estilos["Normal"], fontSize=9, leading=12.5, textColor=TEXTO),
    "pequeno": ParagraphStyle("pequeno", parent=_estilos["Normal"], fontSize=7.5, leading=9.5, textColor=SUAVE),
    "celula": ParagraphStyle("celula", parent=_estilos["Normal"], fontSize=8, leading=10, textColor=TEXTO),
    "celula_b": ParagraphStyle("celula_b", parent=_estilos["Normal"], fontName="Helvetica-Bold", fontSize=8,
                               leading=10, textColor=colors.white),
    "mono": ParagraphStyle("mono", parent=_estilos["Normal"], fontName="Courier", fontSize=6.8, leading=8.5,
                           textColor=TEXTO),
    "kpi_valor": ParagraphStyle("kpi_valor", parent=_estilos["Normal"], fontName="Helvetica-Bold", fontSize=15,
                                leading=18, textColor=PRIMARIA),
    "kpi_rotulo": ParagraphStyle("kpi_rotulo", parent=_estilos["Normal"], fontSize=7.5, leading=9, textColor=SUAVE),
}


def esc(texto) -> str:
    if texto is None:
        return "—"
    return (str(texto).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\n", "<br/>"))


def moeda(valor) -> str:
    if valor is None:
        return "—"
    v = Decimal(str(valor))
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_hora(valor, tz: str = "America/Sao_Paulo") -> str:
    if valor is None:
        return "—"
    if isinstance(valor, datetime):
        return valor.astimezone(ZoneInfo(tz)).strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


def _serializar(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    return str(obj)


def codigo_verificacao(conteudo: dict) -> str:
    texto = json.dumps(conteudo, sort_keys=True, default=_serializar, ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class _Documento(BaseDocTemplate):
    def __init__(self, buffer, *, titulo: str, autor: str, instituicao: str, codigo: str, emitido_em: str,
                 paisagem: bool = False):
        tamanho = landscape(A4) if paisagem else A4
        super().__init__(buffer, pagesize=tamanho, leftMargin=16 * mm, rightMargin=16 * mm,
                         topMargin=30 * mm, bottomMargin=20 * mm, title=titulo, author=instituicao,
                         subject=titulo, creator="RG Hospital — Plataforma Corporativa",
                         keywords=f"verificacao:{codigo}")
        self.titulo_doc = titulo
        self.autor = autor
        self.instituicao = instituicao
        self.codigo = codigo
        self.emitido_em = emitido_em
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="corpo")
        self.addPageTemplates([PageTemplate(id="institucional", frames=[frame], onPage=self._moldura)])

    def _moldura(self, canvas, doc):
        largura, altura = doc.pagesize
        canvas.saveState()
        canvas.setFillColor(PRIMARIA)
        canvas.rect(0, altura - 4 * mm, largura, 4 * mm, stroke=0, fill=1)
        marca.desenhar_pdf(canvas, doc.leftMargin, altura - 22 * mm, 58 * mm, "#2E5C88")
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(PRIMARIA)
        canvas.drawRightString(largura - doc.rightMargin, altura - 13 * mm, self.titulo_doc[:90])
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(SUAVE)
        canvas.drawRightString(largura - doc.rightMargin, altura - 17.5 * mm, f"Emitido em {self.emitido_em}")
        canvas.setStrokeColor(LINHA)
        canvas.setLineWidth(0.6)
        canvas.line(doc.leftMargin, altura - 25 * mm, largura - doc.rightMargin, altura - 25 * mm)
        canvas.line(doc.leftMargin, 15 * mm, largura - doc.rightMargin, 15 * mm)
        canvas.setFont("Helvetica", 6.8)
        canvas.drawString(doc.leftMargin, 11 * mm,
                          f"{self.instituicao} · Documento gerado por {self.autor} · Uso interno — dados protegidos pela LGPD")
        canvas.drawString(doc.leftMargin, 7.5 * mm, f"Código de verificação (SHA-256): {self.codigo}")
        canvas.drawRightString(largura - doc.rightMargin, 11 * mm, f"Página {doc.page}")
        canvas.restoreState()


def _tabela(cabecalho: list[str], linhas: list[list], larguras: list[float] | None = None, *,
            zebra: bool = True, fonte_mono: set[int] | None = None) -> Table:
    fonte_mono = fonte_mono or set()
    dados = [[Paragraph(esc(c), E["celula_b"]) for c in cabecalho]]
    for linha in linhas:
        dados.append([
            c if hasattr(c, "wrap") else Paragraph(esc(c), E["mono"] if i in fonte_mono else E["celula"])
            for i, c in enumerate(linha)
        ])
    tabela = Table(dados, colWidths=larguras, repeatRows=1)
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARIA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINHA),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    if zebra:
        for i in range(2, len(dados), 2):
            estilo.append(("BACKGROUND", (0, i), (-1, i), FUNDO_TAB))
    tabela.setStyle(TableStyle(estilo))
    return tabela


def _pares(pares: list[tuple[str, str]], largura_total: float, colunas: int = 2) -> Table:
    celulas, linha = [], []
    for rotulo, valor in pares:
        linha.append(Paragraph(f"<font color='#64748B' size='7.5'>{esc(rotulo)}</font><br/>{valor}", E["normal"]))
        if len(linha) == colunas:
            celulas.append(linha)
            linha = []
    if linha:
        linha += [""] * (colunas - len(linha))
        celulas.append(linha)
    t = Table(celulas, colWidths=[largura_total / colunas] * colunas)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _kpis(itens: list[tuple[str, str]], largura_total: float) -> Table:
    linha_valores = [Paragraph(esc(v), E["kpi_valor"]) for _, v in itens]
    linha_rotulos = [Paragraph(esc(r), E["kpi_rotulo"]) for r, _ in itens]
    t = Table([linha_valores, linha_rotulos], colWidths=[largura_total / len(itens)] * len(itens))
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, LINHA),
        ("INNERGRID", (0, 0), (-1, -1), 0, colors.white),
        ("LINEAFTER", (0, 0), (-2, -1), 0.6, LINHA),
        ("BACKGROUND", (0, 0), (-1, -1), FUNDO_TAB),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


def _grafico_barras_h(titulo: str, rotulos: list[str], valores: list[float], largura: float,
                      formato=lambda v: f"{v:g}", monetario: bool = False) -> Drawing:
    faixa = 24  # altura por categoria: barras finas (14 pt) com respiro
    altura = faixa * max(1, len(rotulos)) + 52
    d = Drawing(largura, altura)
    d.add(String(0, altura - 12, titulo, fontName="Helvetica-Bold", fontSize=9, fillColor=PRIMARIA))
    if not valores or not any(valores):
        d.add(String(0, altura - 34, "Sem dados no período.", fontName="Helvetica", fontSize=8, fillColor=SUAVE))
        return d
    g = HorizontalBarChart()
    g.x = 120
    g.y = 22
    g.width = largura - 190
    g.height = faixa * len(rotulos)
    g.data = [list(reversed(valores))]
    g.categoryAxis.categoryNames = list(reversed([r[:26] for r in rotulos]))
    g.categoryAxis.labels.fontSize = 7.5
    g.categoryAxis.labels.fontName = "Helvetica"
    g.categoryAxis.strokeColor = LINHA
    g.categoryAxis.visibleTicks = False
    g.groupSpacing = 10
    maximo = max(valores)
    passo = _passo(maximo, inteiro=not monetario)
    g.valueAxis.valueMin = 0
    g.valueAxis.valueMax = passo * max(1, -(-maximo // passo))
    g.valueAxis.valueStep = passo
    g.valueAxis.labels.fontSize = 6.5
    g.valueAxis.labels.fontName = "Helvetica"
    g.valueAxis.labelTextFormat = (lambda v: moeda(v).replace(",00", "")) if monetario else (lambda v: f"{v:,.0f}".replace(",", "."))
    g.valueAxis.strokeColor = LINHA
    g.valueAxis.gridStrokeColor = LINHA
    g.valueAxis.visibleGrid = True
    g.bars[0].fillColor = PRIMARIA
    g.bars[0].strokeColor = None
    g.barLabelFormat = formato
    g.barLabels.fontName = "Helvetica"
    g.barLabels.fontSize = 7
    g.barLabels.boxAnchor = "w"
    g.barLabels.dx = 3
    d.add(g)
    return d


def _passo(maximo: float, inteiro: bool = True) -> float:
    import math
    if maximo <= 0:
        return 1
    bruto = maximo / 4
    mag = 10 ** math.floor(math.log10(bruto))
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= bruto:
            passo = m * mag
            break
    return max(1, math.ceil(passo)) if inteiro else passo


def _grafico_rosca(titulo: str, rotulos: list[str], valores: list[float], largura: float) -> Drawing:
    altura = 150
    d = Drawing(largura, altura)
    d.add(String(0, altura - 12, titulo, fontName="Helvetica-Bold", fontSize=9, fillColor=PRIMARIA))
    if not valores or sum(valores) == 0:
        d.add(String(0, altura - 34, "Sem dados no período.", fontName="Helvetica", fontSize=8, fillColor=SUAVE))
        return d
    p = Pie()
    p.x, p.y, p.width, p.height = 10, 10, 110, 110
    p.data = valores
    p.innerRadiusFraction = 0.55
    p.slices.strokeColor = colors.white
    p.slices.strokeWidth = 1
    for i in range(len(valores)):
        p.slices[i].fillColor = colors.HexColor(PALETA[i % len(PALETA)])
    d.add(p)
    total = sum(valores)
    for i, (r, v) in enumerate(zip(rotulos, valores)):
        y = 118 - i * 13
        d.add(Rect(140, y - 1, 7, 7, fillColor=colors.HexColor(PALETA[i % len(PALETA)]), strokeColor=None))
        d.add(String(152, y, f"{r}: {v:g} ({v / total:.0%})", fontName="Helvetica", fontSize=7.5, fillColor=TEXTO))
    return d


def _grafico_colunas(titulo: str, rotulos: list[str], series: list[list[float]], nomes: list[str],
                     largura: float) -> Drawing:
    altura = 170
    d = Drawing(largura, altura)
    d.add(String(0, altura - 12, titulo, fontName="Helvetica-Bold", fontSize=9, fillColor=PRIMARIA))
    if not rotulos:
        d.add(String(0, altura - 34, "Sem dados no período.", fontName="Helvetica", fontSize=8, fillColor=SUAVE))
        return d
    g = VerticalBarChart()
    g.x, g.y, g.width, g.height = 40, 30, largura - 60, altura - 60
    g.data = series
    g.categoryAxis.categoryNames = rotulos
    g.categoryAxis.labels.fontSize = 7
    g.valueAxis.valueMin = 0
    g.valueAxis.labels.fontSize = 6.5
    g.valueAxis.labels.fontName = "Helvetica"
    g.categoryAxis.labels.fontName = "Helvetica"
    g.valueAxis.visibleGrid = True
    g.valueAxis.gridStrokeColor = LINHA
    g.valueAxis.strokeColor = LINHA
    g.categoryAxis.strokeColor = LINHA
    g.groupSpacing = 6
    for i in range(len(series)):
        g.bars[i].fillColor = colors.HexColor(PALETA[i % len(PALETA)])
        g.bars[i].strokeColor = None
    d.add(g)
    for i, nome in enumerate(nomes):
        d.add(Rect(40 + i * 120, 7, 7, 7, fillColor=colors.HexColor(PALETA[i % len(PALETA)]), strokeColor=None))
        d.add(String(51 + i * 120, 8, nome, fontName="Helvetica", fontSize=7.5, fillColor=TEXTO))
    return d


def _montar(elementos, *, titulo: str, autor: str, instituicao: str, codigo: str, tz: str,
            paisagem: bool = False) -> bytes:
    buffer = io.BytesIO()
    emitido = datetime.now(ZoneInfo(tz)).strftime("%d/%m/%Y %H:%M")
    doc = _Documento(buffer, titulo=titulo, autor=autor, instituicao=instituicao, codigo=codigo,
                     emitido_em=emitido, paisagem=paisagem)
    doc.build(elementos)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Relatórios
# ---------------------------------------------------------------------------
def dossie_solicitacao(detalhe: dict, *, autor: str, instituicao: str, tz: str) -> tuple[bytes, str]:
    s = detalhe["solicitacao"]
    codigo = codigo_verificacao({"tipo": "dossie", "solicitacao": s, "assinaturas": detalhe["assinaturas"],
                                 "historico": detalhe["historico"]})
    largura = A4[0] - 32 * mm
    el = [
        Paragraph(f"Dossiê da solicitação {esc(s['codigo'])}", E["titulo"]),
        Paragraph(esc(s["titulo"]), E["subtitulo"]),
        _pares([
            ("Status", esc(STATUS_SOLICITACAO.get(s["status"], s["status"]))),
            ("Tipo", esc(TIPO_SOLICITACAO.get(s["tipo"], s["tipo"]))),
            ("Setor", esc(s["setor_nome"])),
            ("Urgência", esc(URGENCIA.get(s["urgencia"], s["urgencia"]))),
            ("Gestor solicitante", esc(s["gestor_nome"])),
            ("Comprador responsável", esc(s["comprador_nome"])),
            ("Aberta em", data_hora(s["criado_em"], tz)),
            ("Prazo SLA", f"{data_hora(s['sla_prazo_limite'], tz)} — {esc(SLA_SITUACAO.get(s['sla_situacao'], s['sla_situacao']))}"),
            ("Valor estimado", moeda(s["valor_estimado"])),
            ("Valor final homologado", moeda(s["valor_final_aprovado"])),
        ], largura, 2),
        Paragraph("Descrição", E["h2"]), Paragraph(esc(s["descricao"]), E["normal"]),
        Paragraph("Justificativa do gestor", E["h2"]), Paragraph(esc(s["justificativa"]), E["normal"]),
    ]
    pareceres = [
        ("Parecer da Administração", s.get("justificativa_adm")),
        ("Justificativa da alteração de urgência", s.get("justificativa_urgencia")),
        ("Motivo da solicitação de nova cotação", s.get("motivo_nova_cotacao")),
        ("Parecer de Compras", s.get("justificativa_compras")),
        ("Motivo do cancelamento", s.get("motivo_cancelamento")),
    ]
    for rotulo, texto in pareceres:
        if texto:
            el += [Paragraph(rotulo, E["h2"]), Paragraph(esc(texto), E["normal"])]

    anexos = [a for a in detalhe["anexos"]]
    el.append(Paragraph("Documentos anexados", E["h2"]))
    if anexos:
        el.append(_tabela(
            ["Arquivo", "Origem", "Rodada", "Enviado por", "SHA-256", "Situação"],
            [[a["nome_original"], a["origem"], a["rodada_cotacao"], a["enviado_por_nome"], a["sha256"],
              "Removido" if a["removido_em"] else "Ativo"] for a in anexos],
            [largura * f for f in (0.2, 0.1, 0.08, 0.15, 0.36, 0.11)], fonte_mono={4},
        ))
    else:
        el.append(Paragraph("Nenhum documento anexado.", E["normal"]))

    el.append(Paragraph("Cotações", E["h2"]))
    if detalhe["cotacoes"]:
        el.append(_tabela(
            ["Fornecedor", "CNPJ", "Valor", "Prazo", "Pagamento", "Vencedora"],
            [[c["razao_social"], _cnpj_fmt(c["cnpj"]), moeda(c["valor"]), f"{c['prazo_entrega_dias']} dias",
              c["condicoes_pagamento"] or "—", "Sim" if c["selecionada"] else ""] for c in detalhe["cotacoes"]],
            [largura * f for f in (0.28, 0.2, 0.14, 0.1, 0.18, 0.1)],
        ))
    else:
        el.append(Paragraph("Nenhuma cotação registrada.", E["normal"]))

    el.append(Paragraph("Assinaturas eletrônicas", E["h2"]))
    if detalhe["assinaturas"]:
        el.append(_tabela(
            ["Responsável", "Ação", "Data/hora", "IP", "Hash de autenticidade (HMAC-SHA-256)"],
            [[f"{a['usuario_nome']} ({a['usuario_papel']})", ACAO_ASSINATURA.get(a["acao"], a["acao"]),
              data_hora(a["assinado_em"], tz), a["ip"], a["hash_autenticidade"]] for a in detalhe["assinaturas"]],
            [largura * f for f in (0.2, 0.16, 0.13, 0.1, 0.41)], fonte_mono={4},
        ))
    else:
        el.append(Paragraph("Nenhuma assinatura registrada.", E["normal"]))

    el.append(Paragraph("Histórico de movimentações", E["h2"]))
    el.append(_tabela(
        ["Data/hora", "Responsável", "Movimentação", "Observação"],
        [[data_hora(h["criado_em"], tz), h["autor_nome"] or "Sistema",
          _mov(h), h["observacao"] or ""] for h in detalhe["historico"]],
        [largura * f for f in (0.15, 0.2, 0.25, 0.4)],
    ))
    el += [Spacer(1, 8), Paragraph(
        "As assinaturas eletrônicas registram usuário, data/hora (UTC), IP de origem e o hash do conteúdo "
        "da solicitação no momento da assinatura. A autenticidade pode ser verificada na plataforma.", E["pequeno"])]
    return _montar(el, titulo=f"Dossiê {s['codigo']}", autor=autor, instituicao=instituicao, codigo=codigo, tz=tz), codigo


def _mov(h: dict) -> str:
    if h["acao"] == "mudanca_status":
        return (f"{STATUS_SOLICITACAO.get(h['status_de'], h['status_de'])} → "
                f"{STATUS_SOLICITACAO.get(h['status_para'], h['status_para'])}")
    return {"criacao": "Abertura da solicitação", "alteracao_urgencia": "Alteração de urgência",
            "edicao": "Revisão do conteúdo"}.get(h["acao"], h["acao"])


def _cnpj_fmt(c: str | None) -> str:
    if not c or len(c) != 14:
        return c or "—"
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def relatorio_executivo(painel: dict, filtros_texto: str, *, autor: str, instituicao: str, tz: str) -> tuple[bytes, str]:
    codigo = codigo_verificacao({"tipo": "executivo", "painel": painel, "filtros": filtros_texto})
    largura = A4[0] - 32 * mm
    k = painel["kpis"]
    el = [
        Paragraph("Relatório executivo de solicitações e serviços", E["titulo"]),
        Paragraph(esc(filtros_texto), E["subtitulo"]),
        _kpis([
            ("Solicitações no período", str(k["total"])),
            ("Em andamento", str(k["em_andamento"])),
            ("Homologadas", str(k["aprovadas"])),
            ("Rejeitadas/canceladas", str(k["rejeitadas"])),
        ], largura),
        Spacer(1, 6),
        _kpis([
            ("Valor homologado", moeda(k["valor_aprovado"])),
            ("Economia sobre estimado", moeda(k["economia"])),
            ("Cumprimento de SLA", f"{k['sla_cumprimento']:.0%}" if k["sla_cumprimento"] is not None else "—"),
            ("Ciclo médio (dias)", f"{k['ciclo_medio_dias']:.1f}".replace(".", ",") if k["ciclo_medio_dias"] is not None else "—"),
        ], largura),
        Spacer(1, 6),
        _kpis([
            ("SLA dentro do prazo", str(k["sla_dentro"])),
            ("SLA em alerta (< 24h)", str(k["sla_alerta"])),
            ("SLA estourado", str(k["sla_estourado"])),
            ("Serviços atrasados", str(painel["servicos"]["atrasados"])),
        ], largura),
        Spacer(1, 10),
    ]
    status = painel["por_status"]
    el.append(KeepTogether([_grafico_rosca("Distribuição por status",
                                           [STATUS_SOLICITACAO.get(s["status"], s["status"]) for s in status],
                                           [s["quantidade"] for s in status], largura)]))
    setores = painel["por_setor"]
    el.append(KeepTogether([_grafico_barras_h("Solicitações por setor", [s["setor_nome"] for s in setores],
                                              [s["quantidade"] for s in setores], largura)]))
    el.append(KeepTogether([_grafico_barras_h("Valor homologado por setor (R$)", [s["setor_nome"] for s in setores],
                                              [float(s["valor_aprovado"] or 0) for s in setores], largura,
                                              formato=lambda v: moeda(v), monetario=True)]))
    meses = painel["por_mes"]
    el.append(KeepTogether([_grafico_colunas("Evolução mensal", [m["mes"] for m in meses],
                                             [[m["abertas"] for m in meses], [m["homologadas"] for m in meses]],
                                             ["Abertas", "Homologadas"], largura)]))
    el.append(Paragraph("Detalhamento por setor", E["h2"]))
    el.append(_tabela(
        ["Setor", "Solicitações", "Em andamento", "Homologadas", "Valor homologado", "SLA estourado"],
        [[s["setor_nome"], s["quantidade"], s["em_andamento"], s["aprovadas"], moeda(s["valor_aprovado"]),
          s["sla_estourado"]] for s in setores],
        [largura * f for f in (0.28, 0.13, 0.14, 0.13, 0.19, 0.13)],
    ))
    if painel["top_fornecedores"]:
        el.append(Paragraph("Principais fornecedores homologados", E["h2"]))
        el.append(_tabela(
            ["Fornecedor", "CNPJ", "Contratos", "Valor homologado"],
            [[f["razao_social"], _cnpj_fmt(f["cnpj"]), f["contratos"], moeda(f["valor"])] for f in painel["top_fornecedores"]],
            [largura * f for f in (0.45, 0.22, 0.13, 0.2)],
        ))
    sv = painel["servicos"]
    el.append(Paragraph("Serviços programados no período", E["h2"]))
    el.append(_kpis([("Agendados", str(sv["agendados"])), ("Em andamento", str(sv["em_andamento"])),
                     ("Concluídos", str(sv["concluidos"])), ("Atrasados", str(sv["atrasados"]))], largura))
    return _montar(el, titulo="Relatório executivo", autor=autor, instituicao=instituicao, codigo=codigo, tz=tz), codigo


def relatorio_solicitacoes(linhas: list[dict], filtros_texto: str, *, autor: str, instituicao: str,
                           tz: str) -> tuple[bytes, str]:
    codigo = codigo_verificacao({"tipo": "solicitacoes", "linhas": linhas, "filtros": filtros_texto})
    largura = landscape(A4)[0] - 32 * mm
    total_estimado = sum(Decimal(str(l["valor_estimado"] or 0)) for l in linhas)
    total_aprovado = sum(Decimal(str(l["valor_final_aprovado"] or 0)) for l in linhas)
    el = [
        Paragraph("Relatório de solicitações", E["titulo"]),
        Paragraph(esc(filtros_texto) + f" · {len(linhas)} registro(s)", E["subtitulo"]),
        _tabela(
            ["Código", "Título", "Setor", "Urgência", "Status", "SLA", "Abertura", "Estimado", "Homologado"],
            [[l["codigo"], l["titulo"], l["setor_nome"], URGENCIA.get(l["urgencia"], l["urgencia"]),
              STATUS_SOLICITACAO.get(l["status"], l["status"]), SLA_SITUACAO.get(l["sla_situacao"], l["sla_situacao"]),
              data_hora(l["criado_em"], tz), moeda(l["valor_estimado"]), moeda(l["valor_final_aprovado"])]
             for l in linhas],
            [largura * f for f in (0.1, 0.22, 0.12, 0.07, 0.12, 0.1, 0.09, 0.09, 0.09)],
        ),
        Spacer(1, 6),
        Paragraph(f"<b>Total estimado:</b> {moeda(total_estimado)} &nbsp;&nbsp; <b>Total homologado:</b> {moeda(total_aprovado)}",
                  E["normal"]),
    ]
    return _montar(el, titulo="Relatório de solicitações", autor=autor, instituicao=instituicao, codigo=codigo,
                   tz=tz, paisagem=True), codigo


def relatorio_servicos(linhas: list[dict], filtros_texto: str, *, autor: str, instituicao: str,
                       tz: str) -> tuple[bytes, str]:
    codigo = codigo_verificacao({"tipo": "servicos", "linhas": linhas, "filtros": filtros_texto})
    largura = landscape(A4)[0] - 32 * mm
    el = [
        Paragraph("Agenda de serviços programados", E["titulo"]),
        Paragraph(esc(filtros_texto) + f" · {len(linhas)} registro(s)", E["subtitulo"]),
        _tabela(
            ["Código", "Data", "Horário", "Serviço", "Categoria", "Setor", "Executor / Empresa", "Periodicidade", "Situação"],
            [[l["codigo"], data_hora(l["data_programada"]), f"{l['hora_inicio']:%H:%M}–{l['hora_termino']:%H:%M}",
              l["titulo"], CATEGORIA_SERVICO.get(l["categoria"], l["categoria"]), l["setor_nome"],
              l["responsavel_executor"] + (f" / {l['empresa_terceirizada']}" if l["empresa_terceirizada"] else ""),
              PERIODICIDADE.get(l["periodicidade"], l["periodicidade"]),
              SITUACAO_SERVICO.get(l["situacao"], l["situacao"]) + (" (atrasado)" if l["atrasado"] else "")]
             for l in linhas],
            [largura * f for f in (0.09, 0.07, 0.08, 0.2, 0.11, 0.11, 0.16, 0.08, 0.1)],
        ),
    ]
    return _montar(el, titulo="Serviços programados", autor=autor, instituicao=instituicao, codigo=codigo,
                   tz=tz, paisagem=True), codigo
