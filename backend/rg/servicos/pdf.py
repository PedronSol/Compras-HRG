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
from ..rotulos import (ACAO_ASSINATURA, DECISAO_APROVACAO, NIVEL_APROVACAO, PAPEL, SITUACAO_RECEBIMENTO,
                       SLA_SITUACAO, STATUS_PEDIDO, STATUS_SOLICITACAO, TIPO_SOLICITACAO, URGENCIA)

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
                         subject=titulo, creator="Hospital Rio Grande — Compras RG",
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
def _qtd(v) -> str:
    if v is None:
        return "—"
    d = Decimal(str(v)).normalize()
    texto = f"{d:f}"
    if "." in texto:
        texto = texto.rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def _cnpj_fmt(c: str | None) -> str:
    if not c or len(c) != 14:
        return c or "—"
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def _mov(h: dict) -> str:
    rotulos = STATUS_PEDIDO if h["acao"] == "pedido_status" else STATUS_SOLICITACAO
    if h["acao"] in ("mudanca_status", "pedido_status"):
        prefixo = "Pedido: " if h["acao"] == "pedido_status" else ""
        return f"{prefixo}{rotulos.get(h['status_de'], h['status_de'])} → {rotulos.get(h['status_para'], h['status_para'])}"
    if h["acao"] == "recebimento":
        return f"Recebimento ({SITUACAO_RECEBIMENTO.get(h['status_para'], h['status_para'])})"
    return {"criacao": "Abertura da solicitação", "edicao": "Ajuste do conteúdo",
            "pedido_emitido": "Pedido de compra emitido"}.get(h["acao"], h["acao"])


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
            ("Solicitante", esc(s["solicitante_nome"])),
            ("Comprador responsável", esc(s["comprador_nome"])),
            ("Aberta em", data_hora(s["criado_em"], tz)),
            ("Prazo de atendimento", f"{data_hora(s['sla_prazo_limite'], tz)} — "
                                     f"{esc(SLA_SITUACAO.get(s['sla_situacao'], s['sla_situacao']))}"),
            ("Valor estimado", moeda(s["valor_estimado"])),
            ("Valor contratado", moeda(s["valor_final"])),
            ("Fornecedor", esc(s["fornecedor_nome"])),
            ("Pedido de compra", esc(s["pedido_codigo"])),
        ], largura, 2),
    ]
    if s.get("descricao"):
        el += [Paragraph("Descrição", E["h2"]), Paragraph(esc(s["descricao"]), E["normal"])]
    el += [Paragraph("Justificativa", E["h2"]), Paragraph(esc(s["justificativa"]), E["normal"])]
    for rotulo, texto in (("Justificativa da escolha do fornecedor", s.get("justificativa_escolha")),
                          ("Motivo da devolução", s.get("motivo_devolucao")),
                          ("Motivo da reprovação", s.get("motivo_reprovacao")),
                          ("Motivo do cancelamento", s.get("motivo_cancelamento"))):
        if texto:
            el += [Paragraph(rotulo, E["h2"]), Paragraph(esc(texto), E["normal"])]

    el.append(Paragraph("Itens solicitados", E["h2"]))
    el.append(_tabela(["#", "Descrição", "Un.", "Qtd.", "Unitário estimado", "Total estimado"],
                      [[i + 1, it["descricao"], it["unidade"], _qtd(it["quantidade"]), moeda(it["valor_unitario_estimado"]),
                        moeda(it["total_estimado"])] for i, it in enumerate(detalhe["itens"])],
                      [largura * f for f in (0.05, 0.45, 0.07, 0.1, 0.16, 0.17)]))

    el.append(Paragraph("Aprovações", E["h2"]))
    if detalhe["aprovacoes"]:
        el.append(_tabela(["Data/hora", "Nível", "Decisão", "Responsável", "Parecer"],
                          [[data_hora(a["criado_em"], tz), NIVEL_APROVACAO.get(a["nivel"], a["nivel"]),
                            DECISAO_APROVACAO.get(a["decisao"], a["decisao"]), a["usuario_nome"], a["parecer"] or ""]
                           for a in detalhe["aprovacoes"]],
                          [largura * f for f in (0.15, 0.15, 0.12, 0.2, 0.38)]))
    else:
        el.append(Paragraph("Nenhuma decisão registrada.", E["normal"]))

    el.append(Paragraph("Propostas de fornecedores", E["h2"]))
    if detalhe["cotacoes"]:
        el.append(_tabela(["Fornecedor", "CNPJ", "Valor total", "Frete", "Prazo", "Pagamento", "Vencedora"],
                          [[c["nome_fantasia"] or c["razao_social"], _cnpj_fmt(c["cnpj"]), moeda(c["valor_total"]),
                            moeda(c["frete"]), f"{c['prazo_entrega_dias']} dias", c["condicoes_pagamento"] or "—",
                            "Sim" if c["selecionada"] else ""] for c in detalhe["cotacoes"]],
                          [largura * f for f in (0.24, 0.18, 0.13, 0.1, 0.09, 0.16, 0.1)]))
    else:
        el.append(Paragraph("Nenhuma proposta registrada.", E["normal"]))

    if detalhe["pedidos"]:
        el.append(Paragraph("Pedidos de compra", E["h2"]))
        el.append(_tabela(["Pedido", "Fornecedor", "Status", "Valor", "Previsão", "Recebido"],
                          [[p["codigo"], p["fornecedor_fantasia"] or p["fornecedor_nome"], STATUS_PEDIDO.get(p["status"]),
                            moeda(p["valor_total"]), data_hora(p["data_prevista_entrega"]), f"{p['percentual_recebido']}%"]
                           for p in detalhe["pedidos"]],
                          [largura * f for f in (0.14, 0.3, 0.18, 0.14, 0.12, 0.12)]))
    if detalhe["recebimentos"]:
        el.append(Paragraph("Recebimentos", E["h2"]))
        el.append(_tabela(["Código", "Data", "Nota fiscal", "Conferente", "Situação", "Observações"],
                          [[r["codigo"], data_hora(r["recebido_em"], tz), r["nota_fiscal"], r["recebido_por_nome"],
                            SITUACAO_RECEBIMENTO.get(r["situacao"]), r["observacoes"] or ""] for r in detalhe["recebimentos"]],
                          [largura * f for f in (0.12, 0.14, 0.12, 0.18, 0.14, 0.3)]))

    el.append(Paragraph("Documentos anexados", E["h2"]))
    if detalhe["anexos"]:
        el.append(_tabela(["Arquivo", "Tipo", "Enviado por", "SHA-256", "Situação"],
                          [[a["nome_original"], a["tipo_documento"], a["enviado_por_nome"], a["sha256"],
                            "Removido" if a["removido_em"] else "Ativo"] for a in detalhe["anexos"]],
                          [largura * f for f in (0.24, 0.12, 0.16, 0.36, 0.12)], fonte_mono={3}))
    else:
        el.append(Paragraph("Nenhum documento anexado.", E["normal"]))

    el.append(Paragraph("Assinaturas eletrônicas", E["h2"]))
    if detalhe["assinaturas"]:
        el.append(_tabela(["Responsável", "Ação", "Data/hora", "IP", "Hash de autenticidade (HMAC-SHA-256)"],
                          [[f"{a['usuario_nome']} ({PAPEL.get(a['papel'], a['papel'])})",
                            ACAO_ASSINATURA.get(a["acao"], a["acao"]), data_hora(a["assinado_em"], tz), a["ip"],
                            a["hash_autenticidade"]] for a in detalhe["assinaturas"]],
                          [largura * f for f in (0.2, 0.17, 0.13, 0.09, 0.41)], fonte_mono={4}))
    el.append(Paragraph("Histórico de movimentações", E["h2"]))
    el.append(_tabela(["Data/hora", "Responsável", "Movimentação", "Observação"],
                      [[data_hora(h["criado_em"], tz), h["autor_nome"] or "Sistema", _mov(h), h["observacao"] or ""]
                       for h in detalhe["historico"]],
                      [largura * f for f in (0.15, 0.2, 0.27, 0.38)]))
    el += [Spacer(1, 8), Paragraph(
        "As assinaturas eletrônicas registram usuário, perfil, data/hora (UTC), IP de origem e o hash do conteúdo no "
        "momento da assinatura. A autenticidade pode ser verificada no sistema.", E["pequeno"])]
    return _montar(el, titulo=f"Dossiê {s['codigo']}", autor=autor, instituicao=instituicao, codigo=codigo, tz=tz), codigo


def documento_pedido(dados: dict, *, autor: str, instituicao: str, tz: str) -> tuple[bytes, str]:
    """Pedido de compra oficial para envio ao fornecedor."""
    p, f = dados["pedido"], dados["fornecedor"]
    codigo = codigo_verificacao({"tipo": "pedido", "pedido": p, "itens": dados["itens"]})
    largura = A4[0] - 32 * mm
    el = [
        Paragraph(f"Pedido de compra {esc(p['codigo'])}", E["titulo"]),
        Paragraph(f"Referente à solicitação {esc(p['solicitacao_codigo'])} · {esc(p['solicitacao_titulo'])}", E["subtitulo"]),
        _pares([
            ("Fornecedor", f"<b>{esc(f['razao_social'])}</b>"),
            ("CNPJ", esc(_cnpj_fmt(f["cnpj"]))),
            ("Contato", esc(" · ".join(x for x in (f.get("contato"), f.get("email"), f.get("telefone")) if x) or "—")),
            ("Cidade", esc(f"{f.get('cidade') or '—'}/{f.get('uf') or '—'}")),
            ("Data de emissão", data_hora(p["criado_em"], tz)),
            ("Status", esc(STATUS_PEDIDO.get(p["status"], p["status"]))),
            ("Condições de pagamento", esc(p["condicoes_pagamento"])),
            ("Prazo de entrega", f"{p['prazo_entrega_dias']} dias" + (
                f" · previsão {data_hora(p['data_prevista_entrega'])}" if p.get("data_prevista_entrega") else "")),
            ("Local de entrega", esc(p["local_entrega"] or "Almoxarifado central — Hospital Rio Grande")),
            ("Setor requisitante", esc(p["setor_nome"])),
            ("Comprador responsável", esc(p["comprador_nome"])),
        ], largura, 2),
        Paragraph("Itens", E["h2"]),
        _tabela(["#", "Descrição", "Marca", "Un.", "Qtd.", "Unitário", "Total"],
                [[i + 1, it["descricao"], it["marca"] or "—", it["unidade"], _qtd(it["quantidade"]),
                  moeda(it["valor_unitario"]), moeda(it["total"])] for i, it in enumerate(dados["itens"])],
                [largura * x for x in (0.05, 0.38, 0.13, 0.07, 0.09, 0.14, 0.14)]),
        Spacer(1, 6),
        _pares([("Subtotal dos itens", moeda(p["valor_itens"])), ("Frete", moeda(p["frete"])),
                ("Desconto", moeda(p["desconto"])), ("Valor total do pedido", f"<b>{moeda(p['valor_total'])}</b>")],
               largura, 4),
    ]
    if p.get("observacoes"):
        el += [Paragraph("Observações", E["h2"]), Paragraph(esc(p["observacoes"]), E["normal"])]
    if dados["aprovacoes"]:
        el.append(Paragraph("Aprovações", E["h2"]))
        el.append(_tabela(["Data/hora", "Nível", "Decisão", "Responsável"],
                          [[data_hora(a["criado_em"], tz), NIVEL_APROVACAO.get(a["nivel"]), DECISAO_APROVACAO.get(a["decisao"]),
                            a["usuario_nome"]] for a in dados["aprovacoes"]],
                          [largura * x for x in (0.2, 0.25, 0.2, 0.35)]))
    el += [Spacer(1, 10), Paragraph(
        "Faturar em nome do Hospital Rio Grande. Informe o número deste pedido na nota fiscal. A entrega será conferida "
        "pelo setor de Recebimento; itens em desacordo com o pedido serão recusados.", E["pequeno"])]
    return _montar(el, titulo=f"Pedido de compra {p['codigo']}", autor=autor, instituicao=instituicao, codigo=codigo,
                   tz=tz), codigo


def _num(v, casas=1) -> str:
    return "—" if v is None else f"{v:.{casas}f}".replace(".", ",")


def relatorio_executivo(painel: dict, filtros_texto: str, *, autor: str, instituicao: str, tz: str) -> tuple[bytes, str]:
    codigo = codigo_verificacao({"tipo": "executivo", "painel": painel, "filtros": filtros_texto})
    largura = A4[0] - 32 * mm
    k = painel["kpis"]
    el = [
        Paragraph("Relatório executivo de Compras", E["titulo"]),
        Paragraph(esc(filtros_texto), E["subtitulo"]),
        _kpis([("Valor contratado", moeda(k["valor_contratado"])), ("Pedidos emitidos", str(k["pedidos"])),
               ("Economia sobre o estimado", moeda(k["economia"])), ("Ticket médio", moeda(k["ticket_medio"]))], largura),
        Spacer(1, 6),
        _kpis([("Solicitações no período", str(k["solicitacoes"])), ("Em aberto hoje", str(k["abertas"])),
               ("Prazo de atendimento cumprido", f"{k['sla_cumprimento']:.0%}" if k["sla_cumprimento"] is not None else "—"),
               ("Entregas no prazo", f"{k['pontualidade_entregas']:.0f}%" if k["pontualidade_entregas"] is not None else "—")],
              largura),
        Spacer(1, 6),
        _kpis([("Tempo médio de aprovação (dias)", _num(k["tempo_aprovacao_dias"])),
               ("Tempo médio de cotação (dias)", _num(k["tempo_cotacao_dias"])),
               ("Abertura até pedido (dias)", _num(k["tempo_ate_pedido_dias"])),
               ("Lead time total (dias)", _num(k["lead_time_dias"]))], largura),
        Spacer(1, 10),
    ]
    funil = painel["funil"]
    el.append(KeepTogether([_grafico_barras_h("Solicitações em andamento por etapa", [f["rotulo"] for f in funil],
                                              [f["quantidade"] for f in funil], largura)]))
    setores = painel["por_setor"]
    el.append(KeepTogether([_grafico_barras_h("Valor contratado por setor (R$)", [s["setor_nome"] for s in setores[:10]],
                                              [float(s["valor"] or 0) for s in setores[:10]], largura,
                                              formato=lambda v: moeda(v), monetario=True)]))
    categorias = painel["por_categoria"]
    el.append(KeepTogether([_grafico_barras_h("Valor contratado por categoria (R$)", [c["categoria"] for c in categorias[:10]],
                                              [float(c["valor"] or 0) for c in categorias[:10]], largura,
                                              formato=lambda v: moeda(v), monetario=True)]))
    meses = painel["por_mes"][-12:]
    el.append(KeepTogether([_grafico_colunas("Evolução mensal", [m["mes"][:2] + "/" + m["mes"][-2:] for m in meses],
                                             [[m["solicitacoes"] for m in meses], [m["pedidos"] for m in meses]],
                                             ["Solicitações", "Pedidos"], largura)]))
    if painel["top_fornecedores"]:
        el.append(Paragraph("Principais fornecedores", E["h2"]))
        el.append(_tabela(["Fornecedor", "CNPJ", "Pedidos", "Valor contratado"],
                          [[f["fornecedor"], _cnpj_fmt(f["cnpj"]), f["pedidos"], moeda(f["valor"])]
                           for f in painel["top_fornecedores"]],
                          [largura * x for x in (0.45, 0.22, 0.13, 0.2)]))
    if setores:
        el.append(Paragraph("Detalhamento por setor", E["h2"]))
        el.append(_tabela(["Setor", "Pedidos", "Valor contratado"],
                          [[s["setor_nome"], s["pedidos"], moeda(s["valor"])] for s in setores],
                          [largura * x for x in (0.6, 0.15, 0.25)]))
    return _montar(el, titulo="Relatório executivo de Compras", autor=autor, instituicao=instituicao, codigo=codigo,
                   tz=tz), codigo


def relatorio_solicitacoes(linhas: list[dict], filtros_texto: str, *, autor: str, instituicao: str,
                           tz: str) -> tuple[bytes, str]:
    codigo = codigo_verificacao({"tipo": "solicitacoes", "linhas": linhas, "filtros": filtros_texto})
    largura = landscape(A4)[0] - 32 * mm
    total_estimado = sum(Decimal(str(l["valor_estimado"] or 0)) for l in linhas)
    total_contratado = sum(Decimal(str(l["valor_final"] or 0)) for l in linhas)
    el = [
        Paragraph("Relatório de solicitações de compra", E["titulo"]),
        Paragraph(esc(filtros_texto) + f" · {len(linhas)} registro(s)", E["subtitulo"]),
        _tabela(["Código", "Título", "Setor", "Urgência", "Status", "Prazo", "Abertura", "Estimado", "Contratado"],
                [[l["codigo"], l["titulo"], l["setor_nome"], URGENCIA.get(l["urgencia"], l["urgencia"]),
                  STATUS_SOLICITACAO.get(l["status"], l["status"]), SLA_SITUACAO.get(l["sla_situacao"], l["sla_situacao"]),
                  data_hora(l["criado_em"], tz), moeda(l["valor_estimado"]), moeda(l["valor_final"])] for l in linhas],
                [largura * x for x in (0.09, 0.24, 0.13, 0.07, 0.12, 0.1, 0.09, 0.08, 0.08)]),
        Spacer(1, 6),
        Paragraph(f"<b>Total estimado:</b> {moeda(total_estimado)} &nbsp;&nbsp; <b>Total contratado:</b> "
                  f"{moeda(total_contratado)}", E["normal"]),
    ]
    return _montar(el, titulo="Relatório de solicitações", autor=autor, instituicao=instituicao, codigo=codigo,
                   tz=tz, paisagem=True), codigo
