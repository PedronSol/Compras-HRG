// Componentes reutilizáveis: formatação, badges, toasts, modais, estados vazios e paginação.
import { $, html, on, renderizar, seguro, aplicarEstilosDinamicos } from "./dom.js";
import { icone } from "./icones.js";
import { rotulo, setor as buscarSetor } from "../estado.js";

// ---------------------------------------------------------------- formatação
const fmtMoeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
const fmtNumero = new Intl.NumberFormat("pt-BR");
const fmtCompacto = new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 });
const fmtData = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "America/Sao_Paulo" });
const fmtDataHora = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" });
const fmtRelativo = new Intl.RelativeTimeFormat("pt-BR", { numeric: "auto" });

export const formato = {
  moeda: (v) => (v === null || v === undefined || v === "" ? "—" : fmtMoeda.format(Number(v))),
  moedaCompacta: (v) => (v === null || v === undefined ? "—" : "R$ " + fmtCompacto.format(Number(v))),
  numero: (v) => (v === null || v === undefined ? "—" : fmtNumero.format(v)),
  percentual: (v) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`),
  data: (v) => {
    if (!v) return "—";
    if (/^\d{4}-\d{2}-\d{2}$/.test(v)) { const [a, m, d] = v.split("-"); return `${d}/${m}/${a}`; }
    return fmtData.format(new Date(v));
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
    if (h === null || h === undefined) return "";
    const n = Number(h);
    const abs = Math.abs(n);
    const texto = abs >= 48 ? `${Math.round(abs / 24)} dias` : abs >= 1 ? `${Math.round(abs)} h` : `${Math.round(abs * 60)} min`;
    return n >= 0 ? `restam ${texto}` : `estourado há ${texto}`;
  },
  cnpj: (c) => {
    const d = String(c || "").toUpperCase().replace(/[^0-9A-Z]/g, "");
    return d.length === 14 ? `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}` : c || "—";
  },
  entradaDecimal: (v) => (v === null || v === undefined || v === "" ? "" : Number(v).toFixed(2).replace(".", ",")),
  hojeISO: () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10),
};

// ---------------------------------------------------------------- badges
const TOM_STATUS = {
  aguardando_adm: ["info", true], necessita_nova_cotacao: ["alerta", true], rejeitado_adm: ["perigo", false],
  aprovado_adm: ["primaria", true], em_cotacao: ["primaria", true], aprovado: ["sucesso", false],
  rejeitado_compras: ["perigo", false], cancelado: ["", false],
};
export function badgeStatus(status) {
  const [tom, ativo] = TOM_STATUS[status] || ["", false];
  return html`<span class="badge ${tom} ${ativo ? "pulso" : ""}"><span class="ponto"></span>${rotulo("status_solicitacao", status)}</span>`;
}

const SLA = {
  dentro_prazo: ["sucesso", "check_circulo"], alerta: ["alerta", "relogio"], estourado: ["perigo", "alerta"],
  cumprido: ["sucesso", "check"], cumprido_com_atraso: ["alerta", "alerta"],
};
export function badgeSla(situacao, horas) {
  const [tom, ic] = SLA[situacao] || ["", "info"];
  const detalhe = ["dentro_prazo", "alerta", "estourado"].includes(situacao) && horas !== undefined ? formato.horasRestantes(horas) : "";
  return html`<span class="badge ${tom}" title="${detalhe}">${icone(ic)}${rotulo("sla_situacao", situacao)}</span>`;
}

export function badgeUrgencia(u) {
  const tom = { imediato: "perigo", urgente: "alerta", normal: "contorno" }[u] || "";
  return html`<span class="badge ${tom}">${u === "imediato" ? icone("alerta") : u === "urgente" ? icone("relogio") : ""}${rotulo("urgencia", u)}</span>`;
}

export function badgeSetor(codigo, nome, cor) {
  const s = buscarSetor(codigo);
  return html`<span class="badge setor" data-cor="${cor || s?.cor || "#64748b"}"><span class="ponto"></span>${nome || s?.nome || codigo}</span>`;
}

const TOM_SERVICO = { agendado: "info", em_andamento: "primaria", concluido: "sucesso", cancelado: "" };
export function badgeServico(situacao, atrasado = false) {
  if (atrasado) return html`<span class="badge perigo">${icone("alerta")}Atrasado</span>`;
  return html`<span class="badge ${TOM_SERVICO[situacao] || ""} ${situacao === "em_andamento" ? "pulso" : ""}"><span class="ponto"></span>${rotulo("situacao_servico", situacao)}</span>`;
}

export function badgeUsuario(status) {
  const tom = { pendente: "alerta", aprovado: "sucesso", rejeitado: "perigo", suspenso: "" }[status] || "";
  return html`<span class="badge ${tom}"><span class="ponto"></span>${rotulo("status_usuario", status)}</span>`;
}

// ---------------------------------------------------------------- estados
export function vazio(titulo, texto = "", acao = "") {
  return html`<div class="vazio">${icone("documento")}<h3>${titulo}</h3>${texto ? html`<p>${texto}</p>` : ""}${acao}</div>`;
}

export function carregando() {
  return html`<div class="carregando-pagina" aria-busy="true" aria-live="polite"><span class="sr-only">Carregando…</span>
    <div class="esqueleto"></div><div class="kpis"><div class="esqueleto alto"></div><div class="esqueleto alto"></div><div class="esqueleto alto"></div></div>
    <div class="esqueleto medio"></div></div>`;
}

export function aviso(tipo, titulo, texto = "") {
  const ic = { info: "info", alerta: "alerta", perigo: "x_circulo", sucesso: "check_circulo" }[tipo];
  return html`<div class="aviso ${tipo}" role="${tipo === "perigo" ? "alert" : "status"}">${icone(ic)}<div><strong>${titulo}</strong>${texto ? html`<span class="texto-aviso">${texto}</span>` : ""}</div></div>`;
}

export function erroTela(erro, aoTentar) {
  const el = document.createElement("div");
  renderizar(el, html`<div class="cartao"><div class="vazio">${icone("alerta")}<h3>Não foi possível carregar</h3><p>${erro?.message || "Erro inesperado"}</p>
    <button class="botao secundario" data-tentar>${icone("atualizar")}Tentar novamente</button></div></div>`);
  el.querySelector("[data-tentar]").addEventListener("click", aoTentar);
  return el;
}

export function paginacao({ total, pagina, por_pagina: porPagina }) {
  const paginas = Math.max(1, Math.ceil(total / porPagina));
  const ini = total ? (pagina - 1) * porPagina + 1 : 0;
  const fim = Math.min(total, pagina * porPagina);
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
  toast("erro", titulo, campos.length ? campos.join(" · ") : erro?.message || "Erro inesperado");
}

// ---------------------------------------------------------------- modais
/**
 * Abre um <dialog> modal acessível. `conteudo` é HtmlSeguro com corpo; `rodape` opcional.
 * Retorna { el, fechar, corpo }. `aoFechar` é chamado ao encerrar.
 */
export function modal({ titulo, conteudo, rodape = "", largo = false, aoFechar } = {}) {
  const dialogo = document.createElement("dialog");
  dialogo.className = `modal ${largo ? "largo" : ""}`;
  const idTitulo = `modal-t-${Math.random().toString(36).slice(2, 8)}`;
  dialogo.setAttribute("aria-labelledby", idTitulo);
  renderizar(dialogo, html`<div class="modal-cabecalho"><h2 id="${idTitulo}">${titulo}</h2>
      <button type="button" class="botao fantasma icone pequeno" data-fechar aria-label="Fechar">${icone("fechar")}</button></div>
    <div class="modal-corpo">${conteudo}</div>${rodape ? html`<div class="modal-rodape">${rodape}</div>` : ""}`);
  document.body.appendChild(dialogo);
  const fechar = () => { if (dialogo.open) dialogo.close(); };
  dialogo.addEventListener("close", () => { dialogo.remove(); aoFechar?.(); });
  on(dialogo, "click", "[data-fechar]", fechar);
  dialogo.addEventListener("click", (e) => { if (e.target === dialogo) fechar(); });
  dialogo.showModal();
  const foco = dialogo.querySelector("[autofocus], .modal-corpo input, .modal-corpo textarea, .modal-corpo select");
  (foco || dialogo.querySelector("[data-fechar]"))?.focus();
  return { el: dialogo, fechar, corpo: dialogo.querySelector(".modal-corpo") };
}

/** Confirmação com justificativa opcional. Resolve com { confirmado, texto }. */
export function confirmar({ titulo, mensagem, rotuloConfirmar = "Confirmar", tom = "", justificativa = null, minimo = 0, extra = "" }) {
  return new Promise((resolve) => {
    let resolvido = false;
    const idTexto = `just-${Math.random().toString(36).slice(2, 7)}`;
    const m = modal({
      titulo,
      conteudo: html`<form id="form-confirmar" class="pilha" novalidate>
        ${mensagem ? html`<p class="texto-2">${mensagem}</p>` : ""}${extra}
        ${justificativa ? html`<div class="campo"><label for="${idTexto}">${justificativa}${minimo ? html`<span class="obrigatorio" aria-hidden="true">*</span>` : ""}</label>
          <textarea id="${idTexto}" name="texto" ${minimo ? seguro("required") : ""} maxlength="2000" autofocus></textarea>
          ${minimo ? html`<div class="contador-caracteres insuficiente" data-contador>Mínimo de ${minimo} caracteres</div>` : ""}</div>` : ""}
      </form>`,
      rodape: html`<button type="button" class="botao secundario" data-fechar>Cancelar</button>
        <button type="submit" form="form-confirmar" class="botao ${tom}" data-ok>${rotuloConfirmar}</button>`,
      aoFechar: () => { if (!resolvido) resolve({ confirmado: false }); },
    });
    const form = m.el.querySelector("#form-confirmar");
    const area = form.querySelector("textarea");
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
      if (minimo && texto.length < minimo) {
        area.setAttribute("aria-invalid", "true");
        area.focus();
        return;
      }
      resolvido = true;
      const dados = Object.fromEntries(new FormData(form));
      resolve({ confirmado: true, texto, dados });
      m.fechar();
    });
  });
}

/** Coloca um botão em estado de carregamento durante uma promessa. */
export async function comCarregamento(botao, promessa) {
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

export { aplicarEstilosDinamicos };
