"""Testes unitários: senhas, OCR (análise), CNPJ, periodicidade e marca."""
from datetime import date

from rg.api.servicos import proxima_data
from rg.seguranca import senhas
from rg.servicos.arquivos import detectar_mime, sanitizar_nome
from rg.servicos.ocr.analise import analisar, chave_nfe_valida, cnpj_valido


def test_politica_de_senha():
    assert senhas.validar_politica("curta", minimo=12)
    assert senhas.validar_politica("somenteminusculas", minimo=12)
    assert "A senha não pode conter o seu nome" in senhas.validar_politica(
        "Gustavo#2026abc", minimo=12, nome="Gustavo Silva")
    assert senhas.validar_politica("Hospital#Seguro2026", minimo=12, email="ana@rg.com", nome="Ana Souza") == []


def test_hash_e_reutilizacao():
    h1 = senhas.gerar_hash("Primeira#Senha2026")
    assert h1.startswith("$argon2id$")
    assert senhas.verificar(h1, "Primeira#Senha2026")
    assert not senhas.verificar(h1, "outra")
    assert not senhas.verificar(None, "qualquer")
    assert senhas.senha_reutilizada("Primeira#Senha2026", [senhas.gerar_hash("x"), h1])


def test_cnpj_numerico_e_alfanumerico():
    assert cnpj_valido("11.222.333/0001-81")
    assert not cnpj_valido("11.222.333/0001-82")
    assert not cnpj_valido("00000000000000")
    # CNPJ alfanumérico (IN RFB 2.229/2024) — exemplo oficial da Receita Federal
    assert cnpj_valido("12.ABC.345/01DE-35")


def test_analise_orcamento():
    texto = """ORÇAMENTO Nº 2026-145
MEDTEC EQUIPAMENTOS HOSPITALARES LTDA
CNPJ: 11.222.333/0001-81
Data de emissão: 12/09/2026
Subtotal: R$ 12.000,00
Valor total: R$ 12.450,90
Prazo de entrega: 15 dias úteis
Validade da proposta: 30 dias
Condições de pagamento: 30/60 dias
contato@medtec.com.br (51) 3333-4444"""
    r = analisar(texto)
    assert r["tipo_documento"]["valor"] == "orcamento"
    assert r["cnpj_emitente"]["valor"] == "11.222.333/0001-81"
    assert r["valor_total"]["valor"] == "12450.90"
    assert r["numero_documento"]["valor"] == "2026-145"
    assert r["data_emissao"]["valor"] == "2026-09-12"
    assert r["prazo_entrega_dias"]["valor"] == 15
    assert r["validade_dias"]["valor"] == 30
    assert r["condicoes_pagamento"]["valor"] == "30/60 dias"
    assert "MEDTEC" in r["razao_social"]["valor"]
    assert r["emails"] == ["contato@medtec.com.br"]


def _chave_valida(base43: str) -> str:
    pesos = [2, 3, 4, 5, 6, 7, 8, 9]
    soma = sum(int(c) * pesos[i % 8] for i, c in enumerate(reversed(base43)))
    r = soma % 11
    return base43 + str(0 if r < 2 else 11 - r)


def test_analise_nota_fiscal_com_chave():
    base = "43" + "2609" + "11222333000181" + "55" + "001" + "000004567" + "1" + "12345678"
    chave = _chave_valida(base)
    assert chave_nfe_valida(chave)
    agrupada = " ".join(chave[i:i + 4] for i in range(0, 44, 4))
    texto = f"""DANFE - Documento Auxiliar da Nota Fiscal Eletrônica
CHAVE DE ACESSO
{agrupada}
VALOR TOTAL DA NOTA 8.990,00
DATA DE EMISSÃO 03/09/2026"""
    r = analisar(texto)
    assert r["tipo_documento"]["valor"] == "nota_fiscal"
    assert r["chave_acesso"]["valor"] == chave
    assert r["numero_documento"]["valor"] == "4567"
    assert r["cnpj_emitente"]["valor"] == "11.222.333/0001-81"
    assert r["valor_total"]["valor"] == "8990.00"


def test_analise_laudo_calibracao():
    texto = """CERTIFICADO DE CALIBRAÇÃO Nº CAL-8812
Equipamento: Bomba de infusão BI-300
Número de série: SN-45-2231
Data da calibração: 01/09/2026
Próxima calibração: 01/09/2027
Resultado: APROVADO - dentro da tolerância"""
    r = analisar(texto)
    assert r["tipo_documento"]["valor"] == "laudo"
    assert r["equipamento"]["valor"] == "Bomba de infusão BI-300"
    assert r["data_calibracao"]["valor"] == "2026-09-01"
    assert r["proxima_calibracao"]["valor"] == "2027-09-01"
    assert r["resultado_laudo"]["valor"] == "conforme"


def test_proxima_data_periodicidade():
    assert proxima_data(date(2026, 1, 31), "mensal") == date(2026, 2, 28)
    assert proxima_data(date(2026, 9, 19), "semanal") == date(2026, 9, 26)
    assert proxima_data(date(2026, 8, 31), "semestral") == date(2027, 2, 28)
    assert proxima_data(date(2026, 9, 19), "unica") is None


def test_deteccao_de_tipo_por_bytes():
    assert detectar_mime(b"%PDF-1.7 ...") == "application/pdf"
    assert detectar_mime(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert detectar_mime(b"MZ\x90\x00 executavel") is None
    assert sanitizar_nome("../../etc/passwd", "application/pdf") == "passwd.pdf"
    assert sanitizar_nome("foto.JPEG", "image/jpeg") == "foto.jpeg"
