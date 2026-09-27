// Componentes reutilizáveis: formatação, badges, fluxo, KPIs, toasts, modais, estados e paginação.
import { $, html, on, renderizar, seguro, aplicarEstilosDinamicos } from "./dom.js";
import { icone } from "./icones.js";
import { rotulo, setor as buscarSetor, estado } from "../estado.js";
import { navegar } from "../roteador.js";

// ---------------------------------------------------------------- formatação
const fmtMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmtNumero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });
const fmtCompacto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const fmtData = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "America/Sao_Paulo" });
const fmtDataCurta = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", timeZone: "America/Sao_Paulo" });
const fmtDataHora = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" });
const fmtRelativo = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });

const vazioV = (v) => v === null || v === undefined || v === "";

export const formato = {
  moeda: (v) => (vazioV(v) ? "—" : fmtMoeda.format(Number(v))),
  moedaCompacta: (v) => (vazioV(v) ? "—" : Math.abs(Number(v)) < 10000 ? fmtMoeda.format(Number(v)).replace(/,\d\d$/, "") : "R$ " + fmtCompacto.format(Number(v))),
  numero: (v) => (vazioV(v) ? "—" : fmtNumero.format(Number(v))),
  percentual: (v) => (vazioV(v) ? "—" : `${Math.round(v * 100)}%`),
  dias: (v) => (vazioV(v) ? "—" : `${Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} d`),
  data: (v) => {
    if (!v) return "—";
    if (/^\d{4}-\d{2}-\d{2}$/.test(v)) { const [a, m, d] = v.split("-"); return `${d}/${m}/${a}`; }
    return fmtData.format(new Date(v));
  },
  dataCurta: (v) => {
    if (!v) return "—";
    const d = /^\d{4}-\d{2}-\d{2}$/.test(v) ? new Date(`${v}T12:00:00-03:00`) : new Date(v);
    return fmtDataCurta.format(d).replace(".", "");
  },
  dataHora: (v) => (v ? fmtDataHora.format(new Date(v)) : "—"),
  relativo: (v) => {
    if (!v) return "—";
    const seg = (new Date(v).getTime() - Date.now()) / 1000;
    const abs = Math.abs(seg);
    if (abs < 60) return "agora";
    if (abs < 3600) return fmtRelativo.format(Math.round(seg / 60), "minute");
    if (abs < 86400) return fmtRelativo.format(Math.round(seg / 3600), "hour");
    if (abs < 86400 * 30) return fmtRelativo.format(Math.round(seg / 86400), "day");
    return fmtData.format(new Date(v));
  },
  tamanho: (b) => (b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(0)} KB` : `${(b / 1048576).toFixed(1)} MB`),
  horasRestantes: (h) => {
    if (vazioV(h)) return "";
    const n = Number(h);
    const abs = Math.abs(n);
    const texto = abs >= 48 ? `${Math.round(abs / 24)} dias` : abs >= 1 ? `${Math.round(abs)} h` : `${Math.round(abs * 60)} min`;
    return n >= 0 ? `restam ${texto}` : `atrasado ${texto}`;
  },
  cnpj: (c) => {
    const d = String(c || "").toUpperCase().replace(/[^0-9A-Z]/g, "");
    return d.length === 14 ? `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}` : c || "—";
  },
  entradaDecimal: (v, casas = 2) => (vazioV(v) ? "" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas, useGrouping: false })),
  lerDecimal: (t) => {
    if (vazioV(t)) return 0;
    const s = String(t).replace(/[R$\s]/g, "");
    const n = Number(s.includes(",") ? s.replace(/\./g, "").replace(",", ".") : s);
    return Number.isFinite(n) ? n : 0;
  },
  hojeISO: () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10),
  isoDias: (dias) => new Date(Date.now() + dias * 86400000 - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10),
};

// ---------------------------------------------------------------- badges
const TOM_SOLICITACAO = {
  aguardando_gestor: ["info", true], aguardando_diretoria: ["violeta", true], devolvida: ["alerta", true],
  reprovada: ["perigo", false], aprovada: ["primaria", true], em_cotacao: ["primaria", true],
  aguardando_pedido: ["primaria", true], em_pedido: ["petroleo", true], recebida_parcial: ["petroleo", true],
  concluida: ["sucesso", false], cancelada: ["", false],
};
export function badgeStatus(status, grande = false) {
  const [tom, ativo] = TOM_SOLICITACAO[status] || ["", false];
  return html`<span class="badge ${tom} ${ativo ? "pulso" : ""} ${grande ? "grande" : ""}"><span class="ponto"></span>${rotulo("status_solicitacao", status)}</span>`;
}

const TOM_PEDIDO = {
  aguardando_financeiro: ["info", true], aguardando_diretoria: ["violeta", true], aprovado: ["primaria", true],
  enviado: ["petroleo", true], entregue_parcial: ["alerta", true], entregue: ["sucesso", false],
  reprovado: ["perigo", false], cancelado: ["", false],
};
export function badgePedido(status, grande = false) {
  const [tom, ativo] = TOM_PEDIDO[status] || ["", false];
  return html`<span class="badge ${tom} ${ativo ? "pulso" : ""} ${grande ? "grande" : ""}"><span class="ponto"></span>${rotulo("status_pedido", status)}</span>`;
}

export function badgeRecebimento(situacao) {
  const [tom, ic] = { conforme: ["sucesso", "check_circulo"], divergente: ["alerta", "alerta"], recusado: ["perigo", "x_circulo"] }[situacao] || ["", "info"];
  return html`<span class="badge ${tom}">${icone(ic)}${rotulo("situacao_recebimento", situacao)}</span>`;
}

const SLA = {
  dentro_prazo: ["sucesso", "relogio"], alerta: ["alerta", "ampulheta"], estourado: ["perigo", "alerta"],
  cumprido: ["", "check"], cumprido_com_atraso: ["alerta", "check"],
};
export function badgeSla(situacao, horas) {
  const [tom, ic] = SLA[situacao] || ["", "info"];
  const detalhe = ["dentro_prazo", "alerta", "estourado"].includes(situacao) && horas !== undefined ? formato.horasRestantes(horas) : "";
  return html`<span class="badge ${tom}" title="${detalhe}">${icone(ic)}${rotulo("sla_situacao", situacao)}</span>`;
}

export function badgeUrgencia(u) {
  if (u === "normal") return html`<span class="texto-3 pequeno">Normal</span>`;
  const tom = { imediato: "perigo", urgente: "alerta" }[u] || "";
  return html`<span class="badge ${tom}">${icone(u === "imediato" ? "alerta" : "relogio")}${rotulo("urgencia", u)}</span>`;
}

export function badgeSetor(codigo, nome, cor) {
  const s = buscarSetor(codigo);
  return html`<span class="badge setor" data-cor="${cor || s?.cor || "#64748b"}"><span class="ponto"></span>${nome || s?.nome || codigo}</span>`;
}

export function badgeUsuario(status) {
  const tom = { pendente: "alerta", aprovado: "sucesso", rejeitado: "perigo", suspenso: "" }[status] || "";
  return html`<span class="badge ${tom}"><span class="ponto"></span>${rotulo("status_usuario", status)}</span>`;
}

export const ICONE_PAPEL = {
  admin: "engrenagem", comprador: "carrinho", solicitante: "documento", gestor: "usuario_check",
  financeiro: "carteira", recebimento: "caminhao", diretoria: "maleta", auditoria: "auditoria",
};
const TOM_PAPEL = { admin: "", comprador: "primaria", solicitante: "info", gestor: "info", financeiro: "sucesso", recebimento: "petroleo", diretoria: "violeta", auditoria: "alerta" };
export function badgePapel(papel) {
  return html`<span class="badge ${TOM_PAPEL[papel] || ""}">${icone(ICONE_PAPEL[papel] || "perfil")}${rotulo("papel", papel)}</span>`;
}

// ---------------------------------------------------------------- fluxo (7 etapas)
/** Calcula o estado de cada etapa a partir da solicitação (e do pedido ativo). */
export function etapasFluxo(s) {
  const nomes = estado.meta?.etapas || ["Solicitação", "Aprovação", "Cotação", "Fornecedor", "Pedido", "Recebimento", "Conclusão"];
  const st = s.status;
  const ps = s.pedido_status;
  let atual;
  let tipoAtual = "atual";
  if (["aguardando_gestor", "aguardando_diretoria", "devolvida"].includes(st)) { atual = 1; if (st === "devolvida") tipoAtual = "atencao"; }
  else if (st === "reprovada") { atual = 1; tipoAtual = "bloqueada"; }
  else if (["aprovada", "em_cotacao"].includes(st)) atual = 2;
  else if (st === "aguardando_pedido") atual = 4;
  else if (st === "em_pedido") atual = ["enviado", "entregue_parcial"].includes(ps) ? 5 : 4;
  else if (st === "recebida_parcial") atual = 5;
  else if (st === "concluida") atual = 7;
  else if (st === "cancelada") { atual = s.cotacao_iniciada_em ? 2 : s.aprovado_em ? 2 : 1; tipoAtual = "bloqueada"; }
  const detalhes = [
    formato.dataCurta(s.criado_em),
    st === "aguardando_gestor" ? "Gestor do setor" : st === "aguardando_diretoria" ? "Diretoria" : st === "devolvida" ? "Devolvida" : st === "reprovada" ? "Reprovada" : s.aprovado_em ? formato.dataCurta(s.aprovado_em) : "",
    s.cotacoes_qtd ? `${s.cotacoes_qtd} proposta(s)` : st === "aprovada" ? "Aguardando início" : "",
    s.fornecedor_fantasia || s.fornecedor_nome || "",
    ps && atual === 4 ? rotulo("status_pedido", ps) : s.pedido_codigo || "",
    ps && atual >= 5 ? rotulo("status_pedido", ps) : "",
    s.finalizado_em && st === "concluida" ? formato.dataCurta(s.finalizado_em) : st === "cancelada" ? "Cancelada" : "",
  ];
  return nomes.map((nome, i) => ({
    nome, detalhe: detalhes[i],
    estado: i < atual ? "concluida" : i === atual ? tipoAtual : "pendente",
  }));
}

export function fluxo(s) {
  const etapas = etapasFluxo(s);
  const ic = { concluida: "check", bloqueada: "x", atencao: "devolver" };
  return html`<ol class="fluxo" aria-label="Etapas do processo de compra">${etapas.map((e, i) => html`
    <li class="etapa ${e.estado}" ${e.estado === "atual" ? seguro('aria-current="step"') : ""}>
      <span class="marcador">${ic[e.estado] ? icone(ic[e.estado]) : i + 1}</span>
      <span class="nome">${e.nome}</span>
      <span class="detalhe" title="${e.detalhe}">${e.detalhe || " "}</span>
    </li>`)}</ol>`;
}

export function miniFluxo(s) {
  const etapas = etapasFluxo(s);
  const classe = { concluida: "ok", atual: "atual", atencao: "atual", bloqueada: "parado" };
  const atual = etapas.find((e) => ["atual", "atencao", "bloqueada"].includes(e.estado));
  return html`<span class="mini-fluxo" title="${atual ? `Etapa: ${atual.nome}` : "Concluída"}" aria-label="${atual ? `Etapa: ${atual.nome}` : "Concluída"}">${etapas.map((e) => html`<i class="${classe[e.estado] || ""}"></i>`)}</span>`;
}

// ---------------------------------------------------------------- estrutura de página
export function cabecalho({ titulo, sub = "", migalhas = [], acoes = "", extra = "" }) {
  return html`<header class="cabecalho-pagina">
    <div class="titulos">
      ${migalhas.length ? html`<nav class="migalhas" aria-label="Você está em">${migalhas.map((m, i) => html`${i ? icone("seta_dir") : ""}${m.href ? html`<a href="${m.href}">${m.rotulo}</a>` : html`<span>${m.rotulo}</span>`}`)}</nav>` : ""}
      <h1>${titulo}${extra}</h1>
      ${sub ? html`<p class="sub">${sub}</p>` : ""}
    </div>
    ${acoes ? html`<div class="acoes-pagina">${acoes}</div>` : ""}
  </header>`;
}

export function kpi({ rotulo: r, valor, meta = "", icone: ic = "tendencia", tom = "", href = "" }) {
  const corpo = html`<div class="kpi-topo"><span class="kpi-icone ${tom}">${icone(ic)}</span>${r}</div>
    <div class="valor" title="${typeof valor === "string" ? valor : ""}">${valor}</div>${meta ? html`<div class="meta">${meta}</div>` : ""}`;
  return href ? html`<a class="kpi" href="${href}">${corpo}</a>` : html`<div class="kpi">${corpo}</div>`;
}

/** Abas acessíveis. itens: [{ valor, rotulo, qtd, icone, critico }] */
export function abas(itens, ativo, { nome = "aba", classe = "" } = {}) {
  return html`<div class="abas ${classe}" role="tablist">${itens.map((a) => html`<button type="button" class="aba" role="tab" data-${seguro(nome)}="${a.valor}" aria-selected="${String(a.valor === ativo)}">
    ${a.icone ? icone(a.icone) : ""}${a.rotulo}${a.qtd !== undefined && a.qtd !== null ? html`<span class="qtd ${a.critico && a.qtd ? "critica" : ""}">${a.qtd}</span>` : ""}</button>`)}</div>`;
}

/** Torna linhas de tabela com data-href navegáveis (clique e Enter), sem interferir em links/botões. */
export function ativarLinhasClicaveis(raiz) {
  on(raiz, "click", "tr[data-href]", (e, tr) => {
    if (e.target.closest("a, button, input, select, label")) return;
    navegar(tr.dataset.href);
  });
  on(raiz, "keydown", "tr[data-href]", (e, tr) => { if (e.key === "Enter") navegar(tr.dataset.href); });
}

export function pessoa(nome, sub = "") {
  return html`<span class="linha-flex"><span class="avatar pequeno" aria-hidden="true">${iniciaisDe(nome)}</span><span><span>${nome || "—"}</span>${sub ? html`<br><small class="texto-3">${sub}</small>` : ""}</span></span>`;
}
function iniciaisDe(nome = "") {
  const p = String(nome || "").trim().split(/\s+/).filter(Boolean);
  return ((p[0]?.[0] || "") + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase();
}

// ---------------------------------------------------------------- estados
export function vazio(titulo, texto = "", acao = "", ic = "documento", compacto = false) {
  return html`<div class="vazio ${compacto ? "compacto" : ""}"><span class="icone-vazio">${icone(ic)}</span><h3>${titulo}</h3>${texto ? html`<p>${texto}</p>` : ""}${acao}</div>`;
}

export function carregando() {
  return html`<div class="carregando-pagina" aria-busy="true" aria-live="polite"><span class="sr-only">Carregando…</span>
    <div class="esqueleto titulo"></div><div class="kpis"><div class="esqueleto alto"></div><div class="esqueleto alto"></div><div class="esqueleto alto"></div><div class="esqueleto alto"></div></div>
    <div class="esqueleto medio"></div></div>`;
}

export function carregandoBloco(linhas = 4) {
  return html`<div class="cartao-corpo pilha-sm" aria-busy="true">${Array.from({ length: linhas }, () => html`<div class="esqueleto"></div>`)}</div>`;
}

export function aviso(tipo, titulo, texto = "", acoes = "") {
  const ic = { info: "info", alerta: "alerta", perigo: "x_circulo", sucesso: "check_circulo" }[tipo];
  return html`<div class="aviso ${tipo}" role="${tipo === "perigo" ? "alert" : "status"}">${icone(ic)}<div><strong>${titulo}</strong>${texto ? html`<span class="texto-aviso">${texto}</span>` : ""}</div>${acoes ? html`<div class="acoes-aviso">${acoes}</div>` : ""}</div>`;
}

export function erroTela(erro, aoTentar) {
  const el = document.createElement("div");
  const semPermissao = erro?.status === 403;
  const naoEncontrado = erro?.status === 404;
  renderizar(el, html`<div class="cartao">${vazio(
    semPermissao ? "Acesso restrito" : naoEncontrado ? "Registro não encontrado" : "Não foi possível carregar",
    erro?.message || "Erro inesperado", html`<button class="botao secundario" data-tentar>${icone("atualizar")}Tentar novamente</button>`,
    semPermissao ? "cadeado" : "alerta")}</div>`);
  el.querySelector("[data-tentar]").addEventListener("click", aoTentar);
  return el;
}

export function paginacao({ total, pagina, por_pagina: porPagina }) {
  const paginas = Math.max(1, Math.ceil(total / porPagina));
  const ini = total ? (pagina - 1) * porPagina + 1 : 0;
  const fim = Math.min(total, pagina * porPagina);
  if (paginas <= 1) return html`<nav class="paginacao" aria-label="Paginação"><span>${formato.numero(total)} registro(s)</span></nav>`;
  return html`<nav class="paginacao" aria-label="Paginação">
    <span>${formato.numero(ini)}–${formato.numero(fim)} de ${formato.numero(total)}</span>
    <div class="grupo-botoes">
      <button class="botao secundario pequeno" data-pagina="${pagina - 1}" ${pagina <= 1 ? seguro("disabled") : ""}>${icone("seta_esq")}Anterior</button>
      <span class="pequeno texto-3">Página ${pagina} de ${paginas}</span>
      <button class="botao secundario pequeno" data-pagina="${pagina + 1}" ${pagina >= paginas ? seguro("disabled") : ""}>Próxima${icone("seta_dir")}</button>
    </div></nav>`;
}

// ---------------------------------------------------------------- toasts
export function toast(tipo, titulo, mensagem = "", duracao = 5000) {
  const area = $("#toasts");
  const el = document.createElement("div");
  el.className = `toast ${tipo}`;
  el.setAttribute("role", tipo === "erro" ? "alert" : "status");
  const ic = { sucesso: "check_circulo", erro: "x_circulo", alerta: "alerta", info: "info" }[tipo] || "info";
  renderizar(el, html`${icone(ic)}<div><div class="t-titulo">${titulo}</div>${mensagem ? html`<div class="t-msg">${mensagem}</div>` : ""}</div>
    <button type="button" aria-label="Fechar aviso">${icone("fechar")}</button>`);
  const remover = () => el.remove();
  el.querySelector("button").addEventListener("click", remover);
  area.appendChild(el);
  if (duracao) setTimeout(remover, duracao);
  while (area.children.length > 4) area.firstElementChild.remove();
}

export function toastErro(erro, titulo = "Não foi possível concluir") {
  if (erro?.name === "AbortError") return;
  const campos = Object.values(erro?.campos || {});
  toast("erro", titulo, campos.length ? campos.join(" · ") : erro?.message || "Erro inesperado", 7000);
}

// ---------------------------------------------------------------- modais
/**
 * Abre um <dialog> modal acessível. `tamanho`: "" | "largo" | "extra"; `gaveta` abre como painel lateral.
 * Retorna { el, fechar, corpo }.
 */
export function modal({ titulo, sub = "", conteudo, rodape = "", largo = false, tamanho = "", gaveta = false, aoFechar } = {}) {
  const dialogo = document.createElement("dialog");
  dialogo.className = `modal ${largo ? "largo" : ""} ${tamanho} ${gaveta ? "gaveta" : ""}`;
  const idTitulo = `modal-t-${Math.random().toString(36).slice(2, 8)}`;
  dialogo.setAttribute("aria-labelledby", idTitulo);
  renderizar(dialogo, html`<div class="modal-cabecalho"><h2 id="${idTitulo}">${titulo}${sub ? html`<span class="sub">${sub}</span>` : ""}</h2>
      <button type="button" class="botao fantasma icone pequeno" data-fechar aria-label="Fechar">${icone("fechar")}</button></div>
    <div class="modal-corpo">${conteudo}</div>${rodape ? html`<div class="modal-rodape">${rodape}</div>` : ""}`);
  document.body.appendChild(dialogo);
  const fechar = () => { if (dialogo.open) dialogo.close(); };
  dialogo.addEventListener("close", () => { dialogo.remove(); aoFechar?.(); });
  on(dialogo, "click", "[data-fechar]", fechar);
  dialogo.addEventListener("mousedown", (e) => { if (e.target === dialogo) fechar(); });
  dialogo.showModal();
  const foco = dialogo.querySelector("[autofocus], .modal-corpo input:not([type=hidden]), .modal-corpo textarea, .modal-corpo select");
  (foco || dialogo.querySelector("[data-fechar]"))?.focus();
  return { el: dialogo, fechar, corpo: dialogo.querySelector(".modal-corpo") };
}

/** Confirmação com justificativa opcional. Resolve com { confirmado, texto, dados }. */
export function confirmar({ titulo, mensagem, rotuloConfirmar = "Confirmar", tom = "", justificativa = null, minimo = 0, extra = "", placeholder = "", icone: ic = "" }) {
  return new Promise((resolve) => {
    let resolvido = false;
    const idTexto = `just-${Math.random().toString(36).slice(2, 7)}`;
    const m = modal({
      titulo,
      conteudo: html`<form id="form-confirmar" class="pilha" novalidate>
        ${mensagem ? html`<p class="texto-2">${mensagem}</p>` : ""}${extra}
        ${justificativa ? html`<div class="campo"><label for="${idTexto}">${justificativa}${minimo ? html`<span class="obrigatorio" aria-hidden="true">*</span>` : ""}</label>
          <textarea id="${idTexto}" name="texto" ${minimo ? seguro("required") : ""} maxlength="2000" placeholder="${placeholder}" autofocus></textarea>
          ${minimo ? html`<div class="contador-caracteres insuficiente" data-contador>Mínimo de ${minimo} caracteres</div>` : ""}</div>` : ""}
      </form>`,
      rodape: html`<button type="button" class="botao secundario" data-fechar>Cancelar</button>
        <button type="submit" form="form-confirmar" class="botao ${tom}" data-ok>${ic ? icone(ic) : ""}${rotuloConfirmar}</button>`,
      aoFechar: () => { if (!resolvido) resolve({ confirmado: false }); },
    });
    const form = m.el.querySelector("#form-confirmar");
    const area = form.querySelector(`#${idTexto}`);
    const contador = form.querySelector("[data-contador]");
    area?.addEventListener("input", () => {
      if (!contador) return;
      const n = area.value.trim().length;
      contador.textContent = n >= minimo ? `${n} caracteres` : `${n}/${minimo} caracteres mínimos`;
      contador.classList.toggle("insuficiente", n < minimo);
    });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const texto = area?.value.trim() || "";
      if (minimo && texto.length < minimo) { area.setAttribute("aria-invalid", "true"); area.focus(); return; }
      resolvido = true;
      resolve({ confirmado: true, texto, dados: Object.fromEntries(new FormData(form)) });
      m.fechar();
    });
  });
}

/** Coloca um botão em estado de carregamento durante uma promessa. */
export async function comCarregamento(botao, promessa) {
  if (!botao) return promessa;
  const original = botao.innerHTML;
  botao.disabled = true;
  botao.setAttribute("aria-busy", "true");
  renderizar(botao, html`${icone("atualizar", "girando")}<span>Processando…</span>`);
  try {
    return await promessa;
  } finally {
    botao.disabled = false;
    botao.removeAttribute("aria-busy");
    botao.innerHTML = original;
  }
}

export function opcoes(mapa, selecionado, { vazio: rotuloVazio } = {}) {
  const itens = Object.entries(mapa).map(([v, r]) => html`<option value="${v}" ${String(v) === String(selecionado ?? "") ? seguro("selected") : ""}>${r}</option>`);
  return rotuloVazio !== undefined ? html`<option value="">${rotuloVazio}</option>${itens}` : html`${itens}`;
}

export function opcoesSetores(setores, selecionado, { vazio: rotuloVazio, somenteOperacionais = false } = {}) {
  const lista = setores.filter((s) => s.ativo && (!somenteOperacionais || s.operacional));
  return opcoes(Object.fromEntries(lista.map((s) => [s.codigo, s.nome])), selecionado, { vazio: rotuloVazio });
}

export const pode = (capacidade) => Boolean(estado.usuario?.capacidades?.includes(capacidade));

export { aplicarEstilosDinamicos };
