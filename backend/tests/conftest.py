"""Infraestrutura de testes: PostgreSQL 17 real (pgembed), migrações e usuários de cada papel."""
from __future__ import annotations

import io
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


@pytest.fixture(scope="session")
def servidor_pg():
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
        OCR_SINCRONO=True,
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
        "gestor": criar_usuario(url_banco, papel="gestor", setor="uti_adulto", nome="Gustavo Gestor"),
        "gestor_lab": criar_usuario(url_banco, papel="gestor", setor="laboratorio", nome="Lara Laboratório"),
        "compras": criar_usuario(url_banco, papel="compras", setor="suprimentos", nome="Carlos Compras"),
    }


@pytest.fixture()
def clientes(app, usuarios):
    return {nome: Cliente(app, u) for nome, u in usuarios.items()}


def pdf_orcamento(cnpj: str = "11.222.333/0001-81", total: str = "12.450,90") -> bytes:
    from reportlab.pdfgen import canvas
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    linhas = [
        "ORÇAMENTO Nº 2026-145",
        "MEDTEC EQUIPAMENTOS HOSPITALARES LTDA",
        f"CNPJ: {cnpj}",
        "Data de emissão: 12/09/2026",
        "Item: Monitor multiparamétrico - 2 unidades",
        "Subtotal: R$ 12.000,00",
        f"Valor total: R$ {total}",
        "Prazo de entrega: 15 dias úteis",
        "Validade da proposta: 30 dias",
        "Condições de pagamento: 30/60 dias",
        "contato@medtec.com.br  (51) 3333-4444",
    ]
    y = 800
    for linha in linhas:
        c.drawString(60, y, linha)
        y -= 22
    c.save()
    return buffer.getvalue()


def dados_solicitacao(**extra) -> dict:
    base = {
        "tipo": "compra",
        "titulo": "Aquisição de monitores multiparamétricos",
        "descricao": "Substituição de dois monitores da UTI adulto com defeito recorrente.",
        "justificativa": "Equipamentos atuais apresentam falhas frequentes que colocam pacientes em risco.",
        "urgencia": "urgente",
        "valor_estimado": "13.000,00",
    }
    base.update(extra)
    return base


def criar_solicitacao(cliente: Cliente, com_anexo: bool = True, **extra) -> dict:
    dados = dados_solicitacao(**extra)
    if com_anexo:
        dados["arquivos"] = [(io.BytesIO(pdf_orcamento()), "orcamento-medtec.pdf")]
    r = cliente.post("/api/v1/solicitacoes", data=dados)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


@pytest.fixture()
def raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[2]
