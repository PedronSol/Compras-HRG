// Tema claro/escuro/sistema com persistência local.
const CHAVE = "rg-tema";

export function temaAtual() {
  try { return localStorage.getItem(CHAVE) || "system"; } catch { return "system"; }
}

export function aplicarTema(tema) {
  const raiz = document.documentElement;
  if (tema === "light" || tema === "dark") raiz.dataset.theme = tema;
  else delete raiz.dataset.theme;
  try { localStorage.setItem(CHAVE, tema); } catch { /* ignorado */ }
  const escuro = tema === "dark" || (tema === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", escuro ? "#132A45" : "#2E5C88");
}
