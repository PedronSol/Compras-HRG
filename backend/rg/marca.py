"""Geometria vetorial oficial da marca Hospital Rio Grande (fonte única).

Usada para gerar os SVG/PNG do frontend (scripts/gerar_marca.py) e para
desenhar o logotipo nos relatórios PDF, sem fundo e em qualquer cor.
Cada forma é uma lista de subcaminhos: ("preencher" | "vazar", path_svg).
"""
from __future__ import annotations

import re

COR_PRIMARIA = "#2E5C88"
COR_DESTAQUE = "#8EB7E5"

# Símbolo (viewBox 145 167 1310 1220)
MARCA_VIEWBOX = (145.0, 167.0, 1310.0, 1220.0)
MARCA = [
    ("preencher", "M800,167 C1337,167 1455,277 1455,777 C1455,1277 1337,1387 800,1387 "
                  "C263,1387 145,1277 145,777 C145,277 263,167 800,167 Z"),
    ("vazar", "M795,296 C890,296 1335,695 1335,780 C1335,865 895,1258 800,1258 "
              "C705,1258 263,860 263,775 C263,690 700,296 795,296 Z"),
    ("preencher", "M783,412 H816 C820.4,412 824,415.6 824,420 V627 C824,696.6 880.4,753 950,753 H1157 "
                  "C1161.4,753 1165,756.6 1165,761 V793 C1165,797.4 1161.4,801 1157,801 H950 "
                  "C880.4,801 824,857.4 824,927 V1134 C824,1138.4 820.4,1142 816,1142 H783 "
                  "C778.6,1142 775,1138.4 775,1134 V927 C775,857.4 718.6,801 649,801 H443 "
                  "C438.6,801 435,797.4 435,793 V761 C435,756.6 438.6,753 443,753 H649 "
                  "C718.6,753 775,696.6 775,627 V420 C775,415.6 778.6,412 783,412 Z"),
]

_R = [
    ("preencher", "M149,207 H240 C265,207 276,220 276,243 C276,266 263,277 237,279 L281,327 H256 "
                  "L210,279 H182 C172,279 165,286 165,296 V327 H149 Z"),
    ("vazar", "M165,226 H244 C255,226 260,232 260,243 C260,254 255,261 244,261 H183 "
              "C173,261 165,254 165,244 Z"),
]


def _deslocar(path: str, dx: float) -> str:
    """Translada horizontalmente um path composto apenas por comandos absolutos."""
    saida, cmd = [], ""
    for token in re.findall(r"[A-Za-z]|-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?|-?\d+(?:\.\d+)?", path):
        if token.isalpha():
            cmd = token
            saida.append(token)
        elif "," in token:
            x, y = token.split(",")
            saida.append(f"{float(x) + dx:g},{y}")
        elif cmd == "H":
            saida.append(f"{float(token) + dx:g}")
        else:
            saida.append(token)
    return " ".join(saida)


# Logotipo horizontal (viewBox 140 140 1255 195): "HOSPITAL" + "RIO GRANDE" com o símbolo no "O"
LOGO_VIEWBOX = (140.0, 140.0, 1255.0, 195.0)
LOGO_LETRAS = (
    _R
    + [("preencher", "M305,207 H321 V327 H305 Z")]  # I
    + [("preencher", "M665,241 H646 C638,228 622,222 598,222 C565,222 547,238 547,266 C547,294 565,311 598,311 "
                     "C628,311 646,299 652,280 V278 H593 V260 H668 V327 H652 V313 C640,324 621,329 598,329 "
                     "C553,329 529,306 529,266 C529,226 553,204 598,204 C634,204 657,216 665,241 Z")]  # G
    + [(modo, _deslocar(p, 543)) for modo, p in _R]  # R
    + [("preencher", "M890,207 H924 L975,327 H955 L942,298 H871 L859,327 H838 Z"),
       ("vazar", "M907,213 L935,281 H879 Z")]  # A
    + [("preencher", "M990,207 H1006 L1099,301 V207 H1115 V327 H1099 L1006,233 V327 H990 Z")]  # N
    + [("preencher", "M1138,207 H1196 C1234,207 1253,228 1253,267 C1253,306 1234,327 1196,327 H1138 Z"),
       ("vazar", "M1154,226 H1196 C1223,226 1237,240 1237,267 C1237,294 1223,308 1196,308 H1154 Z")]  # D
    + [("preencher", "M1277,207 H1385 V225 H1293 V258 H1380 V275 H1293 V309 H1385 V327 H1277 Z")]  # E
)
# Posição do símbolo substituindo a letra "O"
LOGO_MARCA_CAIXA = (340.0, 205.0, 132.0)  # x, y, largura
LOGO_TEXTO_SUPERIOR = {"texto": "HOSPITAL", "x": 147.0, "y": 177.0, "tamanho": 42.0, "largura": 521.0}


# ---------------------------------------------------------------------------
# Interpretação de paths (somente M, L, H, V, C, Z absolutos)
# ---------------------------------------------------------------------------
def interpretar(path: str) -> list[tuple[str, list[float]]]:
    tokens = re.findall(r"[MLHVCZ]|-?\d+(?:\.\d+)?", path.replace(",", " "))
    ops: list[tuple[str, list[float]]] = []
    i, cmd = 0, ""
    aridade = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Z": 0}
    x = y = 0.0
    while i < len(tokens):
        if tokens[i].isalpha():
            cmd = tokens[i]
            i += 1
            if cmd == "Z":
                ops.append(("Z", []))
                continue
        n = aridade[cmd]
        valores = [float(v) for v in tokens[i:i + n]]
        i += n
        if cmd == "H":
            x = valores[0]
            ops.append(("L", [x, y]))
        elif cmd == "V":
            y = valores[0]
            ops.append(("L", [x, y]))
        else:
            x, y = valores[-2], valores[-1]
            ops.append((cmd, valores))
            if cmd == "M":
                cmd = "L"
    return ops


def achatar(path: str, passos: int = 24) -> list[tuple[float, float]]:
    """Converte o path em polígono (aproxima curvas de Bézier)."""
    pontos: list[tuple[float, float]] = []
    atual = (0.0, 0.0)
    for op, v in interpretar(path):
        if op in ("M", "L"):
            atual = (v[0], v[1])
            pontos.append(atual)
        elif op == "C":
            x0, y0 = atual
            x1, y1, x2, y2, x3, y3 = v
            for k in range(1, passos + 1):
                t = k / passos
                a = (1 - t) ** 3
                b = 3 * (1 - t) ** 2 * t
                c = 3 * (1 - t) * t ** 2
                d = t ** 3
                pontos.append((a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3))
            atual = (x3, y3)
    return pontos


# ---------------------------------------------------------------------------
# Saídas
# ---------------------------------------------------------------------------
def svg_marca(cor: str = COR_DESTAQUE, titulo: str = "Hospital Rio Grande") -> str:
    x, y, w, h = MARCA_VIEWBOX
    d = " ".join(p for _, p in MARCA[:2])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:g} {y:g} {w:g} {h:g}" role="img" aria-label="{titulo}">'
        f"<title>{titulo}</title>"
        f'<path fill="{cor}" fill-rule="evenodd" d="{d}"/>'
        f'<path fill="{cor}" d="{MARCA[2][1]}"/></svg>'
    )


def svg_logo(cor: str = COR_DESTAQUE, titulo: str = "Hospital Rio Grande") -> str:
    x, y, w, h = LOGO_VIEWBOX
    mx, my, mw = LOGO_MARCA_CAIXA
    escala = mw / MARCA_VIEWBOX[2]
    t = LOGO_TEXTO_SUPERIOR
    letras = []
    grupo: list[str] = []
    for modo, p in LOGO_LETRAS:
        if modo == "preencher" and grupo:
            letras.append(" ".join(grupo))
            grupo = []
        grupo.append(p)
    letras.append(" ".join(grupo))
    caminhos = "".join(f'<path fill-rule="evenodd" d="{d}"/>' for d in letras)
    marca = (f'<g transform="translate({mx:g} {my:g}) scale({escala:.6f}) translate({-MARCA_VIEWBOX[0]:g} {-MARCA_VIEWBOX[1]:g})">'
             f'<path fill-rule="evenodd" d="{MARCA[0][1]} {MARCA[1][1]}"/><path d="{MARCA[2][1]}"/></g>')
    texto = (f'<text x="{t["x"]:g}" y="{t["y"]:g}" font-family="Georgia, \'Times New Roman\', serif" '
             f'font-size="{t["tamanho"]:g}" textLength="{t["largura"]:g}" lengthAdjust="spacing">{t["texto"]}</text>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x:g} {y:g} {w:g} {h:g}" role="img" aria-label="{titulo}">'
        f'<title>{titulo}</title><g fill="{cor}">{texto}{caminhos}{marca}</g></svg>'
    )


def desenhar_pdf(canvas, x: float, y: float, largura: float, cor, *, completo: bool = True) -> float:
    """Desenha o logotipo (completo) ou só o símbolo no canvas ReportLab.

    (x, y) é o canto inferior esquerdo. Retorna a altura desenhada.
    """
    from reportlab.lib.colors import HexColor

    vx, vy, vw, vh = LOGO_VIEWBOX if completo else MARCA_VIEWBOX
    escala = largura / vw
    altura = vh * escala
    cor = HexColor(cor) if isinstance(cor, str) else cor

    def _path(subcaminhos, transformar):
        p = canvas.beginPath()
        for _, d in subcaminhos:
            for op, v in interpretar(d):
                if op == "M":
                    p.moveTo(*transformar(v[0], v[1]))
                elif op == "L":
                    p.lineTo(*transformar(v[0], v[1]))
                elif op == "C":
                    p.curveTo(*transformar(v[0], v[1]), *transformar(v[2], v[3]), *transformar(v[4], v[5]))
                elif op == "Z":
                    p.close()
        return p

    def base(px, py):
        return x + (px - vx) * escala, y + altura - (py - vy) * escala

    canvas.saveState()
    canvas.setFillColor(cor)
    if completo:
        # letras (cada letra com seus vazados, regra par-ímpar)
        grupos, atual = [], []
        for item in LOGO_LETRAS:
            if item[0] == "preencher" and atual:
                grupos.append(atual)
                atual = []
            atual.append(item)
        grupos.append(atual)
        for g in grupos:
            canvas.drawPath(_path(g, base), stroke=0, fill=1, fillMode=0)
        mx, my, mw = LOGO_MARCA_CAIXA
        esc_m = mw / MARCA_VIEWBOX[2]

        def marca_pt(px, py):
            return base(mx + (px - MARCA_VIEWBOX[0]) * esc_m, my + (py - MARCA_VIEWBOX[1]) * esc_m)
        canvas.drawPath(_path(MARCA[:2], marca_pt), stroke=0, fill=1, fillMode=0)
        canvas.drawPath(_path(MARCA[2:], marca_pt), stroke=0, fill=1)
        t = LOGO_TEXTO_SUPERIOR
        tamanho = t["tamanho"] * escala
        tx, ty = base(t["x"], t["y"])
        largura_txt = canvas.stringWidth(t["texto"], "Times-Roman", tamanho)
        espaco = (t["largura"] * escala - largura_txt) / (len(t["texto"]) - 1)
        texto = canvas.beginText(tx, ty)
        texto.setFont("Times-Roman", tamanho)
        texto.setCharSpace(espaco)
        texto.textOut(t["texto"])
        canvas.drawText(texto)
    else:
        canvas.drawPath(_path(MARCA[:2], base), stroke=0, fill=1, fillMode=0)
        canvas.drawPath(_path(MARCA[2:], base), stroke=0, fill=1)
    canvas.restoreState()
    return altura
