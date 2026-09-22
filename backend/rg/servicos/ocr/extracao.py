"""Extração de texto de PDFs, imagens e documentos Office.

Ordem de preferência:
  1. Camada de texto do PDF (pypdfium2) — documentos digitais, sem perda.
  2. OCR Tesseract (se o binário estiver instalado, idioma 'por').
  3. OCR RapidOCR (ONNX, sem dependências externas).
"""
from __future__ import annotations

import io
import logging
import re
import shutil
import threading
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

from PIL import Image, ImageOps

log = logging.getLogger("rg.ocr")

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MIME_IMAGENS = {"image/png", "image/jpeg", "image/webp", "image/tiff"}


class MotorIndisponivel(RuntimeError):
    pass


@dataclass
class ResultadoTexto:
    texto: str
    motor: str
    paginas: int


class _MotorOCR:
    """Seleciona e mantém o motor de OCR (inicialização preguiçosa e thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rapid = None
        self._tesseract: str | None = None
        self._tesseract_idioma = "por"
        self._configurado = False

    def configurar(self, tesseract_cmd: str = "") -> None:
        cmd = tesseract_cmd or shutil.which("tesseract")
        if cmd:
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = cmd
                idiomas = set(pytesseract.get_languages(config=""))
                self._tesseract_idioma = "por" if "por" in idiomas else "eng"
                self._tesseract = cmd
            except Exception as exc:  # binário inválido
                log.warning("Tesseract indisponível (%s); usando RapidOCR", exc)
                self._tesseract = None
        self._configurado = True

    @property
    def nome(self) -> str:
        if not self._configurado:
            self.configurar()
        return f"tesseract-{self._tesseract_idioma}" if self._tesseract else "rapidocr-onnx"

    def reconhecer(self, imagem: Image.Image) -> str:
        if not self._configurado:
            self.configurar()
        imagem = _preprocessar(imagem)
        if self._tesseract:
            import pytesseract
            return pytesseract.image_to_string(imagem, lang=self._tesseract_idioma, config="--psm 6")
        return self._rapidocr(imagem)

    def _rapidocr(self, imagem: Image.Image) -> str:
        import numpy as np
        with self._lock:
            if self._rapid is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                except ImportError as exc:
                    raise MotorIndisponivel("Nenhum motor de OCR instalado (Tesseract ou RapidOCR)") from exc
                self._rapid = RapidOCR()
            resultado, _ = self._rapid(np.array(imagem.convert("RGB")))
        return _montar_linhas(resultado or [])


motor = _MotorOCR()


def _preprocessar(imagem: Image.Image) -> Image.Image:
    imagem = ImageOps.exif_transpose(imagem)
    if imagem.mode not in ("RGB", "L"):
        imagem = imagem.convert("RGB")
    menor = min(imagem.size)
    if menor < 900:  # amplia digitalizações pequenas para melhorar o reconhecimento
        fator = 900 / menor
        imagem = imagem.resize((int(imagem.width * fator), int(imagem.height * fator)), Image.LANCZOS)
    maior = max(imagem.size)
    if maior > 4000:
        fator = 4000 / maior
        imagem = imagem.resize((int(imagem.width * fator), int(imagem.height * fator)), Image.LANCZOS)
    return ImageOps.autocontrast(imagem.convert("L")).convert("RGB")


def _montar_linhas(caixas: list) -> str:
    """Reconstrói linhas de texto a partir das caixas do RapidOCR (agrupamento por eixo Y)."""
    itens = []
    for caixa, texto, _conf in caixas:
        ys = [p[1] for p in caixa]
        xs = [p[0] for p in caixa]
        itens.append((min(ys), max(ys), min(xs), texto))
    itens.sort(key=lambda i: (i[0] + i[1]) / 2)
    linhas: list[list[tuple]] = []
    for item in itens:
        centro = (item[0] + item[1]) / 2
        altura = item[1] - item[0]
        if linhas:
            ultima = linhas[-1]
            ref_centro = sum((i[0] + i[1]) / 2 for i in ultima) / len(ultima)
            if abs(centro - ref_centro) <= max(altura * 0.5, 6):
                ultima.append(item)
                continue
        linhas.append([item])
    return "\n".join("  ".join(i[3] for i in sorted(linha, key=lambda i: i[2])) for linha in linhas)


def extrair_texto(dados: bytes, mime: str, max_paginas: int = 8) -> ResultadoTexto:
    if mime == "application/pdf":
        return _extrair_pdf(dados, max_paginas)
    if mime in MIME_IMAGENS:
        with Image.open(io.BytesIO(dados)) as img:
            paginas = []
            for indice in range(min(getattr(img, "n_frames", 1), max_paginas)):
                img.seek(indice)
                paginas.append(motor.reconhecer(img.copy()))
        return ResultadoTexto("\n\f\n".join(paginas), motor.nome, len(paginas))
    if mime == MIME_DOCX:
        return ResultadoTexto(_texto_docx(dados), "office-xml", 1)
    if mime == MIME_XLSX:
        return ResultadoTexto(_texto_xlsx(dados), "office-xml", 1)
    raise MotorIndisponivel(f"Formato sem suporte a extração: {mime}")


def _extrair_pdf(dados: bytes, max_paginas: int) -> ResultadoTexto:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(dados)
    try:
        total = min(len(pdf), max_paginas)
        textos: list[str] = []
        usou_ocr = False
        for i in range(total):
            pagina = pdf[i]
            try:
                pagina_texto = pagina.get_textpage()
                texto = pagina_texto.get_text_bounded() or ""
                pagina_texto.close()
                if len(re.sub(r"\s", "", texto)) < 40:  # página digitalizada: aplica OCR
                    bitmap = pagina.render(scale=220 / 72)
                    texto = motor.reconhecer(bitmap.to_pil())
                    usou_ocr = True
                textos.append(texto)
            finally:
                pagina.close()
    finally:
        pdf.close()
    return ResultadoTexto("\n\f\n".join(textos), ("pdf-texto+" + motor.nome) if usou_ocr else "pdf-texto", total)


_NS_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_NS_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _texto_docx(dados: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        raiz = ElementTree.fromstring(z.read("word/document.xml"))
    linhas = []
    for par in raiz.iter(_NS_W + "p"):
        partes = []
        for no in par.iter():
            if no.tag == _NS_W + "t" and no.text:
                partes.append(no.text)
            elif no.tag == _NS_W + "tab":
                partes.append("  ")
        if partes:
            linhas.append("".join(partes))
    return "\n".join(linhas)


def _texto_xlsx(dados: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        compartilhadas: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            raiz = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
            for si in raiz.iter(_NS_S + "si"):
                compartilhadas.append("".join(t.text or "" for t in si.iter(_NS_S + "t")))
        planilhas = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        linhas: list[str] = []
        for nome in planilhas[:10]:
            raiz = ElementTree.fromstring(z.read(nome))
            for row in raiz.iter(_NS_S + "row"):
                celulas = []
                for c in row.iter(_NS_S + "c"):
                    v = c.find(_NS_S + "v")
                    if c.get("t") == "s" and v is not None and v.text is not None:
                        celulas.append(compartilhadas[int(v.text)])
                    elif c.get("t") == "inlineStr":
                        celulas.append("".join(t.text or "" for t in c.iter(_NS_S + "t")))
                    elif v is not None and v.text is not None:
                        celulas.append(_numero_planilha(v.text))
                if celulas:
                    linhas.append("  ".join(celulas))
    return "\n".join(linhas)


def _numero_planilha(valor: str) -> str:
    """Números de planilha vêm com ponto decimal; converte para o padrão brasileiro quando monetário."""
    try:
        numero = float(valor)
    except ValueError:
        return valor
    if numero.is_integer():
        return str(int(numero))
    return f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
