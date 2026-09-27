// Central de notificações do usuário.
import { api } from "../api.js";
import { ouvir } from "../estado.js";
import { html, renderizar, on } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { cabecalho, toast, toastErro, vazio, erroTela } from "../ui/componentes.js";
import { itemNotificacao } from "../ui/shell.js";

export async function montar({ raiz }) {
  let somenteNaoLidas = false;
  renderizar(raiz, html`
    ${cabecalho({ titulo: "Notificações", sub: "Movimentações das solicitações e pedidos, prazos e avisos de acesso",
      acoes: html`<button class="botao secundario" aria-pressed="false" data-filtro>${icone("filtro")}Somente não lidas</button>
      <button class="botao secundario" data-todas>${icone("check")}Marcar todas como lidas</button>` })}
    <section class="cartao" id="lista-notif" aria-live="polite"></section>`);
  const alvo = raiz.querySelector("#lista-notif");
  async function carregar() {
    try {
      const d = await api.get("/notificacoes", { limite: 100, nao_lidas: somenteNaoLidas || undefined });
      renderizar(alvo, d.itens.length ? html`${d.itens.map(itemNotificacao)}` : vazio("Nenhuma notificação", "Você será avisado sobre cada movimentação relevante.", "", "sino"));
    } catch (e) { alvo.replaceChildren(erroTela(e, carregar)); }
  }
  on(alvo, "click", "[data-notificacao]", (e, a) => { api.post(`/notificacoes/${a.dataset.notificacao}/lida`).catch(() => {}); });
  raiz.querySelector("[data-filtro]").addEventListener("click", (e) => {
    somenteNaoLidas = !somenteNaoLidas;
    e.currentTarget.setAttribute("aria-pressed", String(somenteNaoLidas));
    e.currentTarget.classList.toggle("secundario", !somenteNaoLidas);
    carregar();
  });
  raiz.querySelector("[data-todas]").addEventListener("click", async () => {
    try { const r = await api.post("/notificacoes/lidas"); toast("sucesso", `${r.atualizadas} notificação(ões) marcada(s) como lida(s)`); carregar(); } catch (e) { toastErro(e); }
  });
  await carregar();
  return { desmontar: ouvir("evento", (ev) => { if (ev.tabela === "notificacoes") carregar(); }) };
}
