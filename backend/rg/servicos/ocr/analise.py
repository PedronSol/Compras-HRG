"""Interpretação do texto extraído de notas fiscais, orçamentos e laudos.

Heurísticas determinísticas e auditáveis: cada campo retorna valor e confiança
(0–1). Documentos fiscais têm CNPJ e chave de acesso validados por dígito
verificador, eliminando falsos positivos de OCR.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

_MESES = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

RE_CNPJ = re.compile(r"(?<![0-9A-Z])([0-9A-Z]{2}\.?[0-9A-Z]{3}\.?[0-9A-Z]{3}/?[0-9A-Z]{4}-?\d{2})(?![0-9A-Z])")
RE_VALOR = re.compile(r"(?<![\d,.])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})(?![\d])")
RE_DATA = re.compile(r"(?<!\d)(\d{2})[/.-](\d{2})[/.-](\d{4}|\d{2})(?!\d)")
RE_DATA_EXTENSO = re.compile(r"(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})")
RE_CHAVE = re.compile(r"(?<!\d)((?:\d{4}[\s.]?){10}\d{4})(?!\d)")
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
RE_TELEFONE = re.compile(r"(?:\(?\b\d{2}\)?\s?)?(?:9\s?)?\d{4}[-\s]?\d{4}\b")
RE_RAZAO = re.compile(r"\b(LTDA|S\.?/?A\.?|EIRELI|MEI?|EPP|COMERCIO|COMÉRCIO|INDUSTRIA|INDÚSTRIA|SERVICOS|SERVIÇOS)\b", re.I)


def _sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def cnpj_valido(cnpj: str) -> bool:
    d = re.sub(r"[^0-9A-Z]", "", cnpj.upper())
    if not re.fullmatch(r"[0-9A-Z]{12}\d{2}", d) or len(set(d)) == 1:
        return False

    def dv(base: str, pesos: list[int]) -> int:
        soma = sum((ord(c) - 48) * p for c, p in zip(base, pesos))
        r = soma % 11
        return 0 if r < 2 else 11 - r

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    return dv(d[:12], p1) == int(d[12]) and dv(d[:13], p2) == int(d[13])


def formatar_cnpj(cnpj: str) -> str:
    d = re.sub(r"[^0-9A-Z]", "", cnpj.upper())
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else cnpj


def chave_nfe_valida(chave: str) -> bool:
    d = re.sub(r"\D", "", chave)
    if len(d) != 44:
        return False
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(c) * pesos[i % 8] for i, c in enumerate(reversed(d[:43])))
    r = soma % 11
    return (0 if r < 2 else 11 - r) == int(d[43])


def _valor(texto: str) -> Decimal | None:
    try:
        return Decimal(texto.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _data(dia: str, mes: str, ano: str) -> date | None:
    try:
        a = int(ano)
        if a < 100:
            a += 2000
        d = date(a, int(mes), int(dia))
    except ValueError:
        return None
    return d if 2000 <= d.year <= 2100 else None


def _datas(linha: str) -> list[date]:
    encontradas = [d for d in (_data(*m.groups()) for m in RE_DATA.finditer(linha)) if d]
    base = _sem_acentos(linha.lower())
    for m in RE_DATA_EXTENSO.finditer(base):
        mes = _MESES.get(m.group(2))
        if mes:
            d = _data(m.group(1), str(mes), m.group(3))
            if d:
                encontradas.append(d)
    return encontradas


def _campo(valor, confianca: float, origem: str | None = None) -> dict:
    return {"valor": valor, "confianca": round(confianca, 2), "trecho": (origem or "")[:160] or None}


def _valor_em_linha_ou_proxima(linhas: list[str], i: int) -> tuple[Decimal, str] | None:
    for j in (i, i + 1, i + 2):
        if j < len(linhas):
            valores = [(_valor(v), linhas[j]) for v in RE_VALOR.findall(linhas[j])]
            valores = [v for v in valores if v[0] is not None and v[0] > 0]
            if valores:
                return valores[-1]
    return None


def classificar(texto_normalizado: str) -> tuple[str, float]:
    t = texto_normalizado
    pontos = {
        "nota_fiscal": sum(k in t for k in ("danfe", "nota fiscal", "nf-e", "nfs-e", "chave de acesso",
                                            "documento auxiliar", "natureza da operacao", "icms")),
        "laudo": sum(k in t for k in ("laudo", "certificado de calibracao", "calibracao", "rastreabilidade",
                                      "incerteza", "responsavel tecnico", "conclusao", "inspecao")),
        "orcamento": sum(k in t for k in ("orcamento", "proposta", "cotacao", "validade da proposta",
                                          "prazo de entrega", "condicoes de pagamento", "forma de pagamento")),
    }
    melhor = max(pontos, key=pontos.get)
    if pontos[melhor] == 0:
        return "outro", 0.2
    total = sum(pontos.values())
    return melhor, min(0.95, 0.4 + 0.6 * pontos[melhor] / total)


def analisar(texto: str) -> dict:
    """Retorna os campos estruturados identificados no documento."""
    linhas = [re.sub(r"[ \t]+", " ", l).strip() for l in texto.splitlines()]
    linhas = [l for l in linhas if l and l != "\f"]
    norm = [_sem_acentos(l.lower()) for l in linhas]
    completo = "\n".join(norm)
    resultado: dict = {"avisos": []}

    tipo, conf_tipo = classificar(completo)
    resultado["tipo_documento"] = _campo(tipo, conf_tipo)

    # CNPJs válidos (numéricos ou alfanuméricos)
    cnpjs: list[dict] = []
    vistos = set()
    for i, linha in enumerate(linhas):
        for m in RE_CNPJ.finditer(linha.upper()):
            bruto = re.sub(r"[^0-9A-Z]", "", m.group(1))
            if bruto in vistos:
                continue
            if cnpj_valido(bruto):
                vistos.add(bruto)
                cnpjs.append({"cnpj": bruto, "formatado": formatar_cnpj(bruto), "linha": i})
    resultado["cnpjs"] = [{"cnpj": c["cnpj"], "formatado": c["formatado"]} for c in cnpjs]

    # Chave de acesso NF-e (44 dígitos com DV)
    chave = None
    for m in RE_CHAVE.finditer(texto):
        d = re.sub(r"\D", "", m.group(1))
        if chave_nfe_valida(d):
            chave = d
            break
    if chave:
        resultado["chave_acesso"] = _campo(chave, 0.99)
        resultado["numero_documento"] = _campo(str(int(chave[25:34])), 0.97, "chave de acesso")
        resultado["serie"] = _campo(str(int(chave[22:25])), 0.97, "chave de acesso")
        emitente = chave[6:20]
        if cnpj_valido(emitente):
            resultado["cnpj_emitente"] = _campo(formatar_cnpj(emitente), 0.99, "chave de acesso")
        if resultado["tipo_documento"]["valor"] != "nota_fiscal":
            resultado["tipo_documento"] = _campo("nota_fiscal", 0.9)

    if "cnpj_emitente" not in resultado and cnpjs:
        idx_cnpj_rotulado = next((c for c in cnpjs if "cnpj" in norm[c["linha"]]), cnpjs[0])
        resultado["cnpj_emitente"] = _campo(idx_cnpj_rotulado["formatado"], 0.8, linhas[idx_cnpj_rotulado["linha"]])

    # Razão social: linha com natureza jurídica próxima ao CNPJ do emitente, ou primeira ocorrência
    razao = None
    if cnpjs:
        alvo = cnpjs[0]["linha"]
        for j in range(max(0, alvo - 3), min(len(linhas), alvo + 2)):
            candidato = re.sub(r"(?i)raz[aã]o social\s*[:\-]?\s*", "", linhas[j])
            candidato = RE_CNPJ.sub("", candidato).replace("CNPJ", "").strip(" :-|")
            if RE_RAZAO.search(candidato) and 3 <= len(candidato) <= 120:
                razao = (candidato, 0.75, linhas[j])
                break
    if not razao:
        for i, l in enumerate(linhas[:25]):
            if "razao social" in norm[i] or "fornecedor" in norm[i] or "emitente" in norm[i]:
                partes = re.split(r"[:\-]", l, maxsplit=1)
                if len(partes) == 2 and len(partes[1].strip()) >= 3:
                    razao = (partes[1].strip(), 0.65, l)
                    break
            if RE_RAZAO.search(l) and not RE_VALOR.search(l) and len(l) <= 120:
                razao = (RE_CNPJ.sub("", l).strip(" :-|"), 0.55, l)
                break
    if razao:
        resultado["razao_social"] = _campo(razao[0], razao[1], razao[2])

    # Valor total: prioriza rótulos específicos
    rotulos = [
        ("valor total da nota", 0.95), ("total da nota", 0.93), ("valor total geral", 0.93),
        ("total geral", 0.92), ("valor liquido", 0.9), ("total a pagar", 0.9), ("valor total", 0.88),
        ("total do orcamento", 0.9), ("total da proposta", 0.9), ("valor global", 0.88), ("total", 0.6),
    ]
    total = None
    for rotulo, conf in rotulos:
        for i, l in enumerate(norm):
            if rotulo in l and "subtotal" not in l and "total de itens" not in l:
                achado = _valor_em_linha_ou_proxima(linhas, i)
                if achado:
                    total = (achado[0], conf, achado[1])
                    break
        if total:
            break
    todos_valores = sorted({v for v in (_valor(x) for x in RE_VALOR.findall(texto)) if v and v > 0}, reverse=True)
    if not total and todos_valores:
        total = (todos_valores[0], 0.4, "maior valor do documento")
        resultado["avisos"].append("Valor total inferido pelo maior valor encontrado; confirme manualmente.")
    if total:
        resultado["valor_total"] = _campo(f"{total[0]:.2f}", total[1], total[2])
    resultado["valores_encontrados"] = [f"{v:.2f}" for v in todos_valores[:15]]

    # Número do documento (quando não obtido pela chave)
    if "numero_documento" not in resultado:
        padroes = [
            (r"(?:nota fiscal|nf-?e|nfs-?e|danfe)[^\n]{0,20}?n[or°º.]*\s*[:#]?\s*(\d[\d.]{0,14})", 0.85),
            (r"(?:orcamento|proposta|cotacao|laudo|certificado)\s*(?:comercial\s*)?(?:n[or°º.]*|numero|#)\s*[:#]?\s*([a-z0-9][\w/.-]{0,20})", 0.8),
            (r"\bn[°º]\s*[:#]?\s*(\d[\d./-]{0,14})", 0.55),
            (r"\bnumero\s*[:#]?\s*(\d[\d./-]{0,14})", 0.55),
        ]
        for padrao, conf in padroes:
            m = re.search(padrao, completo)
            if m:
                resultado["numero_documento"] = _campo(m.group(1).strip(".").upper(), conf, m.group(0))
                break

    # Datas
    datas: list[date] = []
    emissao = None
    for i, l in enumerate(norm):
        ds = _datas(linhas[i])
        datas.extend(ds)
        if ds and emissao is None and any(k in l for k in ("emissao", "data do documento", "data:", "data de emissao")):
            emissao = (ds[0], 0.85, linhas[i])
    if emissao is None and datas:
        emissao = (datas[0], 0.5, "primeira data do documento")
    if emissao:
        resultado["data_emissao"] = _campo(emissao[0].isoformat(), emissao[1], emissao[2])
    resultado["datas"] = sorted({d.isoformat() for d in datas})

    # Campos comerciais (orçamentos)
    m = re.search(r"prazo de entrega[^\n\d]{0,40}(\d{1,3})\s*(dias?(?:\s+uteis)?|d\.?u\.?)", completo)
    if m:
        resultado["prazo_entrega_dias"] = _campo(int(m.group(1)), 0.85, m.group(0))
    m = re.search(r"validade(?: da proposta| do orcamento)?[^\n\d]{0,30}(\d{1,3})\s*dias", completo)
    if m:
        resultado["validade_dias"] = _campo(int(m.group(1)), 0.85, m.group(0))
    else:
        for i, l in enumerate(norm):
            if "validade" in l or "valido ate" in l:
                ds = _datas(linhas[i])
                if ds:
                    resultado["validade_data"] = _campo(ds[-1].isoformat(), 0.8, linhas[i])
                    break
    for i, l in enumerate(norm):
        if "condicoes de pagamento" in l or "condicao de pagamento" in l or "forma de pagamento" in l:
            partes = re.split(r":", linhas[i], maxsplit=1)
            valor = partes[1].strip() if len(partes) == 2 and partes[1].strip() else (
                linhas[i + 1] if i + 1 < len(linhas) else "")
            if valor:
                resultado["condicoes_pagamento"] = _campo(valor[:160], 0.75, linhas[i])
            break

    # Campos técnicos (laudos / certificados de calibração)
    for chave_campo, termos in (
        ("equipamento", ("equipamento", "instrumento", "descricao do item")),
        ("numero_serie", ("numero de serie", "n. de serie", "n° de serie", "no de serie", "serie:")),
        ("patrimonio", ("patrimonio", "tag", "identificacao")),
        ("responsavel_tecnico", ("responsavel tecnico", "executante", "tecnico responsavel")),
    ):
        for i, l in enumerate(norm):
            if any(t in l for t in termos):
                partes = re.split(r"[:\-]", linhas[i], maxsplit=1)
                if len(partes) == 2 and partes[1].strip():
                    resultado[chave_campo] = _campo(partes[1].strip()[:120], 0.7, linhas[i])
                    break
    for i, l in enumerate(norm):
        if "data da calibracao" in l or "data de calibracao" in l or "data da inspecao" in l:
            ds = _datas(linhas[i])
            if ds:
                resultado["data_calibracao"] = _campo(ds[0].isoformat(), 0.85, linhas[i])
        if "proxima calibracao" in l or "valido ate" in l or "vencimento" in l:
            ds = _datas(linhas[i])
            if ds:
                resultado["proxima_calibracao"] = _campo(ds[-1].isoformat(), 0.8, linhas[i])
    if tipo == "laudo" or resultado["tipo_documento"]["valor"] == "laudo":
        if re.search(r"\b(aprovado|conforme|dentro da tolerancia)\b", completo):
            resultado["resultado_laudo"] = _campo("conforme", 0.7)
        elif re.search(r"\b(reprovado|nao conforme|fora da tolerancia)\b", completo):
            resultado["resultado_laudo"] = _campo("nao_conforme", 0.7)

    resultado["emails"] = sorted(set(RE_EMAIL.findall(texto)))[:5]
    telefones = []
    for t in RE_TELEFONE.findall(texto):
        digitos = re.sub(r"\D", "", t)
        if 10 <= len(digitos) <= 11 and digitos not in telefones:
            telefones.append(digitos)
    resultado["telefones"] = telefones[:5]

    if not cnpjs and resultado["tipo_documento"]["valor"] in ("nota_fiscal", "orcamento"):
        resultado["avisos"].append("Nenhum CNPJ válido identificado.")
    if len(re.sub(r"\s", "", texto)) < 30:
        resultado["avisos"].append("Pouco texto reconhecido; verifique a qualidade da digitalização.")
    return resultado
