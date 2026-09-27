"""Infraestrutura de testes: PostgreSQL real (pgembed ou RG_TEST_PG_URL), migrações e usuários dos 8 perfis."""
from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import psycopg
import pytest
from cryptography.fernet import Fernet
from psycopg.rows import dict_row

from rg import create_app
from rg.config import Config
from rg.db import aplicar_migracoes, db
from rg.seguranca import senhas

SENHA_PADRAO = "Hospital#Seguro2026"


def _instalar_fusos(destino: Path) -> None:
    """O build embutido do PostgreSQL não traz a base IANA; usa a do pacote tzdata (mesmo formato TZif)."""
    if destino.exists():
        return
    import tzdata
    origem = Path(tzdata.__file__).parent / "zoneinfo"
    shutil.copytree(origem, destino, ignore=shutil.ignore_patterns("__init__.py", "__pycache__"))


class _ServidorExterno:
    """PostgreSQL já em execução (RG_TEST_PG_URL), útil onde o pgembed não está disponível."""

    def __init__(self, url: str):
        self.url = url

    def get_uri(self) -> str:
        return self.url


@pytest.fixture(scope="session")
def servidor_pg():
    externo = os.environ.get("RG_TEST_PG_URL")
    if externo:
        yield _ServidorExterno(externo)
        return
    pgembed = pytest.importorskip("pgembed")
    _instalar_fusos(Path(pgembed.__file__).parent / "pginstall" / "share" / "postgresql" / "timezone")
    diretorio = tempfile.mkdtemp(prefix="rg-pg-")
    servidor = pgembed.get_server(diretorio, cleanup_mode="stop")
    yield servidor
    try:
        servidor.cleanup()
    except Exception:
        pass
    shutil.rmtree(diretorio, ignore_errors=True)


@pytest.fixture(scope="session")
def url_banco(servidor_pg):
    base = servidor_pg.get_uri()
    nome = f"rg_teste_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(base, autocommit=True) as c:
        c.execute(f'create database "{nome}"')
    url = base.rsplit("/", 1)[0] + "/" + nome
    aplicar_migracoes(url)
    return url


@pytest.fixture(scope="session")
def app(url_banco, tmp_path_factory):
    config = Config(
        TESTING=True,
        AMBIENTE="teste",
        SECRET_KEY="t" * 40,
        SIGNATURE_SECRET="s" * 40,
        ENCRYPTION_KEYS=[Fernet.generate_key().decode()],
        DATABASE_URL=url_banco,
        DB_APP_ROLE="rg_app",
        DB_POOL_MIN=1,
        DB_POOL_MAX=8,
        SESSION_COOKIE_SECURE=False,
        HIBP_ENABLED=False,
        STORAGE_DIR=tmp_path_factory.mktemp("storage"),
        BACKGROUND_JOBS=False,
        SERVE_FRONTEND=True,
    )
    aplicacao = create_app(config)
    yield aplicacao
    db.close()


@pytest.fixture()
def sql(url_banco):
    """Conexão superusuário para preparar cenários (ignora RLS)."""
    with psycopg.connect(url_banco, autocommit=True, row_factory=dict_row) as conn:
        yield conn


def criar_usuario(url: str, *, papel: str, setor: str, status: str = "aprovado", senha: str = SENHA_PADRAO,
                  nome: str | None = None) -> dict:
    email = f"{papel}.{uuid.uuid4().hex[:8]}@rghospital.com.br"
    nome = nome or f"Usuário {papel.title()} Teste"
    with psycopg.connect(url, autocommit=True, row_factory=dict_row) as c:
        c.execute("select set_config('app.contexto', 'sistema', false)")
        linha = c.execute(
            "insert into rg.usuarios (email, nome, setor_codigo, papel, status, senha_hash) values (%s,%s,%s,%s,%s,%s)"
            " returning id", (email, nome, setor, papel, status, senhas.gerar_hash(senha))).fetchone()
    return {"id": str(linha["id"]), "email": email, "senha": senha, "papel": papel, "setor": setor, "nome": nome}


class Cliente:
    """Cliente HTTP autenticado que envia o token CSRF automaticamente."""

    def __init__(self, app, usuario: dict | None = None):
        self.http = app.test_client()
        self.csrf = ""
        self.usuario = usuario
        if usuario:
            r = self.http.post("/api/v1/auth/login", json={"email": usuario["email"], "senha": usuario["senha"]})
            assert r.status_code == 200, r.get_json()
            self.csrf = r.get_json()["csrf_token"]

    def _h(self, extra=None):
        h = {"X-CSRF-Token": self.csrf}
        h.update(extra or {})
        return h

    def get(self, url, **kw):
        return self.http.get(url, **kw)

    def post(self, url, json=None, data=None, **kw):
        if data is not None:
            return self.http.post(url, data=data, headers=self._h(), content_type="multipart/form-data", **kw)
        return self.http.post(url, json=json if json is not None else {}, headers=self._h(), **kw)

    def patch(self, url, json=None, **kw):
        return self.http.patch(url, json=json or {}, headers=self._h(), **kw)

    def delete(self, url, **kw):
        return self.http.delete(url, headers=self._h(), **kw)


@pytest.fixture()
def usuarios(url_banco):
    return {
        "admin": criar_usuario(url_banco, papel="admin", setor="administracao", nome="Ana Administradora"),
        "solicitante": criar_usuario(url_banco, papel="solicitante", setor="uti_adulto", nome="Sofia Solicitante"),
        "gestor": criar_usuario(url_banco, papel="gestor", setor="uti_adulto", nome="Gustavo Gestor"),
        "solicitante_lab": criar_usuario(url_banco, papel="solicitante", setor="laboratorio", nome="Lia Laboratório"),
        "gestor_lab": criar_usuario(url_banco, papel="gestor", setor="laboratorio", nome="Lara Laboratório"),
        "comprador": criar_usuario(url_banco, papel="comprador", setor="suprimentos", nome="Carlos Comprador"),
        "financeiro": criar_usuario(url_banco, papel="financeiro", setor="financeiro", nome="Fabiana Financeiro"),
        "recebimento": criar_usuario(url_banco, papel="recebimento", setor="suprimentos", nome="Rui Recebimento"),
        "diretoria": criar_usuario(url_banco, papel="diretoria", setor="diretoria", nome="Diana Diretoria"),
        "auditoria": criar_usuario(url_banco, papel="auditoria", setor="controladoria", nome="Otto Auditor"),
    }


@pytest.fixture()
def clientes(app, usuarios):
    return {nome: Cliente(app, u) for nome, u in usuarios.items()}


def pdf_orcamento() -> bytes:
    """Documento de orçamento apenas anexado (o sistema nunca lê seu conteúdo)."""
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(60, 800, "ORÇAMENTO Nº 2026-145 — MEDTEC EQUIPAMENTOS HOSPITALARES LTDA")
    c.drawString(60, 778, "Monitor multiparamétrico — 2 unidades — R$ 12.450,90")
    c.save()
    return buffer.getvalue()


ITENS_PADRAO = [
    {"descricao": "Monitor multiparamétrico 12 polegadas", "unidade": "UN", "quantidade": "2",
     "valor_unitario_estimado": "6.500,00"},
    {"descricao": "Cabo de ECG 5 vias", "unidade": "UN", "quantidade": "4", "valor_unitario_estimado": "250"},
]


def dados_solicitacao(itens=None, **extra) -> dict:
    base = {
        "tipo": "equipamento",
        "titulo": "Aquisição de monitores multiparamétricos",
        "descricao": "Substituição de dois monitores da UTI adulto com defeito recorrente.",
        "justificativa": "Equipamentos atuais apresentam falhas frequentes que colocam pacientes em risco.",
        "urgencia": "urgente",
        "itens": json.dumps(itens if itens is not None else ITENS_PADRAO),
    }
    base.update(extra)
    return base


def criar_solicitacao(cliente: Cliente, com_anexo: bool = True, itens=None, **extra) -> dict:
    dados = dados_solicitacao(itens, **extra)
    if com_anexo:
        dados["arquivos"] = [(io.BytesIO(pdf_orcamento()), "orcamento-medtec.pdf")]
    r = cliente.post("/api/v1/solicitacoes", data=dados)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def acao(cliente: Cliente, sid: str, nome: str, **dados):
    return cliente.post(f"/api/v1/solicitacoes/{sid}/acoes/{nome}", json=dados)


def acao_pedido(cliente: Cliente, pid: str, nome: str, **dados):
    return cliente.post(f"/api/v1/pedidos/{pid}/acoes/{nome}", json=dados)


def fornecedor(cliente: Cliente, cnpj: str, razao: str) -> str:
    r = cliente.post("/api/v1/fornecedores", json={"razao_social": razao, "cnpj": cnpj})
    if r.status_code == 422:
        return cliente.get("/api/v1/fornecedores", query_string={"q": cnpj}).get_json()["itens"][0]["id"]
    assert r.status_code == 201, r.get_json()
    return r.get_json()["id"]


def proposta(cliente: Cliente, sid: str, fornecedor_id: str, itens: list[dict], precos: list[str], **extra):
    corpo = {"fornecedor_id": fornecedor_id, "prazo_entrega_dias": extra.pop("prazo", 10),
             "condicoes_pagamento": "30 dias", "frete": extra.pop("frete", "0"),
             "itens": [{"solicitacao_item_id": i["id"], "quantidade": str(i["quantidade"]), "valor_unitario": p}
                       for i, p in zip(itens, precos)]}
    corpo.update(extra)
    return cliente.post(f"/api/v1/solicitacoes/{sid}/propostas", json=corpo)


def ate_aprovada(clientes, **extra) -> dict:
    d = criar_solicitacao(clientes["solicitante"], com_anexo=False, **extra)
    sid = d["solicitacao"]["id"]
    r = acao(clientes["gestor"], sid, "aprovar", versao=d["solicitacao"]["versao"])
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def ate_pedido(clientes, **extra) -> tuple[dict, str]:
    """Leva uma solicitação até o pedido emitido. Retorna (detalhe, pedido_id)."""
    d = ate_aprovada(clientes, **extra)
    sid = d["solicitacao"]["id"]
    comprador = clientes["comprador"]
    d = acao(comprador, sid, "iniciar_cotacao", versao=d["solicitacao"]["versao"]).get_json()
    itens = d["itens"]
    f1 = fornecedor(comprador, "11.222.333/0001-81", "MEDTEC EQUIPAMENTOS HOSPITALARES LTDA")
    f2 = fornecedor(comprador, "12.ABC.345/01DE-35", "BIOMED SERVICOS LTDA")
    f3 = fornecedor(comprador, "45.723.174/0001-10", "LAGOA PRODUTOS HOSPITALARES LTDA")
    for f, precos in ((f1, ["6400", "240"]), (f2, ["6100", "260"]), (f3, ["6900", "230"])):
        assert proposta(comprador, sid, f, itens, precos).status_code == 201
    d = comprador.get(f"/api/v1/solicitacoes/{sid}").get_json()
    vencedora = d["comparacao"]["ranking"][0]
    d = acao(comprador, sid, "definir_fornecedor", versao=d["solicitacao"]["versao"], cotacao_id=vencedora).get_json()
    r = acao(comprador, sid, "emitir_pedido", versao=d["solicitacao"]["versao"])
    assert r.status_code == 200, r.get_json()
    return r.get_json(), r.get_json()["pedido_criado"]


@pytest.fixture()
def raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[2]
