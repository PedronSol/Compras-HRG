"""Armazenamento cifrado de arquivos e validação de uploads por assinatura binária."""
from __future__ import annotations

import io
import os
import re
import unicodedata
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..errors import ValidacaoError
from ..seguranca.cripto import cofre, sha256_hex

MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

EXTENSOES = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/tiff": ".tif",
    MIME_DOCX: ".docx",
    MIME_XLSX: ".xlsx",
}


def detectar_mime(dados: bytes) -> str | None:
    """Identifica o tipo real do arquivo pelos bytes iniciais (não confia na extensão)."""
    if dados.startswith(b"%PDF-"):
        return "application/pdf"
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if dados.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    if dados[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if dados.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                nomes = set(z.namelist())
                if "[Content_Types].xml" not in nomes:
                    return None
                if "word/document.xml" in nomes:
                    return MIME_DOCX
                if "xl/workbook.xml" in nomes:
                    return MIME_XLSX
        except zipfile.BadZipFile:
            return None
    return None


def sanitizar_nome(nome: str | None, mime: str) -> str:
    base = os.path.basename((nome or "").replace("\\", "/"))
    base = unicodedata.normalize("NFC", base)
    base = "".join(c for c in base if unicodedata.category(c)[0] != "C")
    base = re.sub(r"[<>:\"/\\|?*]", "_", base).strip(" .")
    if not base:
        base = "documento"
    raiz, ext = os.path.splitext(base)
    aceitas = {EXTENSOES[mime], {".jpg": ".jpeg", ".tif": ".tiff"}.get(EXTENSOES[mime], EXTENSOES[mime])}
    if ext.lower() not in aceitas:
        ext = EXTENSOES[mime]
    return (raiz[:180] or "documento") + ext.lower()


class ArquivoValidado:
    __slots__ = ("nome", "mime", "dados", "tamanho", "sha256")

    def __init__(self, nome: str, mime: str, dados: bytes):
        self.nome = nome
        self.mime = mime
        self.dados = dados
        self.tamanho = len(dados)
        self.sha256 = sha256_hex(dados)


def validar_arquivo(file_storage, max_mb: int, campo: str = "arquivos") -> ArquivoValidado:
    dados = file_storage.read(max_mb * 1024 * 1024 + 1)
    if not dados:
        raise ValidacaoError({campo: f"O arquivo {file_storage.filename or ''} está vazio"})
    if len(dados) > max_mb * 1024 * 1024:
        raise ValidacaoError({campo: f"O arquivo {file_storage.filename} excede {max_mb} MB"})
    mime = detectar_mime(dados)
    if not mime:
        raise ValidacaoError({campo: f"Formato não permitido em {file_storage.filename}. "
                                     "Envie PDF, imagem (PNG, JPG, WEBP, TIFF), DOCX ou XLSX."})
    return ArquivoValidado(sanitizar_nome(file_storage.filename, mime), mime, dados)


class Armazenamento:
    def __init__(self) -> None:
        self.base: Path | None = None

    def configurar(self, base: Path) -> None:
        self.base = Path(base).resolve()
        (self.base / "anexos").mkdir(parents=True, exist_ok=True)

    def _resolver(self, caminho: str) -> Path:
        assert self.base is not None, "Armazenamento não configurado"
        destino = (self.base / caminho).resolve()
        if self.base not in destino.parents:
            raise ValueError("Caminho de armazenamento inválido")
        return destino

    def salvar(self, dados: bytes) -> str:
        agora = datetime.now(timezone.utc)
        relativo = f"anexos/{agora:%Y}/{agora:%m}/{uuid.uuid4().hex}.bin"
        destino = self._resolver(relativo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_suffix(".tmp")
        with open(temporario, "wb") as fh:
            fh.write(cofre.cifrar_bytes(dados))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporario, destino)
        return relativo

    def ler(self, caminho: str) -> bytes:
        with open(self._resolver(caminho), "rb") as fh:
            return cofre.decifrar_bytes(fh.read())

    def remover(self, caminho: str) -> None:
        try:
            self._resolver(caminho).unlink(missing_ok=True)
        except OSError:
            pass


armazenamento = Armazenamento()


class LoteArquivos:
    """Grava arquivos cifrados e os remove caso a transação do banco falhe."""

    def __init__(self) -> None:
        self.caminhos: list[str] = []

    def salvar(self, arquivo: ArquivoValidado) -> str:
        caminho = armazenamento.salvar(arquivo.dados)
        self.caminhos.append(caminho)
        return caminho

    def __enter__(self):
        return self

    def __exit__(self, tipo, exc, tb):
        if exc is not None:
            for caminho in self.caminhos:
                armazenamento.remover(caminho)
        return False


def inserir_anexo(cur, lote: LoteArquivos, arquivo: ArquivoValidado, *, usuario_id: str, origem: str,
                  tipo_documento: str, solicitacao_id: str, recebimento_id: str | None = None) -> str:
    """Grava o arquivo cifrado e registra seus metadados. O conteúdo nunca é lido nem interpretado."""
    caminho = lote.salvar(arquivo)
    cur.execute(
        """
        insert into rg.anexos (solicitacao_id, recebimento_id, origem, tipo_documento, nome_original, mime,
                               tamanho, sha256, caminho, enviado_por)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id
        """,
        (solicitacao_id, recebimento_id, origem, tipo_documento, arquivo.nome, arquivo.mime,
         arquivo.tamanho, arquivo.sha256, caminho, usuario_id),
    )
    return str(cur.fetchone()["id"])
