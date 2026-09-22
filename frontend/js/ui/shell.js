// Estrutura da aplicação autenticada: topbar, menu lateral, notificações, busca global e tema.
import { api } from "../api.js";
import { estado, ouvir, emitir, rotulo } from "../estado.js";
import { navegar } from "../roteador.js";
import { $, html, on, renderizar, iniciais, debounce, escapar } from "./dom.js";
import { icone } from "./icones.js";
import { formato, modal, toast, badgeStatus, badgeSetor } from "./componentes.js";
import { aplicarTema, temaAtual } from "../tema.js";

const MENU = [
  { grupo: "Visão geral" },
  { href: "/", rotulo: "Painel executivo", icone: "painel" },
  { href: "/fila", rotulo: { admin: "Aprovações pendentes", compras: "Fila de cotações", gestor: "Minhas pendências" }, icone: "fila", contador: "fila" },
  { grupo: "Operação" },
  { href: "/solicitacoes", rotulo: "Solicitações", icone: "documento" },
  { href: "/solicitacoes/nova", rotulo: "Nova solicitação", icone: "mais", papeis: ["gestor"] },
  { href: "/servicos", rotulo: "Serviços programados", icone: "agenda" },
  { href: "/fornecedores", rotulo: "Fornecedores", icone: "fornecedor", papeis: ["admin", "compras"] },
  { grupo: "Gestão" },
  { href: "/relatorios", rotulo: "Relatórios", icone: "relatorio" },
  { href: "/usuarios", rotulo: "Usuários e acessos", icone: "usuarios", papeis: ["admin"], contador: "usuarios" },
  { href: "/auditoria", rotulo: "Auditoria", icone: "auditoria", papeis: ["admin"] },
];

let desligadores = [];
let painelAberto = null;
let promptInstalacao = null;

window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  promptInstalacao = e;
  $("#btn-instalar")?.classList.remove("oculto");
});

function itensMenu() {
  const papel = estado.usuario.papel;
  const visiveis = MENU.filter((i) => !i.papeis || i.papeis.includes(papel));
  return visiveis.filter((item, idx) => !item.grupo || (visiveis[idx + 1] && !visiveis[idx + 1].grupo));
}

function rotuloItem(item) {
  return typeof item.rotulo === "object" ? item.rotulo[estado.usuario.papel] : item.rotulo;
}

export function montarShell(raiz) {
  const u = estado.usuario;
  renderizar(raiz, html`
    <a class="pular-conteudo" href="#conteudo">Pular para o conteúdo</a>
    <header class="topbar">
      <button class="topbar-botao apenas-mobile" id="btn-menu" aria-label="Abrir menu" aria-expanded="false" aria-controls="menu-lateral">${icone("menu")}</button>
      <a class="marca" href="/" aria-label="Hospital Rio Grande — Painel">
        <img class="logo-completo" src="/assets/marca/logo-rg-hospital-branca.svg" alt="" width="190" height="30">
        <img class="simbolo" src="/assets/marca/simbolo-rg-branca.svg" alt="" width="32" height="30">
      </a>
      <div class="busca-global">
        <button type="button" class="abrir-busca" id="btn-busca" aria-haspopup="dialog">${icone("busca")}<span>Buscar solicitações, serviços, fornecedores…</span><kbd>Ctrl K</kbd></button>
      </div>
      <button class="topbar-botao oculto" id="btn-instalar" title="Instalar aplicativo" aria-label="Instalar aplicativo">${icone("instalar")}</button>
      <span class="indicador-rt apenas-desktop" id="indicador-rt" title="Tempo real desconectado" role="img" aria-label="Tempo real desconectado"></span>
      <button class="topbar-botao" id="btn-notificacoes" aria-label="Notificações" aria-haspopup="true" aria-expanded="false">${icone("sino")}<span class="contador oculto" id="contador-notificacoes"></span></button>
      <button class="usuario-botao" id="btn-usuario" aria-haspopup="true" aria-expanded="false">
        <span class="avatar" aria-hidden="true">${iniciais(u.nome)}</span>
        <span class="dados"><strong>${u.nome.split(" ")[0]}</strong><small>${rotulo("papel", u.papel)} · ${u.setor_nome}</small></span>
      </button>
    </header>
    <div class="corpo">
      <aside class="sidebar" id="menu-lateral" aria-label="Menu principal">
        <nav>${itensMenu().map((item) => item.grupo
          ? html`<div class="grupo-titulo">${item.grupo}</div>`
          : html`<a class="nav-item" href="${item.href}" title="${rotuloItem(item)}">${icone(item.icone)}<span class="rotulo">${rotuloItem(item)}</span>${item.contador ? html`<span class="contagem oculto" data-contador="${item.contador}"></span>` : ""}</a>`)}
        </nav>
        <div class="sidebar-rodape"><button type="button" id="btn-recolher" aria-label="Recolher menu">${icone("recolher")}<span class="rotulo">Recolher menu</span></button></div>
      </aside>
      <div class="overlay-menu" id="overlay-menu"></div>
      <main class="conteudo" id="conteudo" tabindex="-1"><div class="conteudo-interno" id="tela"></div></main>
    </div>`);

  document.documentElement.dataset.sidebar = lerPreferencia("rg-sidebar") === "recolhida" ? "recolhida" : "expandida";

  const alternarMenu = (aberto) => {
    document.documentElement.dataset.menu = aberto ? "aberto" : "fechado";
    $("#btn-menu").setAttribute("aria-expanded", String(aberto));
  };
  $("#btn-menu").addEventListener("click", () => alternarMenu(document.documentElement.dataset.menu !== "aberto"));
  $("#overlay-menu").addEventListener("click", () => alternarMenu(false));
  $("#menu-lateral").addEventListener("click", (e) => { if (e.target.closest("a")) alternarMenu(false); });
  $("#btn-recolher").addEventListener("click", () => {
    const recolhida = document.documentElement.dataset.sidebar !== "recolhida";
    document.documentElement.dataset.sidebar = recolhida ? "recolhida" : "expandida";
    $("#btn-recolher").setAttribute("aria-label", recolhida ? "Expandir menu" : "Recolher menu");
    gravarPreferencia("rg-sidebar", recolhida ? "recolhida" : "expandida");
  });
  $("#btn-busca").addEventListener("click", abrirBusca);
  $("#btn-notificacoes").addEventListener("click", (e) => { e.stopPropagation(); alternarNotificacoes(); });
  $("#btn-usuario").addEventListener("click", (e) => { e.stopPropagation(); alternarMenuUsuario(); });
  $("#btn-instalar").addEventListener("click", async () => {
    if (!promptInstalacao) return;
    promptInstalacao.prompt();
    await promptInstalacao.userChoice;
    promptInstalacao = null;
    $("#btn-instalar").classList.add("oculto");
  });
  if (promptInstalacao) $("#btn-instalar").classList.remove("oculto");

  const teclas = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); abrirBusca(); }
    if (e.key === "Escape") { fecharPainel(); alternarMenu(false); }
  };
  document.addEventListener("keydown", teclas);
  document.addEventListener("click", cliqueFora);

  desligadores = [
    () => document.removeEventListener("keydown", teclas),
    () => document.removeEventListener("click", cliqueFora),
    ouvir("tempo-real", (on_) => {
      const el = $("#indicador-rt");
      if (!el) return;
      el.classList.toggle("on", on_);
      const t = on_ ? "Tempo real conectado" : "Tempo real desconectado";
      el.title = t;
      el.setAttribute("aria-label", t);
    }),
    ouvir("evento", (ev) => {
      if (ev.tabela === "notificacoes") atualizarContadores(true);
      else if (ev.tabela === "usuarios" || ev.tabela === "solicitacoes") atualizarContadores(false);
    }),
    ouvir("consulta-periodica", () => atualizarContadores(false)),
  ];
  atualizarContadores(false);
}

export function desmontarShell() {
  desligadores.forEach((fn) => fn());
  desligadores = [];
  fecharPainel();
}

export function marcarMenuAtivo(caminho) {
  document.querySelectorAll(".nav-item").forEach((a) => {
    const href = a.getAttribute("href");
    const ativo = href === "/" ? caminho === "/" : caminho === href || (caminho.startsWith(href + "/") && !(href === "/solicitacoes" && caminho === "/solicitacoes/nova"));
    if (ativo) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

let ultimaContagem = null;
async function atualizarContadores(avisarNovas) {
  try {
    const n = await api.get("/notificacoes", { nao_lidas: 1, limite: 1 });
    estado.naoLidas = n.nao_lidas;
    const el = $("#contador-notificacoes");
    if (el) {
      el.textContent = n.nao_lidas > 99 ? "99+" : n.nao_lidas;
      el.classList.toggle("oculto", !n.nao_lidas);
      $("#btn-notificacoes").setAttribute("aria-label", `Notificações (${n.nao_lidas} não lidas)`);
    }
    if (avisarNovas && ultimaContagem !== null && n.nao_lidas > ultimaContagem && n.itens[0]) {
      const item = n.itens[0];
      toast({ sucesso: "sucesso", erro: "erro", alerta: "alerta" }[item.tipo] || "info", item.titulo, item.mensagem);
    }
    ultimaContagem = n.nao_lidas;
    const fila = await api.get("/solicitacoes", { fila: 1, por_pagina: 1 });
    definirContador("fila", fila.total);
    if (estado.usuario.papel === "admin") {
      const us = await api.get("/usuarios", { status: "pendente", por_pagina: 1 });
      definirContador("usuarios", us.total);
    }
  } catch { /* silencioso: contadores são auxiliares */ }
}

function definirContador(chave, valor) {
  const el = document.querySelector(`[data-contador="${chave}"]`);
  if (!el) return;
  el.textContent = valor > 99 ? "99+" : valor;
  el.classList.toggle("oculto", !valor);
}

// ------------------------------------------------------------- painéis suspensos
function fecharPainel() {
  if (!painelAberto) return;
  painelAberto.el.remove();
  painelAberto.botao?.setAttribute("aria-expanded", "false");
  painelAberto = null;
}

function cliqueFora(e) {
  if (painelAberto && !painelAberto.el.contains(e.target)) fecharPainel();
}

function abrirPainel(botao, conteudo, classe = "") {
  fecharPainel();
  const el = document.createElement("div");
  el.className = `suspenso ${classe}`;
  el.setAttribute("role", "dialog");
  renderizar(el, conteudo);
  document.body.appendChild(el);
  botao.setAttribute("aria-expanded", "true");
  painelAberto = { el, botao };
  el.addEventListener("click", (e) => e.stopPropagation());
  return el;
}

const ICONE_NOTIF = { sucesso: "check_circulo", erro: "x_circulo", alerta: "alerta", info: "info" };

export function itemNotificacao(n) {
  return html`<a class="item-notificacao ${n.tipo} ${n.lida ? "" : "nao-lida"}" href="${n.link || "/notificacoes"}" data-notificacao="${n.id}">
    <span class="icone-n">${icone(ICONE_NOTIF[n.tipo] || "info")}</span>
    <span><span class="n-titulo">${n.titulo}</span><br><span class="n-msg">${n.mensagem}</span><br><time datetime="${n.criado_em}">${formato.relativo(n.criado_em)}</time></span>
  </a>`;
}

async function alternarNotificacoes() {
  const botao = $("#btn-notificacoes");
  if (painelAberto?.botao === botao) { fecharPainel(); return; }
  const el = abrirPainel(botao, html`<div class="cab"><h2>Notificações</h2><button class="botao fantasma pequeno" data-todas>Marcar todas como lidas</button></div>
    <div class="lista" aria-live="polite"><div class="cartao-corpo"><div class="esqueleto"></div></div></div>
    <div class="rodape"><a href="/notificacoes">Ver todas</a></div>`);
  el.setAttribute("aria-label", "Notificações");
  try {
    const dados = await api.get("/notificacoes", { limite: 15 });
    renderizar(el.querySelector(".lista"), dados.itens.length
      ? html`${dados.itens.map(itemNotificacao)}`
      : html`<div class="vazio">${icone("sino")}<p>Nenhuma notificação.</p></div>`);
  } catch (e) {
    renderizar(el.querySelector(".lista"), html`<p class="cartao-corpo texto-3">${e.message}</p>`);
  }
  on(el, "click", "[data-notificacao]", (e, alvo) => {
    api.post(`/notificacoes/${alvo.dataset.notificacao}/lida`).then(() => atualizarContadores(false)).catch(() => {});
    fecharPainel();
  });
  on(el, "click", "[data-todas]", async () => {
    await api.post("/notificacoes/lidas");
    el.querySelectorAll(".nao-lida").forEach((n) => n.classList.remove("nao-lida"));
    atualizarContadores(false);
  });
}

function alternarMenuUsuario() {
  const botao = $("#btn-usuario");
  if (painelAberto?.botao === botao) { fecharPainel(); return; }
  const u = estado.usuario;
  const tema = temaAtual();
  const el = abrirPainel(botao, html`<div class="menu-usuario">
      <div class="cab"><span class="avatar" aria-hidden="true">${iniciais(u.nome)}</span><div><strong>${u.nome}</strong><br><span class="pequeno texto-3">${u.email}</span></div></div>
      <a class="opcao" href="/perfil">${icone("perfil")}Meu perfil e segurança</a>
      <a class="opcao" href="/notificacoes">${icone("sino")}Notificações</a>
      <div class="tema"><div class="pequeno texto-3 negrito" id="rot-tema">Aparência</div>
        <div class="segmentado" role="radiogroup" aria-labelledby="rot-tema">
          ${[["light", "Claro", "sol"], ["dark", "Escuro", "lua"], ["system", "Sistema", "monitor"]].map(([v, r]) => html`
            <label><input type="radio" name="tema" value="${v}" ${tema === v ? html`checked` : ""}><span>${r}</span></label>`)}
        </div></div>
      <button class="opcao" data-sair>${icone("sair")}Sair</button>
    </div>`, "menu-usuario-painel");
  el.setAttribute("aria-label", "Menu do usuário");
  el.querySelectorAll('input[name="tema"]').forEach((r) => r.addEventListener("change", () => aplicarTema(r.value)));
  on(el, "click", "a", () => fecharPainel());
  on(el, "click", "[data-sair]", () => { fecharPainel(); emitir("sair"); });
}

// ------------------------------------------------------------- busca global
function abrirBusca() {
  fecharPainel();
  const m = modal({
    titulo: "Buscar na plataforma",
    largo: true,
    conteudo: html`<div class="busca-campo">${icone("busca")}<input type="search" id="campo-busca" placeholder="Digite código (SOL-2026-…), título, fornecedor ou CNPJ" autocomplete="off" aria-label="Termo de busca" autofocus></div>
      <div class="busca-resultados" id="resultados-busca" aria-live="polite"><p class="cartao-corpo texto-3">Digite ao menos 2 caracteres.</p></div>`,
  });
  m.corpo.style.padding = "0";
  const campo = m.el.querySelector("#campo-busca");
  const alvo = m.el.querySelector("#resultados-busca");
  let controlador = null;
  const buscar = debounce(async () => {
    const q = campo.value.trim();
    if (q.length < 2) { renderizar(alvo, html`<p class="cartao-corpo texto-3">Digite ao menos 2 caracteres.</p>`); return; }
    controlador?.abort();
    controlador = new AbortController();
    try {
      const r = await api.get("/busca", { q }, { sinal: controlador.signal });
      const grupos = [];
      if (r.solicitacoes.length) grupos.push(html`<div class="busca-grupo"><h3>Solicitações</h3>${r.solicitacoes.map((s) => html`<a class="busca-item" href="/solicitacoes/${s.id}">${icone("documento")}<span><strong>${s.codigo}</strong> · ${s.titulo}</span><span class="sub">${badgeStatus(s.status)}</span></a>`)}</div>`);
      if (r.servicos.length) grupos.push(html`<div class="busca-grupo"><h3>Serviços programados</h3>${r.servicos.map((s) => html`<a class="busca-item" href="/servicos?servico=${s.id}">${icone("agenda")}<span><strong>${s.codigo}</strong> · ${s.titulo}</span><span class="sub">${formato.data(s.data_programada)}</span></a>`)}</div>`);
      if (r.fornecedores.length) grupos.push(html`<div class="busca-grupo"><h3>Fornecedores</h3>${r.fornecedores.map((f) => html`<a class="busca-item" href="/fornecedores?q=${encodeURIComponent(f.cnpj)}">${icone("fornecedor")}<span>${f.razao_social}</span><span class="sub mono">${formato.cnpj(f.cnpj)}</span></a>`)}</div>`);
      if (r.usuarios.length) grupos.push(html`<div class="busca-grupo"><h3>Usuários</h3>${r.usuarios.map((u) => html`<a class="busca-item" href="/usuarios?q=${encodeURIComponent(u.email)}">${icone("perfil")}<span>${u.nome}</span><span class="sub">${u.email}</span></a>`)}</div>`);
      renderizar(alvo, grupos.length ? html`${grupos}` : html`<p class="cartao-corpo texto-3">Nenhum resultado para “${q}”.</p>`);
    } catch (e) {
      if (e.name !== "AbortError") renderizar(alvo, html`<p class="cartao-corpo texto-3">${e.message}</p>`);
    }
  }, 250);
  campo.addEventListener("input", buscar);
  campo.addEventListener("keydown", (e) => {
    const itens = [...alvo.querySelectorAll(".busca-item")];
    if (!itens.length || !["ArrowDown", "ArrowUp", "Enter"].includes(e.key)) return;
    e.preventDefault();
    let i = itens.findIndex((it) => it.getAttribute("aria-selected") === "true");
    if (e.key === "Enter") { (itens[i] || itens[0]).click(); return; }
    i = e.key === "ArrowDown" ? Math.min(itens.length - 1, i + 1) : Math.max(0, i - 1);
    itens.forEach((it, k) => it.setAttribute("aria-selected", String(k === i)));
    itens[i].scrollIntoView({ block: "nearest" });
  });
  on(alvo, "click", "a", () => m.fechar());
}

export function lerPreferencia(chave) {
  try { return localStorage.getItem(chave); } catch { return null; }
}
export function gravarPreferencia(chave, valor) {
  try { localStorage.setItem(chave, valor); } catch { /* armazenamento indisponível */ }
}

export { navegar, escapar };
