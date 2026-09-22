"""Gestão de usuários e setores (exclusivo da Administração)."""
from __future__ import annotations

import secrets
import string

from flask import Blueprint, g, jsonify, request

from ..db import db
from ..errors import ApiError, NaoEncontrado, ValidacaoError
from ..seguranca import senhas
from ..seguranca.sessao import ip_cliente, registrar_evento, requer_papel, tx
from ..validacao import Campo, validar
from ._util import corpo_json, paginacao

bp = Blueprint("usuarios", __name__)

CAMPOS_LISTA = """u.id, u.nome, u.email, u.cargo, u.papel, u.status, u.setor_codigo, st.nome as setor_nome,
                  st.cor as setor_cor, u.criado_em, u.ultimo_login_em, u.analisado_em, u.motivo_rejeicao,
                  u.bloqueado_ate, u.troca_senha_obrigatoria, u.anonimizado_em, a.nome as analisado_por_nome"""


def _obter(cur, usuario_id: str) -> dict:
    cur.execute(f"""select {CAMPOS_LISTA} from rg.usuarios u join rg.setores st on st.codigo = u.setor_codigo
                    left join rg.v_usuarios_publico a on a.id = u.analisado_por where u.id = %s""", (usuario_id,))
    u = cur.fetchone()
    if not u:
        raise NaoEncontrado("Usuário não encontrado")
    return u


def _validar_setor_papel(cur, papel: str, setor: str) -> None:
    cur.execute("select operacional from rg.setores where codigo = %s and ativo", (setor,))
    s = cur.fetchone()
    if not s:
        raise ValidacaoError({"setor_codigo": "Setor inválido ou inativo"})
    if papel == "gestor" and not s["operacional"]:
        raise ValidacaoError({"setor_codigo": "Gestores devem pertencer a um setor operacional"})


def _revogar_sessoes(usuario_id: str) -> None:
    with db.transacao(sistema=True, usuario_id=g.usuario["id"], ip=ip_cliente()) as cur:
        cur.execute("update rg.sessoes set revogada_em = now() where usuario_id = %s and revogada_em is null",
                    (usuario_id,))


@bp.get("/usuarios")
@requer_papel("admin")
def listar():
    filtros = validar(request.args.to_dict(), [
        Campo("status", "escolha", escolhas=("pendente", "aprovado", "rejeitado", "suspenso")),
        Campo("papel", "escolha", escolhas=("admin", "gestor", "compras")),
        Campo("setor", "texto", max_len=40),
        Campo("q", "texto", max_len=100),
    ])
    pagina, por_pagina = paginacao(50)
    where, params = ["true"], []
    if filtros.get("status"):
        where.append("u.status = %s")
        params.append(filtros["status"])
    if filtros.get("papel"):
        where.append("u.papel = %s")
        params.append(filtros["papel"])
    if filtros.get("setor"):
        where.append("u.setor_codigo = %s")
        params.append(filtros["setor"])
    if filtros.get("q"):
        where.append("(u.nome ilike %s or u.email ilike %s)")
        termo = "%" + filtros["q"].replace("%", r"\%").replace("_", r"\_") + "%"
        params += [termo, termo]
    clausula = " and ".join(where)
    with tx() as cur:
        cur.execute(f"select count(*) as n from rg.usuarios u where {clausula}", params)
        total = cur.fetchone()["n"]
        cur.execute(f"""select {CAMPOS_LISTA} from rg.usuarios u join rg.setores st on st.codigo = u.setor_codigo
                        left join rg.v_usuarios_publico a on a.id = u.analisado_por
                        where {clausula}
                        order by (u.status = 'pendente') desc, u.criado_em desc limit %s offset %s""",
                    (*params, por_pagina, (pagina - 1) * por_pagina))
        itens = cur.fetchall()
        cur.execute("select status, count(*) as n from rg.usuarios group by status")
        contagem = {r["status"]: r["n"] for r in cur.fetchall()}
    return jsonify({"itens": itens, "total": total, "pagina": pagina, "por_pagina": por_pagina,
                    "contagem_status": contagem})


@bp.post("/usuarios/<uuid:usuario_id>/aprovar")
@requer_papel("admin")
def aprovar(usuario_id):
    dados = validar(corpo_json(), [
        Campo("papel", "escolha", obrigatorio=True, escolhas=("admin", "gestor", "compras"), rotulo="Perfil"),
        Campo("setor_codigo", "texto", obrigatorio=True, max_len=40, rotulo="Setor"),
    ])
    with tx() as cur:
        atual = _obter(cur, str(usuario_id))
        if atual["status"] != "pendente":
            raise ApiError("Somente cadastros pendentes podem ser aprovados", 422, "status_invalido")
        _validar_setor_papel(cur, dados["papel"], dados["setor_codigo"])
        cur.execute("""update rg.usuarios set status = 'aprovado', papel = %s, setor_codigo = %s,
                              analisado_por = %s, analisado_em = now(), motivo_rejeicao = null where id = %s""",
                    (dados["papel"], dados["setor_codigo"], g.usuario["id"], str(usuario_id)))
        registrar_evento(cur, "USUARIO_APROVADO", "rg.usuarios", str(usuario_id), dados)
        return jsonify(_obter(cur, str(usuario_id)))


@bp.post("/usuarios/<uuid:usuario_id>/rejeitar")
@requer_papel("admin")
def rejeitar(usuario_id):
    dados = validar(corpo_json(), [Campo("motivo", "texto", obrigatorio=True, min_len=10, max_len=1000,
                                         rotulo="Motivo")])
    with tx() as cur:
        atual = _obter(cur, str(usuario_id))
        if atual["status"] != "pendente":
            raise ApiError("Somente cadastros pendentes podem ser rejeitados", 422, "status_invalido")
        cur.execute("""update rg.usuarios set status = 'rejeitado', analisado_por = %s, analisado_em = now(),
                              motivo_rejeicao = %s where id = %s""",
                    (g.usuario["id"], dados["motivo"], str(usuario_id)))
        registrar_evento(cur, "USUARIO_REJEITADO", "rg.usuarios", str(usuario_id))
        return jsonify(_obter(cur, str(usuario_id)))


@bp.patch("/usuarios/<uuid:usuario_id>")
@requer_papel("admin")
def atualizar(usuario_id):
    dados = validar(corpo_json(), [
        Campo("papel", "escolha", escolhas=("admin", "gestor", "compras"), rotulo="Perfil"),
        Campo("setor_codigo", "texto", max_len=40, rotulo="Setor"),
        Campo("status", "escolha", escolhas=("aprovado", "suspenso"), rotulo="Situação"),
        Campo("nome", "texto", min_len=3, max_len=120, rotulo="Nome"),
        Campo("cargo", "texto", max_len=80, rotulo="Cargo"),
    ], parcial=True)
    dados = {k: v for k, v in dados.items() if v is not None}
    if not dados:
        raise ValidacaoError({"geral": "Nenhuma alteração informada"})
    uid = str(usuario_id)
    with tx() as cur:
        atual = _obter(cur, uid)
        if atual["anonimizado_em"]:
            raise ApiError("Usuário anonimizado não pode ser alterado", 422, "anonimizado")
        if atual["status"] in ("pendente", "rejeitado") and "status" in dados:
            raise ApiError("Use as ações de aprovação/rejeição para cadastros pendentes", 422, "status_invalido")
        _validar_setor_papel(cur, dados.get("papel", atual["papel"]), dados.get("setor_codigo", atual["setor_codigo"]))
        sets = ", ".join(f"{k} = %s" for k in dados)
        cur.execute(f"update rg.usuarios set {sets} where id = %s", (*dados.values(), uid))
        resultado = _obter(cur, uid)
    if dados.get("status") == "suspenso" or "papel" in dados or "setor_codigo" in dados:
        _revogar_sessoes(uid)  # força novo login com as permissões atualizadas
    return jsonify(resultado)


@bp.post("/usuarios/<uuid:usuario_id>/redefinir-senha")
@requer_papel("admin")
def redefinir_senha(usuario_id):
    uid = str(usuario_id)
    if uid == g.usuario["id"]:
        raise ApiError("Use a troca de senha do seu perfil", 422, "proprio_usuario")
    alfabeto = string.ascii_letters + string.digits + "@#$%&*!?"
    while True:
        temporaria = "".join(secrets.choice(alfabeto) for _ in range(16))
        if not senhas.validar_politica(temporaria, minimo=12):
            break
    with tx() as cur:
        atual = _obter(cur, uid)
        if atual["status"] != "aprovado":
            raise ApiError("Somente usuários ativos podem ter a senha redefinida", 422, "status_invalido")
        novo_hash = senhas.gerar_hash(temporaria)
        cur.execute("update rg.usuarios set senha_hash = %s, senha_alterada_em = now(), troca_senha_obrigatoria = true,"
                    " tentativas_falhas = 0, bloqueado_ate = null where id = %s", (novo_hash, uid))
        registrar_evento(cur, "SENHA_REDEFINIDA_ADMIN", "rg.usuarios", uid)
    with db.transacao(sistema=True, usuario_id=g.usuario["id"], ip=ip_cliente()) as cur:
        cur.execute("insert into rg.senhas_historico (usuario_id, senha_hash) values (%s, %s)", (uid, novo_hash))
    _revogar_sessoes(uid)
    return jsonify({"senha_temporaria": temporaria,
                    "mensagem": "Entregue a senha temporária pessoalmente. Ela deverá ser trocada no primeiro acesso."})


@bp.post("/usuarios/<uuid:usuario_id>/desbloquear")
@requer_papel("admin")
def desbloquear(usuario_id):
    with tx() as cur:
        _obter(cur, str(usuario_id))
        cur.execute("update rg.usuarios set tentativas_falhas = 0, bloqueado_ate = null where id = %s",
                    (str(usuario_id),))
        registrar_evento(cur, "USUARIO_DESBLOQUEADO", "rg.usuarios", str(usuario_id))
        return jsonify(_obter(cur, str(usuario_id)))


@bp.post("/usuarios/<uuid:usuario_id>/anonimizar")
@requer_papel("admin")
def anonimizar(usuario_id):
    """Eliminação/anonimização de dados pessoais (LGPD art. 16/18), preservando trilhas de auditoria."""
    uid = str(usuario_id)
    if uid == g.usuario["id"]:
        raise ApiError("Não é possível anonimizar o próprio usuário", 422, "proprio_usuario")
    with tx() as cur:
        atual = _obter(cur, uid)
        if atual["status"] not in ("rejeitado", "suspenso"):
            raise ApiError("Suspenda o usuário antes de anonimizar", 422, "status_invalido")
        if atual["anonimizado_em"]:
            raise ApiError("Usuário já anonimizado", 422, "anonimizado")
        cur.execute(
            """update rg.usuarios set nome = 'Titular anonimizado', email = %s, cargo = null, telefone_cript = null,
                      senha_hash = %s, anonimizado_em = now() where id = %s""",
            (f"anonimizado-{uid}@anonimizado.invalid", senhas.gerar_hash(secrets.token_urlsafe(32)), uid),
        )
        registrar_evento(cur, "USUARIO_ANONIMIZADO", "rg.usuarios", uid)
    with db.transacao(sistema=True, usuario_id=g.usuario["id"], ip=ip_cliente()) as cur:
        cur.execute("delete from rg.senhas_historico where usuario_id = %s", (uid,))
    _revogar_sessoes(uid)
    return jsonify({"ok": True})


@bp.patch("/setores/<codigo>")
@requer_papel("admin")
def atualizar_setor(codigo):
    dados = validar(corpo_json(), [
        Campo("nome", "texto", min_len=2, max_len=80, rotulo="Nome"),
        Campo("cor", "texto", max_len=7, rotulo="Cor",
              validador=lambda v: None if len(v) == 7 and v.startswith("#") else "Use o formato #RRGGBB"),
        Campo("ativo", "bool", rotulo="Ativo"),
    ], parcial=True)
    dados = {k: v for k, v in dados.items() if v is not None}
    if not dados:
        raise ValidacaoError({"geral": "Nenhuma alteração informada"})
    with tx() as cur:
        sets = ", ".join(f"{k} = %s" for k in dados)
        cur.execute(f"update rg.setores set {sets} where codigo = %s returning *", (*dados.values(), codigo))
        setor = cur.fetchone()
        if not setor:
            raise NaoEncontrado("Setor não encontrado")
    return jsonify(setor)
