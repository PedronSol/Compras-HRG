// Estrutura autenticada: menu lateral por perfil, barra superior, notificações, busca global e tema.
import { api } from "../api.js";
import { estado, ouvir, emitir, rotulo } from "../estado.js";
import { navegar } from "../roteador.js";
import { $, html, on, renderizar, iniciais, debounce, escapar } from "./dom.js";
import { icone } from "./icones.js";
import { formato, modal, toast, badgeStatus, badgePedido, pode } from "./componentes.js";
import { aplicarTema, temaAtual } from "../tema.js";

const COM_FILA = ["comprador", "solicitante", "gestor", "financeiro", "recebimento", "diretoria"];

const MENU = [
  { grupo: "Visão geral" },
  { href: "/", rotulo: "Painel", icone: "painel" },
  { href: "/pendencias", rotulo: "Minhas pendências", icone: "fila", contador: "fila", se: (p) => COM_FILA.includes(p), critico: true },
  { href: "/alertas", rotulo: "Alertas", icone: "alerta", contador: "alertas" },
  { grupo: "Fluxo de compras" },
  { href: "/solicitacoes", rotulo: "Solicitações", icone: "documento" },
  { href: "/solicitacoes/nova", rotulo: "Nova solicitação", icone: "mais", capacidade: "solicitacao.criar" },
  { href: "/aprovacoes", rotulo: "Aprovações", icone: "carimbo", contador: "aprovacoes", se: (p) => ["gestor", "diretoria", "financeiro", "admin", "auditoria"].includes(p) },
  { href: "/cotacoes", rotulo: "Cotações", icone: "balanca", contador: "cotacoes", se: (p) => ["comprador", "admin", "auditoria", "diretoria"].includes(p) },
  { href: "/pedidos", rotulo: "Pedidos de compra", icone: "pedido", capacidade: "pedido.ver", contador: "pedidos", se: (p) => p !== "recebimento" },
  { href: "/recebimentos", rotulo: "Recebimento", icone: "caminhao", capacidade: "recebimento.ver", contador: "recebimentos" },
  { grupo: "Cadastros" },
  { href: "/fornecedores", rotulo: "Fornecedores", icone: "fornecedor", capacidade: "fornecedor.ver" },
  { href: "/materiais", rotulo: "Materiais e categorias", icone: "caixa", capacidade: "material.ver" },
  { grupo: "Gestão" },
  { href: "/relatorios", rotulo: "Relatórios e indicadores", icone: "relatorio", capacidade: "relatorio.ver" },
  { href: "/auditoria", rotulo: "Auditoria", icone: "auditoria", capacidade: "auditoria.ver" },
  { href: "/usuarios", rotulo: "Usuários e perfis", icone: "usuarios", contador: "usuarios", se: (p) => ["admin", "auditoria"].includes(p) },
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
  const visiveis = MENU.filter((i) => i.grupo || ((!i.capacidade || pode(i.capacidade)) && (!i.se || i.se(papel))));
  return visiveis.filter((item, idx) => !item.grupo || (visiveis[idx + 1] && !visiveis[idx + 1].grupo));
}

export function montarShell(raiz) {
  const u = estado.usuario;
  const demo = estado.meta?.demo;
  renderizar(raiz, html`
    <a class="pular-conteudo" href="#conteudo">Pular para o conteúdo</a>
    <div class="shell">
      <aside class="sidebar" id="menu-lateral" aria-label="Menu principal">
        <a class="sidebar-marca" href="/" aria-label="Hospital Rio Grande — Painel">
          <img class="logo-completo" src="/assets/marca/logo-rg-hospital-branca.svg" alt="" width="188" height="30">
          <img class="simbolo" src="/assets/marca/simbolo-rg-branca.svg" alt="" width="32" height="30">
        </a>
        <div class="sidebar-modulo"><span class="icone-modulo">${icone("carrinho")}</span><span><strong>Compras e Suprimentos</strong><small title="${u.setor_nome}">${u.setor_codigo === "suprimentos" ? rotulo("papel", u.papel) : u.setor_nome}</small></span></div>
        <nav>${itensMenu().map((item) => item.grupo
          ? html`<div class="grupo-titulo">${item.grupo}</div>`
          : html`<a class="nav-item" href="${item.href}" title="${item.rotulo}">${icone(item.icone)}<span class="rotulo">${item.rotulo}</span>${item.contador ? html`<span class="contagem oculto ${item.critico ? "" : ""}" data-contador="${item.contador}"></span>` : ""}</a>`)}
        </nav>
        <div class="sidebar-rodape"><button type="button" id="btn-recolher" aria-label="Recolher menu">${icone("recolher")}<span class="rotulo">Recolher menu</span></button></div>
      </aside>
      <div class="overlay-menu" id="overlay-menu"></div>
      <div class="principal">
        <header class="topbar">
          <button class="icone-botao apenas-mobile" id="btn-menu" aria-label="Abrir menu" aria-expanded="false" aria-controls="menu-lateral">${icone("menu")}</button>
          <div class="busca-global">
            <button type="button" id="btn-busca" aria-haspopup="dialog">${icone("busca")}<span>Buscar solicitação, pedido, fornecedor ou material…</span><kbd>Ctrl K</kbd></button>
          </div>
          <span class="espacador"></span>
          ${demo ? html`<span class="selo-demo" title="Todos os dados exibidos são fictícios">${icone("sparkle")}<span class="rotulo-longo">Demonstração · </span>dados fictícios</span>` : ""}
          <button class="icone-botao oculto" id="btn-instalar" title="Instalar aplicativo" aria-label="Instalar aplicativo">${icone("instalar")}</button>
          <span class="indicador-rt apenas-desktop" id="indicador-rt" title="Atualização em tempo real desconectada" role="img" aria-label="Atualização em tempo real desconectada"></span>
          <button class="icone-botao" id="btn-notificacoes" aria-label="Notificações" aria-haspopup="true" aria-expanded="false">${icone("sino")}<span class="contador oculto" id="contador-notificacoes"></span></button>
          <button class="usuario-botao" id="btn-usuario" aria-haspopup="true" aria-expanded="false">
            <span class="avatar" aria-hidden="true">${iniciais(u.nome)}</span>
            <span class="dados"><strong>${u.nome}</strong><small>${rotulo("papel", u.papel)}</small></span>
          </button>
        </header>
        <main class="conteudo" id="conteudo" tabindex="-1"><div class="conteudo-interno" id="tela"></div></main>
      </div>
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

  const atualizarDepois = debounce(() => atualizarContadores(false), 600);
  desligadores = [
    () => document.removeEventListener("keydown", teclas),
    () => document.removeEventListener("click", cliqueFora),
    ouvir("tempo-real", (ligado) => {
      const el = $("#indicador-rt");
      if (!el) return;
      el.classList.toggle("on", ligado);
      const t = ligado ? "Atualização em tempo real ativa" : "Atualização em tempo real desconectada";
      el.title = t;
      el.setAttribute("aria-label", t);
    }),
    ouvir("evento", (ev) => {
      if (ev.tabela === "notificacoes") atualizarContadores(true);
      else atualizarDepois();
    }),
    ouvir("consulta-periodica", () => atualizarContadores(false)),
    ouvir("atualizar-contadores", () => atualizarContadores(false)),
  ];
  atualizarContadores(false);
}

export function desmontarShell() {
  desligadores.forEach((fn) => fn());
  desligadores = [];
  fecharPainel();
}

export function marcarMenuAtivo(caminho) {
  const itens = [...document.querySelectorAll(".nav-item")];
  const melhor = itens.map((a) => a.getAttribute("href"))
    .filter((href) => (href === "/" ? caminho === "/" : caminho === href || caminho.startsWith(href + "/")))
    .sort((a, b) => b.length - a.length)[0];
  itens.forEach((a) => {
    if (a.getAttribute("href") === melhor) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

let ultimaContagem = null;
async function atualizarContadores(avisarNovas) {
  try {
    const { contadores } = await api.get("/painel/pendencias");
    estado.contadores = contadores;
    estado.naoLidas = contadores.notificacoes;
    const el = $("#contador-notificacoes");
    if (el) {
      el.textContent = contadores.notificacoes > 99 ? "99+" : contadores.notificacoes;
      el.classList.toggle("oculto", !contadores.notificacoes);
      $("#btn-notificacoes").setAttribute("aria-label", `Notificações (${contadores.notificacoes} não lidas)`);
    }
    if (avisarNovas && ultimaContagem !== null && contadores.notificacoes > ultimaContagem) {
      const n = await api.get("/notificacoes", { nao_lidas: 1, limite: 1 });
      const item = n.itens[0];
      if (item) toast({ sucesso: "sucesso", erro: "erro", alerta: "alerta" }[item.tipo] || "info", item.titulo, item.mensagem);
    }
    ultimaContagem = contadores.notificacoes;
    for (const [chave, valor] of Object.entries(contadores)) definirContador(chave, valor);
    emitir("contadores", contadores);
  } catch { /* contadores são auxiliares */ }
}

function definirContador(chave, valor) {
  const el = document.querySelector(`[data-contador="${chave}"]`);
  if (!el) return;
  el.textContent = valor > 99 ? "99+" : valor;
  el.classList.toggle("oculto", !valor);
  el.classList.toggle("critica", chave === "alertas" && valor > 0);
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
    <span><span class="n-titulo">${n.titulo}</span><br><span class="n-msg">${n.mensagem}</span><time datetime="${n.criado_em}">${formato.relativo(n.criado_em)}</time></span>
  </a>`;
}

async function alternarNotificacoes() {
  const botao = $("#btn-notificacoes");
  if (painelAberto?.botao === botao) { fecharPainel(); return; }
  const el = abrirPainel(botao, html`<div class="cab"><h2>Notificações</h2><button class="botao fantasma pequeno" data-todas>${icone("check")}Marcar todas como lidas</button></div>
    <div class="lista" aria-live="polite"><div class="cartao-corpo pilha-sm"><div class="esqueleto"></div><div class="esqueleto"></div></div></div>
    <div class="rodape"><a href="/notificacoes">Ver todas as notificações</a></div>`);
  el.setAttribute("aria-label", "Notificações");
  try {
    const dados = await api.get("/notificacoes", { limite: 15 });
    renderizar(el.querySelector(".lista"), dados.itens.length
      ? html`${dados.itens.map(itemNotificacao)}`
      : html`<div class="vazio compacto"><span class="icone-vazio">${icone("sino")}</span><h3>Tudo em dia</h3><p>Nenhuma notificação por enquanto.</p></div>`);
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
      <div class="cab"><span class="avatar grande" aria-hidden="true">${iniciais(u.nome)}</span><div><strong>${u.nome}</strong><br><span class="pequeno texto-3">${u.cargo || rotulo("papel", u.papel)} · ${u.setor_nome}</span><br><span class="minusculo texto-3">${u.email}</span></div></div>
      <a class="opcao" href="/perfil">${icone("perfil")}Meu perfil e segurança</a>
      <a class="opcao" href="/notificacoes">${icone("sino")}Notificações</a>
      <div class="tema"><div class="minusculo texto-3 negrito" id="rot-tema">Aparência</div>
        <div class="segmentado" role="radiogroup" aria-labelledby="rot-tema">
          ${[["light", "Claro", "sol"], ["dark", "Escuro", "lua"], ["system", "Sistema", "monitor"]].map(([v, r, ic]) => html`
            <label><input type="radio" name="tema" value="${v}" ${tema === v ? html`checked` : ""}><span>${icone(ic)}${r}</span></label>`)}
        </div></div>
      <button class="opcao" data-sair>${icone("sair")}${estado.meta?.demo ? "Sair / trocar de perfil" : "Sair"}</button>
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
    titulo: "Buscar",
    largo: true,
    conteudo: html`<div class="busca-campo">${icone("busca")}<input type="search" id="campo-busca" placeholder="Código (SC-2026-…, PC-2026-…), título, fornecedor, CNPJ ou material" autocomplete="off" aria-label="Termo de busca" autofocus></div>
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
      if (r.pedidos.length) grupos.push(html`<div class="busca-grupo"><h3>Pedidos de compra</h3>${r.pedidos.map((p) => html`<a class="busca-item" href="/pedidos/${p.id}">${icone("pedido")}<span><strong>${p.codigo}</strong> · ${p.fornecedor_fantasia || p.fornecedor_nome}</span><span class="sub">${badgePedido(p.status)}</span></a>`)}</div>`);
      if (r.fornecedores.length) grupos.push(html`<div class="busca-grupo"><h3>Fornecedores</h3>${r.fornecedores.map((f) => html`<a class="busca-item" href="/fornecedores?fornecedor=${f.id}">${icone("fornecedor")}<span>${f.nome_fantasia || f.razao_social}</span><span class="sub mono">${formato.cnpj(f.cnpj)}</span></a>`)}</div>`);
      if (r.materiais.length) grupos.push(html`<div class="busca-grupo"><h3>Materiais</h3>${r.materiais.map((mt) => html`<a class="busca-item" href="/materiais?q=${encodeURIComponent(mt.codigo)}">${icone("caixa")}<span>${mt.nome}</span><span class="sub mono">${mt.codigo}</span></a>`)}</div>`);
      if (r.usuarios.length) grupos.push(html`<div class="busca-grupo"><h3>Usuários</h3>${r.usuarios.map((us) => html`<a class="busca-item" href="/usuarios?q=${encodeURIComponent(us.email)}">${icone("perfil")}<span>${us.nome}</span><span class="sub">${us.email}</span></a>`)}</div>`);
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
