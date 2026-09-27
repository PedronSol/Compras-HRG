"""Testes unitários: senhas, CNPJ, tipos de arquivo, comparação de propostas e matriz de permissões."""
from decimal import Decimal

from rg import permissoes
from rg.seguranca import senhas
from rg.servicos.arquivos import detectar_mime, sanitizar_nome
from rg.servicos.workflow import comparar_propostas
from rg.validacao import cnpj_valido


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
    assert cnpj_valido("12.ABC.345/01DE-35")  # exemplo oficial da Receita Federal (IN RFB 2.229/2024)


def test_deteccao_de_tipo_por_bytes():
    assert detectar_mime(b"%PDF-1.7 ...") == "application/pdf"
    assert detectar_mime(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert detectar_mime(b"\xff\xd8\xff\xe0 foto") == "image/jpeg"
    assert detectar_mime(b"MZ\x90\x00 executavel") is None
    assert sanitizar_nome("../../etc/passwd", "application/pdf") == "passwd.pdf"
    assert sanitizar_nome("foto.JPEG", "image/jpeg") == "foto.jpeg"


def test_comparacao_de_propostas():
    itens = [{"id": "a", "descricao": "Luva", "unidade": "CX", "quantidade": Decimal("10"), "valor_unitario_estimado": 40},
             {"id": "b", "descricao": "Gaze", "unidade": "PCT", "quantidade": Decimal("5"), "valor_unitario_estimado": 2}]
    cot = [
        {"id": "x", "valor_total": Decimal("420"), "prazo_entrega_dias": 5,
         "itens": [{"solicitacao_item_id": "a", "valor_unitario": Decimal("41"), "quantidade": Decimal("10"), "marca": None},
                   {"solicitacao_item_id": "b", "valor_unitario": Decimal("2"), "quantidade": Decimal("5"), "marca": None}]},
        {"id": "y", "valor_total": Decimal("380"), "prazo_entrega_dias": 9,
         "itens": [{"solicitacao_item_id": "a", "valor_unitario": Decimal("38"), "quantidade": Decimal("10"), "marca": None}]},
    ]
    c = comparar_propostas(itens, cot, 3)
    assert c["ranking"] == ["x", "y"]  # proposta incompleta vai para o fim, mesmo mais barata
    assert c["menor_total"] == Decimal("420") and c["melhor_prazo"] == 5
    assert c["linhas"][0]["menor_unitario"] == Decimal("38") and c["abaixo_do_minimo"] is True


def test_matriz_de_permissoes_segrega_funcoes():
    assert permissoes.pode({"papel": "gestor"}, "solicitacao.aprovar_gestor")
    assert not permissoes.pode({"papel": "admin"}, "solicitacao.aprovar_gestor")  # administrador não aprova compras
    assert not permissoes.pode({"papel": "comprador"}, "pedido.aprovar_financeiro")
    assert not permissoes.pode({"papel": "auditoria"}, "solicitacao.criar")
    escrita = [c for c in permissoes.CAPACIDADES if not c.endswith(".ver")]
    assert not any(permissoes.pode({"papel": "auditoria"}, c) for c in escrita)
