"""Autenticação, cadastro, sessões, perfil e direitos do titular (LGPD)."""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, make_response, request

from ..db import db
from ..errors import ApiError, ValidacaoError
from ..extensoes import limiter
from ..seguranca import senhas
from ..seguranca.cripto import cofre
from ..seguranca.sessao import (buscar_sessao, criar_sessao, definir_cookie, hash_token, ip_cliente,
                                registrar_evento, remover_cookie, requer_login, tx)
from ..validacao import Campo, somente_digitos, validar
from ._util import corpo_json

bp = Blueprint("auth", __name__)

MSG_CREDENCIAIS = "E-mail ou senha inválidos"


def _checar_senha_nova(senha: str, *, email: str, nome: str) -> None:
    cfg = current_app.config
    problemas = senhas.validar_politica(senha, minimo=cfg["SENHA_MIN_CARACTERES"], email=email, nome=nome)
    if problemas:
        raise ValidacaoError({"senha": problemas[0]}, "A senha não atende à política de segurança")
    if cfg["HIBP_ENABLED"] and senhas.senha_vazada(senha, cfg["HIBP_TIMEOUT"]):
        raise ValidacaoError({"senha": "Esta senha aparece em vazamentos públicos de dados. Escolha outra."},
                             "Senha comprometida")


@bp.post("/auth/login")
@limiter.limit("10 per minute; 60 per hour")
def login():
    dados = validar(corpo_json(), [
        Campo("email", "email", obrigatorio=True, rotulo="E-mail"),
        Campo("senha", "texto", obrigatorio=True, max_len=128, rotulo="Senha"),
    ])
    cfg = current_app.config
    with db.transacao(sistema=True, ip=ip_cliente()) as cur:
        cur.execute(
            "select id, nome, senha_hash, status, bloqueado_ate, bloqueado_ate > now() as bloqueado,"
            " ceil(extract(epoch from (bloqueado_ate - now())) / 60) as minutos, tentativas_falhas"
            " from rg.usuarios where lower(email) = %s and anonimizado_em is null",
            (dados["email"],),
        )
        u = cur.fetchone()
        bloqueado = bool(u and u["bloqueado"])
        if bloqueado:
            registrar_evento(cur, "LOGIN_BLOQUEADO", "rg.usuarios", str(u["id"]))
            falha = False
        elif not u or not senhas.verificar(u["senha_hash"] if u else None, dados["senha"]):
            if u:
                tentativas = u["tentativas_falhas"] + 1
                if tentativas >= cfg["LOGIN_MAX_TENTATIVAS"]:
                    cur.execute("update rg.usuarios set tentativas_falhas = 0,"
                                " bloqueado_ate = now() + make_interval(mins => %s) where id = %s",
                                (cfg["LOGIN_BLOQUEIO_MINUTOS"], u["id"]))
                else:
                    cur.execute("update rg.usuarios set tentativas_falhas = %s where id = %s", (tentativas, u["id"]))
                registrar_evento(cur, "LOGIN_FALHA", "rg.usuarios", str(u["id"]), {"tentativa": tentativas})
            else:
                registrar_evento(cur, "LOGIN_FALHA", "rg.usuarios", None, {"email_informado": dados["email"][:3] + "***"})
            falha = True
        else:
            falha = False
    if bloqueado:
        raise ApiError(f"Conta temporariamente bloqueada por excesso de tentativas. "
                       f"Tente novamente em {int(u['minutos'])} minuto(s).", 423, "conta_bloqueada")
    if falha:
        raise ApiError(MSG_CREDENCIAIS, 401, "credenciais_invalidas")

    if u["status"] != "aprovado":
        mensagens = {
            "pendente": "Seu cadastro está aguardando aprovação do administrador.",
            "rejeitado": "Seu cadastro não foi aprovado. Procure a Administração do hospital.",
            "suspenso": "Seu acesso está suspenso. Procure a Administração do hospital.",
        }
        raise ApiError(mensagens[u["status"]], 403, f"conta_{u['status']}")

    with db.transacao(sistema=True, usuario_id=str(u["id"]), ip=ip_cliente()) as cur:
        novo_hash = senhas.gerar_hash(dados["senha"]) if senhas.precisa_rehash(u["senha_hash"]) else u["senha_hash"]
        cur.execute("update rg.usuarios set tentativas_falhas = 0, bloqueado_ate = null, ultimo_login_em = now(),"
                    " senha_hash = %s where id = %s", (novo_hash, u["id"]))
        token, _csrf = criar_sessao(cur, str(u["id"]))
        registrar_evento(cur, "LOGIN", "rg.usuarios", str(u["id"]))
    usuario, sessao = buscar_sessao(token, tocar=False)
    resposta = make_response(jsonify({"usuario": usuario, "csrf_token": sessao["csrf_token"]}))
    definir_cookie(resposta, token)
    return resposta


@bp.post("/auth/logout")
def logout():
    token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    if token:
        with db.transacao(sistema=True, usuario_id=g.usuario["id"] if g.usuario else None, ip=ip_cliente()) as cur:
            cur.execute("update rg.sessoes set revogada_em = now() where token_hash = %s and revogada_em is null"
                        " returning usuario_id", (hash_token(token),))
            linha = cur.fetchone()
            if linha:
                registrar_evento(cur, "LOGOUT", "rg.usuarios", str(linha["usuario_id"]))
    resposta = make_response(jsonify({"ok": True}))
    remover_cookie(resposta)
    return resposta


@bp.get("/auth/me")
@requer_login
def me():
    return jsonify({"usuario": g.usuario, "csrf_token": g.sessao["csrf_token"]})


@bp.post("/auth/cadastro")
@limiter.limit("5 per hour; 20 per day")
def cadastro():
    cfg = current_app.config
    dados = validar(corpo_json(), [
        Campo("nome", "texto", obrigatorio=True, min_len=3, max_len=120, rotulo="Nome completo"),
        Campo("email", "email", obrigatorio=True, rotulo="E-mail institucional"),
        Campo("setor_codigo", "texto", obrigatorio=True, max_len=40, rotulo="Setor"),
        Campo("papel", "escolha", obrigatorio=True, escolhas=("solicitante", "gestor", "comprador", "financeiro", "recebimento"),
              rotulo="Perfil de acesso"),
        Campo("cargo", "texto", max_len=80, rotulo="Cargo"),
        Campo("telefone", "texto", max_len=20, rotulo="Telefone"),
        Campo("senha", "texto", obrigatorio=True, max_len=128, rotulo="Senha"),
        Campo("consentimento", "bool", obrigatorio=True, rotulo="Consentimento"),
    ])
    if not dados["consentimento"]:
        raise ValidacaoError({"consentimento": "É necessário aceitar o termo de uso e privacidade"})
    telefone = somente_digitos(dados.get("telefone"))
    if telefone and not 10 <= len(telefone) <= 11:
        raise ValidacaoError({"telefone": "Informe DDD + número"})
    _checar_senha_nova(dados["senha"], email=dados["email"], nome=dados["nome"])

    with db.transacao(sistema=True, ip=ip_cliente()) as cur:
        cur.execute("select operacional from rg.setores where codigo = %s and ativo", (dados["setor_codigo"],))
        setor = cur.fetchone()
        if not setor:
            raise ValidacaoError({"setor_codigo": "Setor inválido"})
        if dados["papel"] in ("gestor", "solicitante") and not setor["operacional"]:
            raise ValidacaoError({"setor_codigo": "Solicitantes e gestores devem pertencer a um setor que abre solicitações"})
        cur.execute("select 1 from rg.usuarios where lower(email) = %s", (dados["email"],))
        if cur.fetchone():
            registrar_evento(cur, "CADASTRO_DUPLICADO", "rg.usuarios", None)
        else:
            cur.execute(
                """insert into rg.usuarios (email, nome, setor_codigo, cargo, papel, status, telefone_cript, senha_hash,
                                            consentimento_lgpd_em, consentimento_versao)
                   values (%s, %s, %s, %s, %s, 'pendente', %s, %s, now(), %s) returning id""",
                (dados["email"], dados["nome"], dados["setor_codigo"], dados.get("cargo"), dados["papel"],
                 cofre.cifrar_texto(telefone), senhas.gerar_hash(dados["senha"]), cfg["LGPD_TERMO_VERSAO"]),
            )
            novo = cur.fetchone()
            cur.execute("insert into rg.senhas_historico (usuario_id, senha_hash) select id, senha_hash"
                        " from rg.usuarios where id = %s", (novo["id"],))
    # Resposta idêntica para e-mails novos e existentes (evita enumeração de contas)
    return jsonify({"mensagem": "Cadastro recebido. Você será notificado após a análise do administrador."}), 202


@bp.post("/auth/senha")
@requer_login
@limiter.limit("10 per hour")
def trocar_senha():
    dados = validar(corpo_json(), [
        Campo("senha_atual", "texto", obrigatorio=True, max_len=128, rotulo="Senha atual"),
        Campo("nova_senha", "texto", obrigatorio=True, max_len=128, rotulo="Nova senha"),
    ])
    u = g.usuario
    with tx() as cur:
        cur.execute("select senha_hash from rg.usuarios where id = %s", (u["id"],))
        atual = cur.fetchone()["senha_hash"]
        if not senhas.verificar(atual, dados["senha_atual"]):
            registrar_evento(cur, "TROCA_SENHA_FALHA", "rg.usuarios", u["id"])
            falhou = True
        else:
            falhou = False
    if falhou:
        raise ValidacaoError({"senha_atual": "Senha atual incorreta"})
    try:
        _checar_senha_nova(dados["nova_senha"], email=u["email"], nome=u["nome"])
    except ValidacaoError as exc:
        exc.campos = {"nova_senha": exc.campos.get("senha")}
        raise
    with tx() as cur:
        cur.execute("select senha_hash from rg.senhas_historico where usuario_id = %s"
                    " order by criado_em desc, id desc limit %s", (u["id"], current_app.config["SENHA_HISTORICO"]))
        anteriores = [r["senha_hash"] for r in cur.fetchall()] + [atual]
        if senhas.senha_reutilizada(dados["nova_senha"], anteriores):
            raise ValidacaoError({"nova_senha": "Não reutilize nenhuma das últimas 5 senhas"})
        novo_hash = senhas.gerar_hash(dados["nova_senha"])
        cur.execute("update rg.usuarios set senha_hash = %s, senha_alterada_em = now(),"
                    " troca_senha_obrigatoria = false where id = %s", (novo_hash, u["id"]))
        cur.execute("insert into rg.senhas_historico (usuario_id, senha_hash) values (%s, %s)", (u["id"], novo_hash))
        cur.execute("update rg.sessoes set revogada_em = now() where usuario_id = %s and id <> %s"
                    " and revogada_em is null", (u["id"], g.sessao["id"]))
        registrar_evento(cur, "TROCA_SENHA", "rg.usuarios", u["id"])
    return jsonify({"mensagem": "Senha alterada. As demais sessões foram encerradas."})


@bp.get("/auth/perfil")
@requer_login
def perfil():
    with tx() as cur:
        cur.execute("""select u.id, u.nome, u.email, u.cargo, u.papel, u.setor_codigo, st.nome as setor_nome,
                              u.telefone_cript, u.ultimo_login_em, u.senha_alterada_em, u.criado_em,
                              u.consentimento_lgpd_em, u.consentimento_versao
                         from rg.usuarios u join rg.setores st on st.codigo = u.setor_codigo where u.id = %s""",
                    (g.usuario["id"],))
        p = cur.fetchone()
    p["telefone"] = cofre.decifrar_texto(p.pop("telefone_cript"))
    return jsonify(p)


@bp.patch("/auth/perfil")
@requer_login
def atualizar_perfil():
    dados = validar(corpo_json(), [
        Campo("nome", "texto", min_len=3, max_len=120, rotulo="Nome"),
        Campo("cargo", "texto", max_len=80, rotulo="Cargo"),
        Campo("telefone", "texto", max_len=20, rotulo="Telefone"),
    ], parcial=True)
    if "nome" in dados and not dados["nome"]:
        raise ValidacaoError({"nome": "Nome é obrigatório"})
    campos = {}
    if "nome" in dados:
        campos["nome"] = dados["nome"]
    if "cargo" in dados:
        campos["cargo"] = dados["cargo"]
    if "telefone" in dados:
        tel = somente_digitos(dados["telefone"])
        if tel and not 10 <= len(tel) <= 11:
            raise ValidacaoError({"telefone": "Informe DDD + número"})
        campos["telefone_cript"] = cofre.cifrar_texto(tel)
    if campos:
        with tx() as cur:
            sets = ", ".join(f"{k} = %s" for k in campos)
            cur.execute(f"update rg.usuarios set {sets} where id = %s", (*campos.values(), g.usuario["id"]))
    return perfil()


@bp.get("/auth/sessoes")
@requer_login
def sessoes():
    with tx() as cur:
        cur.execute("""select id, ip, user_agent, criado_em, ultimo_acesso_em, expira_em
                         from rg.sessoes where usuario_id = %s and revogada_em is null and expira_em > now()
                        order by ultimo_acesso_em desc""", (g.usuario["id"],))
        itens = cur.fetchall()
    for s in itens:
        s["atual"] = str(s["id"]) == g.sessao["id"]
    return jsonify({"itens": itens})


@bp.delete("/auth/sessoes/<uuid:sessao_id>")
@requer_login
def encerrar_sessao(sessao_id):
    with tx() as cur:
        cur.execute("update rg.sessoes set revogada_em = now() where id = %s and usuario_id = %s"
                    " and revogada_em is null", (str(sessao_id), g.usuario["id"]))
        if cur.rowcount != 1:
            raise ApiError("Sessão não encontrada", 404, "nao_encontrado")
        registrar_evento(cur, "SESSAO_ENCERRADA", "rg.sessoes", str(sessao_id))
    return jsonify({"ok": True})


@bp.get("/auth/meus-dados")
@requer_login
@limiter.limit("10 per hour")
def meus_dados():
    """Portabilidade (LGPD art. 18): exporta os dados pessoais do titular."""
    uid = g.usuario["id"]
    with tx() as cur:
        cur.execute("""select id, nome, email, cargo, papel, setor_codigo, status, telefone_cript, criado_em,
                              ultimo_login_em, senha_alterada_em, consentimento_lgpd_em, consentimento_versao
                         from rg.usuarios where id = %s""", (uid,))
        perfil_ = cur.fetchone()
        perfil_["telefone"] = cofre.decifrar_texto(perfil_.pop("telefone_cript"))
        cur.execute("select ip, user_agent, criado_em, ultimo_acesso_em, revogada_em from rg.sessoes"
                    " where usuario_id = %s order by criado_em desc limit 200", (uid,))
        sessoes_ = cur.fetchall()
        cur.execute("select codigo, titulo, status, criado_em from rg.solicitacoes where solicitante_id = %s"
                    " order by criado_em desc", (uid,))
        solicitacoes = cur.fetchall()
        cur.execute("""select s.codigo, a.acao, a.ip, a.assinado_em, a.hash_autenticidade
                         from rg.assinaturas a join rg.solicitacoes s on s.id = a.solicitacao_id
                        where a.usuario_id = %s order by a.assinado_em desc""", (uid,))
        assinaturas_ = cur.fetchall()
        cur.execute("select titulo, mensagem, lida, criado_em from rg.notificacoes where destinatario_id = %s"
                    " order by criado_em desc limit 500", (uid,))
        notificacoes = cur.fetchall()
        registrar_evento(cur, "EXPORTACAO_DADOS_TITULAR", "rg.usuarios", uid)
    resposta = jsonify({"titular": perfil_, "sessoes": sessoes_, "solicitacoes_abertas": solicitacoes,
                        "assinaturas": assinaturas_, "notificacoes": notificacoes})
    resposta.headers["Content-Disposition"] = 'attachment; filename="meus-dados-rg-hospital.json"'
    return resposta
