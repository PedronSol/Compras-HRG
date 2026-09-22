// Roteador SPA baseado na History API, com carregamento sob demanda das telas.
import { estado } from "./estado.js";

const rotas = [];
let telaAtual = null;
let manipuladorRota = null;

export function definirRota(padrao, carregar, opcoes = {}) {
  const nomes = [];
  const regex = new RegExp("^" + padrao.replace(/\/:([a-z_]+)/gi, (_, nome) => { nomes.push(nome); return "/([^/]+)"; }) + "/?$");
  rotas.push({ padrao, regex, nomes, carregar, ...opcoes });
}

export function resolver(caminho) {
  for (const rota of rotas) {
    const m = caminho.match(rota.regex);
    if (m) {
      const params = Object.fromEntries(rota.nomes.map((n, i) => [n, decodeURIComponent(m[i + 1])]));
      return { rota, params };
    }
  }
  return null;
}

export function navegar(url, { substituir = false } = {}) {
  const destino = new URL(url, location.origin);
  if (destino.origin !== location.origin) { location.href = url; return; }
  const atual = location.pathname + location.search;
  const novo = destino.pathname + destino.search;
  if (substituir) history.replaceState({}, "", novo);
  else if (novo !== atual) history.pushState({}, "", novo);
  processar();
}

export function aoMudarRota(fn) {
  manipuladorRota = fn;
}

export async function processar() {
  if (telaAtual?.desmontar) {
    try { telaAtual.desmontar(); } catch (e) { console.error(e); }
  }
  telaAtual = null;
  const encontrado = resolver(location.pathname);
  const consulta = Object.fromEntries(new URLSearchParams(location.search));
  telaAtual = await manipuladorRota?.(encontrado, consulta);
}

export function iniciarRoteador() {
  window.addEventListener("popstate", processar);
  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download") || a.dataset.externo !== undefined) return;
    const url = new URL(a.href, location.origin);
    if (url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
    e.preventDefault();
    navegar(url.pathname + url.search);
  });
}

export function atualizarConsulta(parametros, { substituir = true } = {}) {
  const url = new URL(location.href);
  for (const [k, v] of Object.entries(parametros)) {
    if (v === undefined || v === null || v === "" || v === false) url.searchParams.delete(k);
    else url.searchParams.set(k, v === true ? "1" : v);
  }
  const novo = url.pathname + url.search;
  if (substituir) history.replaceState({}, "", novo);
  else history.pushState({}, "", novo);
}

export function podeAcessar(rota) {
  return !rota.papeis || rota.papeis.includes(estado.usuario?.papel);
}
