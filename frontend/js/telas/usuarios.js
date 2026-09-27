// Usuários e perfis: cadastros, perfis de acesso, matriz de permissões, alçadas e setores.
// Administrador gerencia; Auditoria consulta em modo somente leitura.
import { api } from "../api.js";
import { estado, ouvir, rotulo } from "../estado.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, dadosFormulario, mostrarErrosCampos, debounce, iniciais } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import {
  abas, aviso, badgePapel, badgeSetor, badgeUsuario, cabecalho, carregandoBloco, comCarregamento, confirmar, formato,
  modal, opcoes, opcoesSetores, paginacao, pode, toast, toastErro, vazio, erroTela, ICONE_PAPEL,
} from "../ui/componentes.js";

const DESCRICAO_PARAMETRO = {
  alcada_diretoria: ["Alçada da Diretoria (R$)", "Solicitações e pedidos a partir deste valor exigem aprovação da Diretoria."],
  minimo_cotacoes: ["Mínimo de propostas por cotação", "Abaixo disso, a escolha do fornecedor exige justificativa."],
  dias_alerta_entrega: ["Antecedência de alerta de entrega (dias)", "Entregas previstas dentro deste prazo aparecem nos alertas."],
};

export async function montar({ raiz, consulta }) {
  const admin = pode("usuario.gerenciar");
  let aba = ["perfis", "parametros", "setores"].includes(consulta.aba) ? consulta.aba : "usuarios";
  const f = { status: consulta.status ?? (admin ? "pendente" : "aprovado"), q: consulta.q || "", papel: consulta.papel || "", pagina: 1 };
  if (consulta.q && consulta.status === undefined) f.status = "";
  if (consulta.status === "todos") f.status = "";
  let itens = [];

  renderizar(raiz, html`${cabecalho({ titulo: "Usuários e perfis", sub: admin ? "Aprovação de cadastros, perfis de acesso, alçadas e setores" : "Consulta de usuários, perfis e permissões (somente leitura)" })}
    <section class="cartao">${abas([
      { valor: "usuarios", rotulo: "Usuários", icone: "usuarios" }, { valor: "perfis", rotulo: "Perfis e permissões", icone: "escudo" },
      { valor: "parametros", rotulo: "Alçadas e parâmetros", icone: "engrenagem" }, { valor: "setores", rotulo: "Setores", icone: "predio" },
    ], aba, { nome: "aba-principal" })}<div id="corpo-aba"></div></section>`);
  const corpo = raiz.querySelector("#corpo-aba");

  // ------------------------------------------------------------ usuários
  async function abaUsuarios() {
    renderizar(corpo, html`<div id="abas-status"></div>
      <form class="barra-filtros" role="search" id="f-usu">
        <label class="busca"><span class="sr-only">Buscar</span>${icone("busca")}<input class="entrada" type="search" name="q" value="${f.q}" placeholder="Nome ou e-mail"></label>
        <select class="entrada" name="papel" aria-label="Perfil">${opcoes(estado.meta.rotulos.papel, f.papel, { vazio: "Todos os perfis" })}</select>
      </form><div id="lista-usu" aria-live="polite">${carregandoBloco(6)}</div>`);
    const form = corpo.querySelector("#f-usu");
    form.addEventListener("submit", (e) => e.preventDefault());
    form.addEventListener("input", debounce(() => { f.q = form.q.value.trim(); f.papel = form.papel.value; f.pagina = 1; atualizarConsulta({ q: f.q, papel: f.papel }); carregarUsuarios(); }, 300));
    await carregarUsuarios();
  }

  async function carregarUsuarios() {
    const alvo = corpo.querySelector("#lista-usu");
    try {
      const d = await api.get("/usuarios", { status: f.status, q: f.q, papel: f.papel, pagina: f.pagina });
      itens = d.itens;
      const total = Object.values(d.contagem_status).reduce((a, b) => a + b, 0);
      renderizar(corpo.querySelector("#abas-status"), abas([["pendente", "Pendentes"], ["aprovado", "Ativos"], ["suspenso", "Suspensos"], ["rejeitado", "Rejeitados"], ["", "Todos"]]
        .map(([v, r]) => ({ valor: v, rotulo: r, qtd: v ? d.contagem_status[v] || 0 : total, critico: v === "pendente" })), f.status, { nome: "status" }));
      if (!itens.length) { renderizar(alvo, vazio(f.status === "pendente" ? "Nenhum cadastro pendente" : "Nenhum usuário encontrado", "", "", "usuarios")); return; }
      renderizar(alvo, html`<div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Usuário</th><th>Perfil</th><th>Setor</th><th>Situação</th><th>Último acesso</th>${admin ? html`<th class="col-acao"><span class="sr-only">Ações</span></th>` : ""}</tr></thead>
        <tbody>${itens.map((u) => html`<tr>
          <td class="principal-td"><div class="linha-flex"><span class="avatar" aria-hidden="true">${iniciais(u.nome)}</span>
            <span class="principal-celula"><strong>${u.nome}</strong><small>${u.email}${u.cargo ? ` · ${u.cargo}` : ""}</small></span></div></td>
          <td data-rotulo="Perfil">${badgePapel(u.papel)}${u.status === "pendente" ? html`<br><small class="texto-3">perfil solicitado</small>` : ""}</td>
          <td data-rotulo="Setor">${badgeSetor(u.setor_codigo, u.setor_nome, u.setor_cor)}</td>
          <td data-rotulo="Situação">${badgeUsuario(u.status)}${u.bloqueado_ate && new Date(u.bloqueado_ate) > new Date() ? html` <span class="badge perigo">${icone("cadeado")}Bloqueado</span>` : ""}
            ${u.status === "pendente" ? html`<br><small class="texto-3">cadastrado ${formato.relativo(u.criado_em)}</small>` : ""}</td>
          <td data-rotulo="Último acesso" class="texto-3 pequeno">${u.ultimo_login_em ? formato.relativo(u.ultimo_login_em) : "Nunca"}</td>
          ${admin ? html`<td class="col-acao"><div class="grupo-botoes">${u.status === "pendente"
            ? html`<button class="botao sucesso pequeno" data-aprovar="${u.id}">${icone("check")}Aprovar</button><button class="botao secundario pequeno" data-rejeitar="${u.id}">Rejeitar</button>`
            : u.id !== estado.usuario.id && !u.anonimizado_em ? html`<button class="botao secundario pequeno" data-gerenciar="${u.id}">${icone("editar")}Gerenciar</button>` : ""}</div></td>` : ""}
        </tr>`)}</tbody></table></div>${paginacao(d)}`);
    } catch (e) { alvo.replaceChildren(erroTela(e, carregarUsuarios)); }
  }

  function modalAprovar(u) {
    const m = modal({
      titulo: `Aprovar acesso de ${u.nome}`,
      conteudo: html`<form id="f-aprovar" class="pilha" novalidate>
        <p class="texto-2">${u.email} solicitou acesso como <strong>${rotulo("papel", u.papel)}</strong> no setor <strong>${u.setor_nome}</strong>. Confirme ou ajuste antes de liberar.</p>
        <div class="form-grade"><div class="campo col-6"><label for="ap-papel">Perfil de acesso</label><select id="ap-papel" name="papel">${opcoes(estado.meta.rotulos.papel, u.papel)}</select></div>
        <div class="campo col-6"><label for="ap-setor">Setor</label><select id="ap-setor" name="setor_codigo">${opcoesSetores(estado.meta.setores, u.setor_codigo)}</select></div></div>
        <div data-descricao>${aviso("info", rotulo("papel", u.papel), estado.meta.rotulos.papel_descricao[u.papel])}</div>
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao sucesso" type="submit" form="f-aprovar">${icone("check")}Aprovar acesso</button>`,
    });
    const form = m.el.querySelector("#f-aprovar");
    form.papel.addEventListener("change", () => renderizar(m.el.querySelector("[data-descricao]"), aviso("info", rotulo("papel", form.papel.value), estado.meta.rotulos.papel_descricao[form.papel.value])));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await comCarregamento(m.el.querySelector('button[type="submit"]'), api.post(`/usuarios/${u.id}/aprovar`, dadosFormulario(form)));
        m.fechar(); toast("sucesso", "Acesso aprovado", `${u.nome} foi notificado.`); carregarUsuarios();
      } catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
  }

  function modalGerenciar(u) {
    const m = modal({
      titulo: u.nome, sub: u.email, largo: true,
      conteudo: html`<div class="pilha">
        <dl class="pares"><div><dt>Situação</dt><dd>${badgeUsuario(u.status)}</dd></div><div><dt>Perfil</dt><dd>${badgePapel(u.papel)}</dd></div>
          <div><dt>Cadastro</dt><dd>${formato.data(u.criado_em)}</dd></div><div><dt>Último acesso</dt><dd>${u.ultimo_login_em ? formato.dataHora(u.ultimo_login_em) : "Nunca"}</dd></div></dl>
        ${u.status === "rejeitado" && u.motivo_rejeicao ? aviso("perigo", "Motivo da rejeição", u.motivo_rejeicao) : ""}
        ${u.status !== "rejeitado" ? html`<form id="f-ger" class="form-grade" novalidate>
          <div class="campo col-6"><label for="g-papel">Perfil</label><select id="g-papel" name="papel">${opcoes(estado.meta.rotulos.papel, u.papel)}</select></div>
          <div class="campo col-6"><label for="g-setor">Setor</label><select id="g-setor" name="setor_codigo">${opcoesSetores(estado.meta.setores, u.setor_codigo)}</select></div>
          <div class="campo col-6"><label for="g-cargo">Cargo</label><input id="g-cargo" name="cargo" value="${u.cargo ?? ""}" maxlength="80"></div>
          <div class="col-6"><button class="botao" type="submit">${icone("check")}Salvar perfil</button></div>
          <p class="ajuda">Alterações de perfil ou setor encerram as sessões ativas do usuário.</p></form>` : ""}
        <hr><h3>Segurança e LGPD</h3>
        <div class="grupo-botoes">
          ${u.status === "aprovado" ? html`<button class="botao secundario" data-redefinir>${icone("chave")}Redefinir senha</button>
            <button class="botao alerta" data-suspender>${icone("cadeado")}Suspender acesso</button>` : ""}
          ${u.status === "suspenso" ? html`<button class="botao sucesso" data-reativar>${icone("check")}Reativar acesso</button>` : ""}
          ${u.bloqueado_ate && new Date(u.bloqueado_ate) > new Date() ? html`<button class="botao secundario" data-desbloquear>Desbloquear login</button>` : ""}
          ${["suspenso", "rejeitado"].includes(u.status) ? html`<button class="botao perigo" data-anonimizar>${icone("lixeira")}Anonimizar dados pessoais</button>` : ""}
        </div></div>`,
      rodape: html`<button class="botao secundario" data-fechar>Fechar</button>`,
    });
    const form = m.el.querySelector("#f-ger");
    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = dadosFormulario(form);
      if (!d.cargo) d.cargo = null;
      try { await comCarregamento(form.querySelector("button"), api.patch(`/usuarios/${u.id}`, d)); m.fechar(); toast("sucesso", "Perfil atualizado"); carregarUsuarios(); }
      catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
    const atualizarStatus = async (status, titulo, texto) => {
      const r = await confirmar({ titulo, mensagem: texto, rotuloConfirmar: titulo, tom: status === "suspenso" ? "perigo" : "sucesso" });
      if (!r.confirmado) return;
      try { await api.patch(`/usuarios/${u.id}`, { status }); m.fechar(); toast("sucesso", titulo); carregarUsuarios(); } catch (err) { toastErro(err); }
    };
    on(m.el, "click", "[data-suspender]", () => atualizarStatus("suspenso", "Suspender acesso", "As sessões ativas serão encerradas imediatamente."));
    on(m.el, "click", "[data-reativar]", () => atualizarStatus("aprovado", "Reativar acesso", "O usuário poderá entrar novamente."));
    on(m.el, "click", "[data-desbloquear]", async () => { try { await api.post(`/usuarios/${u.id}/desbloquear`); m.fechar(); toast("sucesso", "Login desbloqueado"); carregarUsuarios(); } catch (err) { toastErro(err); } });
    on(m.el, "click", "[data-redefinir]", async () => {
      const r = await confirmar({ titulo: "Redefinir senha", mensagem: "Uma senha temporária será gerada. O usuário deverá trocá-la no próximo acesso e todas as sessões serão encerradas.", rotuloConfirmar: "Gerar senha temporária" });
      if (!r.confirmado) return;
      try {
        const res = await api.post(`/usuarios/${u.id}/redefinir-senha`);
        m.fechar();
        modal({ titulo: "Senha temporária gerada", conteudo: html`<div class="pilha">${aviso("alerta", "Exibida somente agora", res.mensagem)}
          <div class="linha-flex"><code class="mono-hash" id="senha-temp">${res.senha_temporaria}</code><button class="botao secundario pequeno" data-copiar>${icone("copiar")}Copiar</button></div></div>`,
          rodape: html`<button class="botao" data-fechar>Concluir</button>` }).el.querySelector("[data-copiar]").addEventListener("click", () => {
          navigator.clipboard?.writeText(res.senha_temporaria).then(() => toast("sucesso", "Senha copiada"));
        });
      } catch (err) { toastErro(err); }
    });
    on(m.el, "click", "[data-anonimizar]", async () => {
      const r = await confirmar({ titulo: "Anonimizar dados pessoais", tom: "perigo", rotuloConfirmar: "Anonimizar definitivamente",
        mensagem: "Nome, e-mail, telefone e cargo serão substituídos de forma irreversível (LGPD art. 16/18). Registros de auditoria e assinaturas são preservados." });
      if (!r.confirmado) return;
      try { await api.post(`/usuarios/${u.id}/anonimizar`); m.fechar(); toast("sucesso", "Dados anonimizados"); carregarUsuarios(); } catch (err) { toastErro(err); }
    });
  }

  // ------------------------------------------------------------ perfis e permissões
  async function abaPerfis() {
    const [m, u] = await Promise.all([api.get("/permissoes"), api.get("/usuarios", { status: "aprovado", por_pagina: 1 })]);
    const papeis = Object.keys(estado.meta.rotulos.papel);
    const grupos = [...new Set(m.matriz.map((x) => x.grupo))];
    renderizar(corpo, html`<div class="cartao-corpo pilha">
      <div class="perfis-demo">${papeis.map((p) => html`<div class="perfil-demo" data-papel="${p}"><span class="icone-perfil">${icone(ICONE_PAPEL[p])}</span>
        <span><strong>${rotulo("papel", p)}</strong><span class="nome-perfil">${u.por_papel?.[p] || 0} usuário(s) ativo(s)</span><p>${estado.meta.rotulos.papel_descricao[p]}</p></span></div>`)}</div>
      ${aviso("info", "Segregação de funções", "Quem solicita não aprova a própria compra; o Administrador não aprova compras; o Comprador não aprova o pedido que emite; a Auditoria apenas consulta. As mesmas regras são aplicadas pelo banco de dados (RLS e triggers).")}
    </div>
    <div class="tabela-envoltorio"><table class="tabela matriz densa"><thead><tr><th>Permissão</th>${papeis.map((p) => html`<th title="${rotulo("papel", p)}">${rotulo("papel", p).split(" ")[0]}</th>`)}</tr></thead>
      <tbody>${grupos.map((g) => html`<tr><th colspan="${papeis.length + 1}" class="etiqueta">${g}</th></tr>${m.matriz.filter((x) => x.grupo === g).map((x) => html`<tr><td>${x.descricao}</td>
        ${papeis.map((p) => html`<td>${x.perfis.includes(p) ? html`<span class="sim" aria-label="Permitido">${icone("check")}</span>` : html`<span class="nao" aria-label="Não permitido">—</span>`}</td>`)}</tr>`)}`)}</tbody></table></div>`);
  }

  // ------------------------------------------------------------ parâmetros
  async function abaParametros() {
    const r = await api.get("/configuracoes");
    renderizar(corpo, html`<div class="cartao-corpo pilha">
      ${aviso("info", "Parâmetros do fluxo de compras", "Alterações valem imediatamente para novas decisões e ficam registradas na trilha de auditoria.")}
      <div class="grade-3">${r.itens.map((c) => { const [titulo, ajuda] = DESCRICAO_PARAMETRO[c.chave] || [c.chave, c.descricao]; return html`<form class="cartao" data-parametro="${c.chave}"><div class="cartao-corpo pilha-sm">
        <div class="campo"><label for="p-${c.chave}">${titulo}</label><input id="p-${c.chave}" class="num" name="valor" inputmode="decimal" value="${formato.entradaDecimal(c.valor, c.chave === "alcada_diretoria" ? 2 : 0)}" ${admin ? "" : html`disabled`}>
          <p class="ajuda">${ajuda}</p></div>
        <p class="minusculo texto-3">Atualizado ${formato.relativo(c.atualizado_em)}${c.atualizado_por_nome ? ` por ${c.atualizado_por_nome}` : ""}</p>
        ${admin ? html`<button class="botao pequeno" type="submit">${icone("check")}Salvar</button>` : ""}</div></form>`; })}</div></div>`);
    on(corpo, "submit", "[data-parametro]", async (e, formP) => {
      e.preventDefault();
      try { await comCarregamento(formP.querySelector("button"), api.patch(`/configuracoes/${formP.dataset.parametro}`, { valor: formP.valor.value })); toast("sucesso", "Parâmetro atualizado"); abaParametros(); }
      catch (err) { toastErro(err); }
    });
  }

  // ------------------------------------------------------------ setores
  function abaSetores() {
    renderizar(corpo, html`<div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Setor</th><th>Centro de custo</th><th>Cor</th><th>Tipo</th><th>Ativo</th>${admin ? html`<th class="col-acao"></th>` : ""}</tr></thead>
      <tbody>${estado.meta.setores.map((s) => html`<tr data-setor="${s.codigo}">
        <td class="principal-td"><input class="entrada" name="nome" value="${s.nome}" maxlength="80" aria-label="Nome do setor ${s.nome}" ${admin ? "" : html`disabled`}></td>
        <td data-rotulo="Centro de custo" class="mono">${s.centro_custo || "—"}</td>
        <td data-rotulo="Cor"><input type="color" name="cor" value="${s.cor}" aria-label="Cor do setor ${s.nome}" ${admin ? "" : html`disabled`}></td>
        <td data-rotulo="Tipo" class="pequeno texto-3">${s.operacional ? "Abre solicitações" : "Administrativo"}</td>
        <td data-rotulo="Ativo"><input type="checkbox" name="ativo" ${s.ativo ? html`checked` : ""} aria-label="Setor ${s.nome} ativo" ${admin ? "" : html`disabled`}></td>
        ${admin ? html`<td class="col-acao"><button class="botao secundario pequeno" data-salvar-setor>Salvar</button></td>` : ""}</tr>`)}</tbody></table></div>`);
  }

  async function carregarAba() {
    atualizarConsulta({ aba: aba === "usuarios" ? "" : aba });
    try {
      if (aba === "usuarios") await abaUsuarios();
      else if (aba === "perfis") await abaPerfis();
      else if (aba === "parametros") await abaParametros();
      else abaSetores();
    } catch (e) { corpo.replaceChildren(erroTela(e, carregarAba)); }
  }

  on(raiz, "click", "[data-aba-principal]", (e, b) => { aba = b.dataset.abaPrincipal; raiz.querySelectorAll("[data-aba-principal]").forEach((x) => x.setAttribute("aria-selected", String(x === b))); carregarAba(); });
  on(corpo, "click", "[data-status]", (e, b) => { f.status = b.dataset.status; f.pagina = 1; atualizarConsulta({ status: f.status || "todos" }); carregarUsuarios(); });
  on(corpo, "click", "[data-aprovar]", (e, b) => modalAprovar(itens.find((u) => u.id === b.dataset.aprovar)));
  on(corpo, "click", "[data-rejeitar]", async (e, b) => {
    const u = itens.find((x) => x.id === b.dataset.rejeitar);
    const r = await confirmar({ titulo: `Rejeitar cadastro de ${u.nome}`, justificativa: "Motivo da rejeição", minimo: 10, rotuloConfirmar: "Rejeitar", tom: "perigo" });
    if (!r.confirmado) return;
    try { await api.post(`/usuarios/${u.id}/rejeitar`, { motivo: r.texto }); toast("sucesso", "Cadastro rejeitado"); carregarUsuarios(); } catch (err) { toastErro(err); }
  });
  on(corpo, "click", "[data-gerenciar]", (e, b) => modalGerenciar(itens.find((u) => u.id === b.dataset.gerenciar)));
  on(corpo, "click", "[data-pagina]", (e, b) => { f.pagina = Number(b.dataset.pagina); carregarUsuarios(); });
  on(corpo, "click", "[data-salvar-setor]", async (e, b) => {
    const tr = b.closest("tr");
    const dados = { nome: tr.querySelector('[name="nome"]').value.trim(), cor: tr.querySelector('[name="cor"]').value.toUpperCase(), ativo: tr.querySelector('[name="ativo"]').checked };
    try {
      const salvo = await comCarregamento(b, api.patch(`/setores/${tr.dataset.setor}`, dados));
      const idx = estado.meta.setores.findIndex((s) => s.codigo === salvo.codigo);
      estado.meta.setores[idx] = { ...estado.meta.setores[idx], ...salvo };
      toast("sucesso", "Setor atualizado");
    } catch (err) { toastErro(err); }
  });

  await carregarAba();
  return { desmontar: ouvir("evento", (ev) => { if (ev.tabela === "usuarios" && aba === "usuarios") carregarUsuarios(); }) };
}
