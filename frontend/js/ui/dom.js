// Utilitários de DOM e templates HTML com escape automático (proteção contra XSS).

class HtmlSeguro {
  constructor(texto) { this.texto = texto; }
  toString() { return this.texto; }
}

const MAPA_ESCAPE = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;" };

export function escapar(valor) {
  if (valor === null || valor === undefined || valor === false) return "";
  return String(valor).replace(/[&<>"'`]/g, (c) => MAPA_ESCAPE[c]);
}

function valorParaHtml(valor) {
  if (valor instanceof HtmlSeguro) return valor.texto;
  if (Array.isArray(valor)) return valor.map(valorParaHtml).join("");
  return escapar(valor);
}

/** Template literal: interpolações são escapadas, exceto HtmlSeguro (gerado por html`` ou seguro()). */
export function html(partes, ...valores) {
  let saida = partes[0];
  for (let i = 0; i < valores.length; i++) saida += valorParaHtml(valores[i]) + partes[i + 1];
  return new HtmlSeguro(saida);
}

/** Marca conteúdo como confiável (somente para markup estático gerado pelo próprio app, ex.: ícones SVG). */
export function seguro(texto) {
  return new HtmlSeguro(texto);
}

export function renderizar(elemento, conteudo) {
  elemento.innerHTML = conteudo instanceof HtmlSeguro ? conteudo.texto : escapar(conteudo);
  aplicarEstilosDinamicos(elemento);
}

/** Aplica cores/larguras declaradas em data-* via CSSOM (compatível com CSP sem 'unsafe-inline'). */
export function aplicarEstilosDinamicos(raiz) {
  raiz.querySelectorAll("[data-cor]").forEach((el) => el.style.setProperty("--cor", el.dataset.cor));
  raiz.querySelectorAll("[data-largura]").forEach((el) => {
    requestAnimationFrame(() => el.style.setProperty("--largura", `${el.dataset.largura}%`));
  });
}

export function $(seletor, raiz = document) { return raiz.querySelector(seletor); }
export function $$(seletor, raiz = document) { return Array.from(raiz.querySelectorAll(seletor)); }

/** Delegação de eventos: on(raiz, 'click', '[data-acao]', fn) */
export function on(raiz, evento, seletor, manipulador, opcoes) {
  const fn = (e) => {
    const alvo = e.target.closest(seletor);
    if (alvo && raiz.contains(alvo)) manipulador(e, alvo);
  };
  raiz.addEventListener(evento, fn, opcoes);
  return () => raiz.removeEventListener(evento, fn, opcoes);
}

export function dadosFormulario(form) {
  const dados = {};
  new FormData(form).forEach((valor, chave) => {
    if (valor instanceof File) return;
    if (chave in dados) {
      dados[chave] = [].concat(dados[chave], valor);
    } else {
      dados[chave] = typeof valor === "string" ? valor.trim() : valor;
    }
  });
  form.querySelectorAll('input[type="checkbox"][name]').forEach((cb) => {
    if (!cb.value || cb.value === "on") dados[cb.name] = cb.checked;
  });
  return dados;
}

export function mostrarErrosCampos(form, campos = {}) {
  form.querySelectorAll(".erro-campo").forEach((el) => el.remove());
  form.querySelectorAll('[aria-invalid="true"]').forEach((el) => el.removeAttribute("aria-invalid"));
  let primeiro = null;
  for (const [nome, mensagem] of Object.entries(campos)) {
    const entrada = form.querySelector(`[name="${CSS.escape(nome)}"]`);
    const campo = entrada?.closest(".campo") || form.querySelector(`[data-campo="${CSS.escape(nome)}"]`);
    if (!campo) continue;
    const id = `erro-${nome}-${Math.random().toString(36).slice(2, 7)}`;
    const p = document.createElement("p");
    p.className = "erro-campo";
    p.id = id;
    p.setAttribute("role", "alert");
    p.textContent = mensagem;
    campo.appendChild(p);
    if (entrada) {
      entrada.setAttribute("aria-invalid", "true");
      entrada.setAttribute("aria-describedby", id);
      primeiro = primeiro || entrada;
    }
  }
  primeiro?.focus();
}

export function debounce(fn, ms = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

export function iniciais(nome = "") {
  const partes = nome.trim().split(/\s+/).filter(Boolean);
  return ((partes[0]?.[0] || "") + (partes.length > 1 ? partes[partes.length - 1][0] : "")).toUpperCase();
}
