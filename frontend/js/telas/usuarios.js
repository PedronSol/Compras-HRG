// Gestão de usuários e acessos (Administração): aprovação de cadastros, perfis, suspensão, LGPD e setores.
import { api } from "../api.js";
import { estado, ouvir, rotulo } from "../estado.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, dadosFormulario, mostrarErrosCampos, debounce, iniciais } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { aviso, badgeSetor, badgeUsuario, comCarregamento, confirmar, formato, modal, opcoes, opcoesSetores, paginacao, toast, toastErro, vazio, erroTela } from "../ui/componentes.js";

export async function montar({ raiz, consulta }) {
  const f = { status: consulta.status ?? "pendente", q: consulta.q || "", papel: consulta.papel || "", pagina: Number(consulta.pagina) || 1 };
  if (consulta.q && consulta.status === undefined) f.status = "";
  let itens = [];
  renderizar(raiz, html`
    <div class="cabecalho-pagina"><div class="titulos"><h1>Usuários e acessos</h1><p>Aprovação de cadastros, perfis de acesso (RBAC) e setores.</p></div>
      <button class="botao secundario" data-setores>${icone("predio")}Setores</button></div>
    <section class="cartao">
      <div class="abas" role="tablist" aria-label="Situação do cadastro" id="abas-status">
        ${[["pendente", "Pendentes"], ["aprovado", "Ativos"], ["suspenso", "Suspensos"], ["rejeitado", "Rejeitados"], ["", "Todos"]].map(([v, r]) => html`
          <button class="aba" role="tab" data-status="${v}" aria-selected="${f.status === v}">${r}<span class="n" data-n="${v}"></span></button>`)}
      </div>
      <form class="barra-filtros" role="search" id="f-usu">
        <div class="campo largo"><label for="u-q">Buscar</label><input id="u-q" type="search" name="q" value="${f.q}" placeholder="Nome ou e-mail"></div>
        <div class="campo"><label for="u-papel">Perfil</label><select id="u-papel" name="papel">${opcoes(estado.meta.rotulos.papel, f.papel, { vazio: "Todos" })}</select></div>
      </form>
      <div id="lista-usu" aria-live="polite"></div>
    </section>`);
  const alvo = raiz.querySelector("#lista-usu");

  async function carregar() {
    try {
      const d = await api.get("/usuarios", { status: f.status, q: f.q, papel: f.papel, pagina: f.pagina });
      itens = d.itens;
      const total = Object.values(d.contagem_status).reduce((a, b) => a + b, 0);
      raiz.querySelectorAll("[data-n]").forEach((el) => { el.textContent = el.dataset.n ? d.contagem_status[el.dataset.n] || 0 : total; });
      if (!itens.length) { renderizar(alvo, vazio(f.status === "pendente" ? "Nenhum cadastro pendente" : "Nenhum usuário encontrado")); return; }
      renderizar(alvo, html`<div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Usuário</th><th>Perfil</th><th>Setor</th><th>Situação</th><th>Último acesso</th><th><span class="sr-only">Ações</span></th></tr></thead>
        <tbody>${itens.map((u) => html`<tr>
          <td class="principal" data-rotulo="Usuário"><div class="linha-flex"><span class="avatar" aria-hidden="true">${iniciais(u.nome)}</span>
            <span class="quebra"><strong>${u.nome}</strong><span class="sub">${u.email}${u.cargo ? ` · ${u.cargo}` : ""}</span></span></div></td>
          <td data-rotulo="Perfil">${rotulo("papel", u.papel)}${u.status === "pendente" ? html`<span class="sub">solicitado</span>` : ""}</td>
          <td data-rotulo="Setor">${badgeSetor(u.setor_codigo, u.setor_nome, u.setor_cor)}</td>
          <td data-rotulo="Situação">${badgeUsuario(u.status)}${u.bloqueado_ate && new Date(u.bloqueado_ate) > new Date() ? html` <span class="badge perigo">${icone("cadeado")}Bloqueado</span>` : ""}
            ${u.status === "pendente" ? html`<span class="sub">cadastrado ${formato.relativo(u.criado_em)}</span>` : u.analisado_por_nome ? html`<span class="sub">por ${u.analisado_por_nome}</span>` : ""}</td>
          <td data-rotulo="Último acesso">${u.ultimo_login_em ? formato.relativo(u.ultimo_login_em) : "Nunca"}</td>
          <td data-rotulo="Ações"><div class="grupo-botoes">${u.status === "pendente"
            ? html`<button class="botao sucesso pequeno" data-aprovar="${u.id}">${icone("check")}Aprovar</button><button class="botao secundario pequeno" data-rejeitar="${u.id}">Rejeitar</button>`
            : u.id !== estado.usuario.id && !u.anonimizado_em ? html`<button class="botao secundario pequeno" data-gerenciar="${u.id}">${icone("editar")}Gerenciar</button>` : ""}</div></td>
        </tr>`)}</tbody></table></div>${paginacao(d)}`);
    } catch (e) { alvo.replaceChildren(erroTela(e, carregar)); }
  }

  function modalAprovar(u) {
    const m = modal({
      titulo: `Aprovar acesso de ${u.nome}`,
      conteudo: html`<form id="f-aprovar" class="pilha" novalidate>
        <p class="texto-2">${u.email} solicitou acesso como <strong>${rotulo("papel", u.papel)}</strong> no setor <strong>${u.setor_nome}</strong>. Confirme ou ajuste antes de liberar.</p>
        <div class="form-grade"><div class="campo col-6"><label for="ap-papel">Perfil de acesso</label><select id="ap-papel" name="papel">${opcoes(estado.meta.rotulos.papel, u.papel)}</select></div>
        <div class="campo col-6"><label for="ap-setor">Setor</label><select id="ap-setor" name="setor_codigo">${opcoesSetores(estado.meta.setores, u.setor_codigo)}</select></div></div>
        ${aviso("info", "Isolamento de dados", "Gestores acessam somente o próprio setor; Compras vê apenas solicitações liberadas pela Administração; Administradores têm acesso global.")}
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao sucesso" type="submit" form="f-aprovar">${icone("check")}Aprovar acesso</button>`,
    });
    const form = m.el.querySelector("#f-aprovar");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await comCarregamento(m.el.querySelector('button[type="submit"]'), api.post(`/usuarios/${u.id}/aprovar`, dadosFormulario(form)));
        m.fechar(); toast("sucesso", "Acesso aprovado", `${u.nome} foi notificado.`); carregar();
      } catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
  }

  function modalGerenciar(u) {
    const m = modal({
      titulo: u.nome, largo: true,
      conteudo: html`<div class="pilha">
        <dl class="definicoes"><div><dt>E-mail</dt><dd>${u.email}</dd></div><div><dt>Situação</dt><dd>${badgeUsuario(u.status)}</dd></div>
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
      try { await comCarregamento(form.querySelector("button"), api.patch(`/usuarios/${u.id}`, d)); m.fechar(); toast("sucesso", "Perfil atualizado"); carregar(); }
      catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
    const atualizarStatus = async (status, titulo, texto) => {
      const r = await confirmar({ titulo, mensagem: texto, rotuloConfirmar: titulo, tom: status === "suspenso" ? "perigo" : "sucesso" });
      if (!r.confirmado) return;
      try { await api.patch(`/usuarios/${u.id}`, { status }); m.fechar(); toast("sucesso", titulo); carregar(); } catch (err) { toastErro(err); }
    };
    on(m.el, "click", "[data-suspender]", () => atualizarStatus("suspenso", "Suspender acesso", "As sessões ativas serão encerradas imediatamente."));
    on(m.el, "click", "[data-reativar]", () => atualizarStatus("aprovado", "Reativar acesso", "O usuário poderá entrar novamente."));
    on(m.el, "click", "[data-desbloquear]", async () => { try { await api.post(`/usuarios/${u.id}/desbloquear`); m.fechar(); toast("sucesso", "Login desbloqueado"); carregar(); } catch (err) { toastErro(err); } });
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
      try { await api.post(`/usuarios/${u.id}/anonimizar`); m.fechar(); toast("sucesso", "Dados anonimizados"); carregar(); } catch (err) { toastErro(err); }
    });
  }

  async function modalSetores() {
    const m = modal({
      titulo: "Setores hospitalares", largo: true,
      conteudo: html`<p class="texto-2 pequeno">Cores utilizadas nos indicadores e identificadores. Setores inativos não recebem novas solicitações.</p>
        <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Setor</th><th>Cor</th><th>Tipo</th><th>Ativo</th><th></th></tr></thead>
        <tbody>${estado.meta.setores.map((s) => html`<tr data-setor="${s.codigo}">
          <td><input class="entrada" name="nome" value="${s.nome}" maxlength="80" aria-label="Nome do setor ${s.nome}"></td>
          <td><input type="color" name="cor" value="${s.cor}" aria-label="Cor do setor ${s.nome}"></td>
          <td class="pequeno texto-3">${s.operacional ? "Operacional" : "Administrativo"}</td>
          <td><input type="checkbox" name="ativo" ${s.ativo ? html`checked` : ""} aria-label="Setor ${s.nome} ativo"></td>
          <td><button class="botao secundario pequeno" data-salvar-setor>Salvar</button></td></tr>`)}</tbody></table></div>`,
      rodape: html`<button class="botao secundario" data-fechar>Fechar</button>`,
    });
    on(m.el, "click", "[data-salvar-setor]", async (e, b) => {
      const tr = b.closest("tr");
      const corpo = { nome: tr.querySelector('[name="nome"]').value.trim(), cor: tr.querySelector('[name="cor"]').value.toUpperCase(), ativo: tr.querySelector('[name="ativo"]').checked };
      try {
        const salvo = await comCarregamento(b, api.patch(`/setores/${tr.dataset.setor}`, corpo));
        const idx = estado.meta.setores.findIndex((s) => s.codigo === salvo.codigo);
        estado.meta.setores[idx] = { ...estado.meta.setores[idx], ...salvo };
        toast("sucesso", "Setor atualizado");
      } catch (err) { toastErro(err); }
    });
  }

  on(alvo, "click", "[data-aprovar]", (e, b) => modalAprovar(itens.find((u) => u.id === b.dataset.aprovar)));
  on(alvo, "click", "[data-rejeitar]", async (e, b) => {
    const u = itens.find((x) => x.id === b.dataset.rejeitar);
    const r = await confirmar({ titulo: `Rejeitar cadastro de ${u.nome}`, justificativa: "Motivo da rejeição", minimo: 10, rotuloConfirmar: "Rejeitar", tom: "perigo" });
    if (!r.confirmado) return;
    try { await api.post(`/usuarios/${u.id}/rejeitar`, { motivo: r.texto }); toast("sucesso", "Cadastro rejeitado"); carregar(); } catch (err) { toastErro(err); }
  });
  on(alvo, "click", "[data-gerenciar]", (e, b) => modalGerenciar(itens.find((u) => u.id === b.dataset.gerenciar)));
  on(alvo, "click", "[data-pagina]", (e, b) => { f.pagina = Number(b.dataset.pagina); carregar(); });
  on(raiz, "click", "[data-status]", (e, b) => {
    f.status = b.dataset.status; f.pagina = 1;
    raiz.querySelectorAll("[data-status]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    atualizarConsulta({ status: f.status || "todos" });
    carregar();
  });
  raiz.querySelector("[data-setores]").addEventListener("click", modalSetores);
  const form = raiz.querySelector("#f-usu");
  form.addEventListener("submit", (e) => e.preventDefault());
  form.addEventListener("input", debounce(() => { f.q = form.q.value.trim(); f.papel = form.papel.value; f.pagina = 1; atualizarConsulta({ q: f.q, papel: f.papel }); carregar(); }, 300));
  if (consulta.status === "todos") { f.status = ""; raiz.querySelectorAll("[data-status]").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.status === ""))); }

  await carregar();
  const desligar = ouvir("evento", (ev) => { if (ev.tabela === "usuarios") carregar(); });
  return { desmontar: desligar };
}
