"""Gera os arquivos de marca do frontend a partir da geometria oficial (backend/rg/marca.py).

Uso: python scripts/gerar_marca.py
Saída: frontend/assets/marca/*.svg e frontend/assets/icones/*.png (PWA)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from rg import marca  # noqa: E402

DESTINO_MARCA = RAIZ / "frontend" / "assets" / "marca"
DESTINO_ICONES = RAIZ / "frontend" / "assets" / "icones"


def mascara_marca(tamanho: int, ocupacao: float, supersample: int = 4) -> Image.Image:
    """Máscara (L) do símbolo centralizado ocupando `ocupacao` do lado do quadro."""
    lado = tamanho * supersample
    img = Image.new("L", (lado, lado), 0)
    desenho = ImageDraw.Draw(img)
    vx, vy, vw, vh = marca.MARCA_VIEWBOX
    escala = lado * ocupacao / max(vw, vh)
    dx = (lado - vw * escala) / 2
    dy = (lado - vh * escala) / 2
    for modo, d in marca.MARCA:
        pontos = [(dx + (x - vx) * escala, dy + (y - vy) * escala) for x, y in marca.achatar(d, 48)]
        desenho.polygon(pontos, fill=255 if modo == "preencher" else 0)
    return img.resize((tamanho, tamanho), Image.LANCZOS)


def icone(tamanho: int, *, fundo: str | None, cor: str, ocupacao: float, raio: float = 0.0) -> Image.Image:
    ss = 4
    base = Image.new("RGBA", (tamanho * ss, tamanho * ss), (0, 0, 0, 0))
    if fundo:
        d = ImageDraw.Draw(base)
        d.rounded_rectangle([0, 0, tamanho * ss - 1, tamanho * ss - 1], radius=int(tamanho * ss * raio), fill=fundo)
    base = base.resize((tamanho, tamanho), Image.LANCZOS)
    camada = Image.new("RGBA", (tamanho, tamanho), cor)
    base.paste(camada, (0, 0), mascara_marca(tamanho, ocupacao, ss))
    return base


def main() -> None:
    DESTINO_MARCA.mkdir(parents=True, exist_ok=True)
    DESTINO_ICONES.mkdir(parents=True, exist_ok=True)
    arquivos = {
        "logo-rg-hospital.svg": marca.svg_logo(marca.COR_DESTAQUE),
        "logo-rg-hospital-primaria.svg": marca.svg_logo(marca.COR_PRIMARIA),
        "logo-rg-hospital-branca.svg": marca.svg_logo("#FFFFFF"),
        "simbolo-rg.svg": marca.svg_marca(marca.COR_DESTAQUE),
        "simbolo-rg-primaria.svg": marca.svg_marca(marca.COR_PRIMARIA),
        "simbolo-rg-branca.svg": marca.svg_marca("#FFFFFF"),
    }
    for nome, conteudo in arquivos.items():
        (DESTINO_MARCA / nome).write_text(conteudo, encoding="utf-8")
    (RAIZ / "frontend" / "favicon.svg").write_text(marca.svg_marca(marca.COR_PRIMARIA), encoding="utf-8")

    icone(192, fundo=marca.COR_PRIMARIA, cor="#FFFFFF", ocupacao=0.66, raio=0.22).save(DESTINO_ICONES / "icone-192.png")
    icone(512, fundo=marca.COR_PRIMARIA, cor="#FFFFFF", ocupacao=0.66, raio=0.22).save(DESTINO_ICONES / "icone-512.png")
    icone(512, fundo=marca.COR_PRIMARIA, cor="#FFFFFF", ocupacao=0.52).save(DESTINO_ICONES / "icone-maskable-512.png")
    icone(180, fundo=marca.COR_PRIMARIA, cor="#FFFFFF", ocupacao=0.62).save(DESTINO_ICONES / "apple-touch-icon.png")
    icone(512, fundo=None, cor=marca.COR_DESTAQUE, ocupacao=0.96).save(DESTINO_MARCA / "simbolo-rg-512.png")
    icone(48, fundo=None, cor=marca.COR_PRIMARIA, ocupacao=0.96).save(RAIZ / "frontend" / "favicon-48.png")
    print("Marca gerada em", DESTINO_MARCA, "e", DESTINO_ICONES)


if __name__ == "__main__":
    main()
