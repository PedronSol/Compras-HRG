"""Validação declarativa e enxuta de payloads JSON/form."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable

from .errors import ValidacaoError

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def limpar_texto(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = unicodedata.normalize("NFC", str(valor))
    # remove caracteres de controle (exceto quebras de linha e tab)
    texto = "".join(c for c in texto if c in "\n\t" or unicodedata.category(c)[0] != "C")
    texto = texto.strip()
    return texto or None


@dataclass
class Campo:
    nome: str
    tipo: str = "texto"                     # texto|email|inteiro|decimal|data|hora|bool|uuid|escolha|lista_uuid
    obrigatorio: bool = False
    min_len: int | None = None
    max_len: int | None = None
    minimo: float | None = None
    maximo: float | None = None
    escolhas: Iterable[str] | None = None
    rotulo: str | None = None
    validador: Callable[[Any], str | None] | None = None
    padrao: Any = None
    extras: dict = field(default_factory=dict)


def validar(dados: dict | None, campos: list[Campo], *, parcial: bool = False) -> dict:
    """Valida e normaliza `dados`. Com `parcial=True`, apenas campos presentes são exigidos."""
    dados = dados or {}
    erros: dict[str, str] = {}
    saida: dict[str, Any] = {}
    for c in campos:
        rotulo = c.rotulo or c.nome
        presente = c.nome in dados
        bruto = dados.get(c.nome)
        if parcial and not presente:
            continue
        if isinstance(bruto, str) or bruto is None:
            texto = limpar_texto(bruto)
        else:
            texto = bruto
        if texto is None or texto == "":
            if c.obrigatorio:
                erros[c.nome] = f"{rotulo} é obrigatório"
            elif presente or c.padrao is not None:
                saida[c.nome] = c.padrao
            continue
        try:
            valor = _converter(c, texto)
        except ValueError as exc:
            erros[c.nome] = str(exc) or f"{rotulo} inválido"
            continue
        if isinstance(valor, str):
            if c.min_len is not None and len(valor) < c.min_len:
                erros[c.nome] = f"{rotulo} deve ter no mínimo {c.min_len} caracteres"
                continue
            if c.max_len is not None and len(valor) > c.max_len:
                erros[c.nome] = f"{rotulo} deve ter no máximo {c.max_len} caracteres"
                continue
        if isinstance(valor, (int, Decimal)) and not isinstance(valor, bool):
            if c.minimo is not None and valor < Decimal(str(c.minimo)):
                erros[c.nome] = f"{rotulo} deve ser maior ou igual a {c.minimo}"
                continue
            if c.maximo is not None and valor > Decimal(str(c.maximo)):
                erros[c.nome] = f"{rotulo} deve ser menor ou igual a {c.maximo}"
                continue
        if c.validador:
            msg = c.validador(valor)
            if msg:
                erros[c.nome] = msg
                continue
        saida[c.nome] = valor
    if erros:
        raise ValidacaoError(erros)
    return saida


def _converter(c: Campo, valor: Any) -> Any:
    t = c.tipo
    if t == "texto":
        return str(valor)
    if t == "email":
        v = str(valor).lower()
        if not EMAIL_RE.match(v) or len(v) > 254:
            raise ValueError("E-mail inválido")
        return v
    if t == "inteiro":
        if isinstance(valor, bool):
            raise ValueError("Número inteiro inválido")
        try:
            return int(str(valor))
        except ValueError:
            raise ValueError("Número inteiro inválido") from None
    if t == "decimal":
        texto = str(valor).strip().replace("R$", "").replace(" ", "")
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            d = Decimal(texto)
        except InvalidOperation:
            raise ValueError("Valor numérico inválido") from None
        if not d.is_finite():
            raise ValueError("Valor numérico inválido")
        return d.quantize(Decimal("0.01"))
    if t == "data":
        try:
            return date.fromisoformat(str(valor)[:10])
        except ValueError:
            raise ValueError("Data inválida (use AAAA-MM-DD)") from None
    if t == "hora":
        try:
            return time.fromisoformat(str(valor)[:5])
        except ValueError:
            raise ValueError("Horário inválido (use HH:MM)") from None
    if t == "bool":
        if isinstance(valor, bool):
            return valor
        return str(valor).lower() in {"1", "true", "on", "sim"}
    if t == "uuid":
        if not UUID_RE.match(str(valor)):
            raise ValueError("Identificador inválido")
        return str(valor).lower()
    if t == "lista_uuid":
        itens = valor if isinstance(valor, list) else [v for v in str(valor).split(",") if v]
        for item in itens:
            if not UUID_RE.match(str(item)):
                raise ValueError("Lista de identificadores inválida")
        return [str(i).lower() for i in itens]
    if t == "escolha":
        if str(valor) not in set(c.escolhas or ()):
            raise ValueError("Opção inválida")
        return str(valor)
    raise ValueError(f"Tipo de campo desconhecido: {t}")


def somente_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def cnpj_valido(cnpj: str) -> bool:
    """Dígitos verificadores de CNPJ numérico ou alfanumérico (IN RFB nº 2.229/2024)."""
    d = re.sub(r"[^0-9A-Z]", "", (cnpj or "").upper())
    if not re.fullmatch(r"[0-9A-Z]{12}\d{2}", d) or len(set(d)) == 1:
        return False

    def dv(base: str, pesos: list[int]) -> int:
        soma = sum((ord(c) - 48) * p for c, p in zip(base, pesos))
        r = soma % 11
        return 0 if r < 2 else 11 - r

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    return dv(d[:12], p1) == int(d[12]) and dv(d[:13], [6] + p1) == int(d[13])
