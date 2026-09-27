// Lista de solicitações: abas por etapa do fluxo, filtros, tabela responsiva e exportação.
import { api } from "../api.js";
import { estado, rotulo } from "../estado.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import {
  abas, ativarLinhasClicaveis, badgeSetor, badgeSla, badgeStatus, badgeUrgencia, cabecalho, carregandoBloco,
  comCarregamento, formato, miniFluxo, opcoes, opcoesSetores, paginacao, pode, toastErro, vazio,
} from "../ui/componentes.js";

export const ETAPAS = [
  { valor: "", rotulo: "Todas" },
  { valor: "aprovacao", rotulo: "Em aprovação" },
  { valor: "cotacao", rotulo: "Em cotação" },
  { valor: "fornecedor", rotulo: "Fornecedor definido" },
  { valor: "pedido", rotulo: "Pedido emitido" },
  { valor: "recebimento", rotulo: "Recebimento parcial" },
  { valor: "encerradas", rotulo: "Encerradas" },
];

export function tabelaSolicitacoes(itens, { mostrarSetor = true } = {}) {
  return html`<div class="tabela-envoltorio"><table class="tabela responsiva">
    <thead><tr><th scope="col">Solicitação</th>${mostrarSetor ? html`<th scope="col">Setor</th>` : ""}<th scope="col">Etapa</th>
      <th scope="col">Urgência</th><th scope="col">Prazo</th><th scope="col" class="num">Valor</th><th scope="col">Atualização</th></tr></thead>
    <tbody>${itens.map((s) => html`<tr data-href="/solicitacoes/${s.id}" tabindex="0">
      <td class="principal-td"><div class="principal-celula"><span class="codigo">${s.codigo}${s.pedido_codigo ? html` · ${s.pedido_codigo}` : ""}</span>
        <a href="/solicitacoes/${s.id}">${s.titulo}</a>
        <small>${s.solicitante_nome}${s.itens_qtd ? html` · ${s.itens_qtd} ${s.itens_qtd === 1 ? "item" : "itens"}` : ""}${s.fornecedor_fantasia || s.fornecedor_nome ? html` · ${s.fornecedor_fantasia || s.fornecedor_nome}` : ""}</small></div></td>
      ${mostrarSetor ? html`<td data-rotulo="Setor">${badgeSetor(s.setor_codigo, s.setor_nome, s.setor_cor)}</td>` : ""}
      <td data-rotulo="Etapa"><div class="pilha-sm">${badgeStatus(s.status)}${miniFluxo(s)}</div></td>
      <td data-rotulo="Urgência">${badgeUrgencia(s.urgencia)}</td>
      <td data-rotulo="Prazo">${badgeSla(s.sla_situacao, s.sla_horas_restantes)}</td>
      <td data-rotulo="${s.valor_final ? "Contratado" : "Estimado"}" class="num"><strong>${formato.moeda(s.valor_final ?? s.valor_estimado)}</strong><br><small class="texto-3">${s.valor_final ? "contratado" : "estimado"}</small></td>
      <td data-rotulo="Atualização" class="nowrap texto-3 pequeno" title="${formato.dataHora(s.atualizado_em)}">${formato.relativo(s.atualizado_em)}</td>
    </tr>`)}</tbody></table></div>`;
}

export async function montar({ raiz, consulta }) {
  const u = estado.usuario;
  const doSetor = ["solicitante", "gestor"].includes(u.papel);
  const filtros = {
    etapa: consulta.etapa || "", q: consulta.q || "", setor: consulta.setor || "", urgencia: consulta.urgencia || "",
    tipo: consulta.tipo || "", sla: consulta.sla || "", ordem: consulta.ordem || "recentes", minhas: consulta.minhas === "1",
    status: consulta.status || "", pagina: Number(consulta.pagina) || 1,
  };
  const subtitulo = doSetor ? `Solicitações do setor ${u.setor_nome}`
    : u.papel === "comprador" ? "Solicitações aprovadas encaminhadas ao setor de Compras"
      : u.papel === "recebimento" ? "Solicitações com pedido de compra emitido" : "Todas as solicitações de compra do hospital";

  renderizar(raiz, html`
    ${cabecalho({
      titulo: "Solicitações de compra", sub: subtitulo,
      acoes: html`<button class="botao secundario" id="btn-csv">${icone("planilha")}Exportar CSV</button>
        <button class="botao secundario" id="btn-pdf">${icone("pdf")}PDF</button>
        ${pode("solicitacao.criar") ? html`<a class="botao" href="/solicitacoes/nova">${icone("mais")}Nova solicitação</a>` : ""}`,
    })}
    <section class="cartao">
      <div id="abas"></div>
      <form class="barra-filtros" id="filtros" role="search" aria-label="Filtrar solicitações">
        <label class="busca"><span class="sr-only">Buscar</span>${icone("busca")}<input class="entrada" type="search" name="q" value="${filtros.q}" placeholder="Código, título, solicitante, fornecedor ou pedido"></label>
        ${doSetor ? "" : html`<select class="entrada" name="setor" aria-label="Setor">${opcoesSetores(estado.meta.setores, filtros.setor, { vazio: "Todos os setores", somenteOperacionais: true })}</select>`}
        <select class="entrada" name="urgencia" aria-label="Urgência">${opcoes(estado.meta.rotulos.urgencia, filtros.urgencia, { vazio: "Qualquer urgência" })}</select>
        <select class="entrada" name="tipo" aria-label="Tipo">${opcoes(estado.meta.rotulos.tipo_solicitacao, filtros.tipo, { vazio: "Todos os tipos" })}</select>
        <select class="entrada" name="sla" aria-label="Prazo de atendimento">${opcoes({ estourado: "Prazo estourado", alerta: "Vence em < 24 h", dentro_prazo: "No prazo" }, filtros.sla, { vazio: "Qualquer prazo" })}</select>
        <select class="entrada" name="ordem" aria-label="Ordenação">${opcoes({ recentes: "Mais recentes", sla: "Prazo mais próximo", urgencia: "Maior urgência", valor: "Maior valor", antigas: "Mais antigas" }, filtros.ordem)}</select>
        ${["comprador", "solicitante"].includes(u.papel) ? html`<label class="checkbox pequeno"><input type="checkbox" name="minhas" ${filtros.minhas ? html`checked` : ""}><span>${u.papel === "comprador" ? "Sob minha responsabilidade" : "Abertas por mim"}</span></label>` : ""}
      </form>
      <div id="resumo"></div>
      <div id="lista">${carregandoBloco(6)}</div>
    </section>`);

  const alvoAbas = raiz.querySelector("#abas");
  const lista = raiz.querySelector("#lista");
  const form = raiz.querySelector("#filtros");
  let controlador;

  function parametros() {
    const p = { ...filtros, por_pagina: 20 };
    if (!p.minhas) delete p.minhas;
    return p;
  }

  async function carregarContagem() {
    try {
      const c = await api.get("/solicitacoes/contagem");
      renderizar(alvoAbas, abas(ETAPAS.map((e) => ({ ...e, qtd: e.valor ? c.etapas[e.valor] : c.total })), filtros.etapa, { nome: "etapa" }));
    } catch { renderizar(alvoAbas, abas(ETAPAS, filtros.etapa, { nome: "etapa" })); }
  }

  async function carregar() {
    controlador?.abort();
    controlador = new AbortController();
    atualizarConsulta({ ...filtros, pagina: filtros.pagina > 1 ? filtros.pagina : "", ordem: filtros.ordem === "recentes" ? "" : filtros.ordem });
    lista.setAttribute("aria-busy", "true");
    try {
      const r = await api.get("/solicitacoes", parametros(), { sinal: controlador.signal });
      renderizar(raiz.querySelector("#resumo"), r.total ? html`<div class="resumo-lista"><span><strong>${formato.numero(r.total)}</strong> solicitação(ões)</span><span>Valor total <strong>${formato.moeda(r.valor_total)}</strong></span></div>` : "");
      renderizar(lista, r.itens.length
        ? html`${tabelaSolicitacoes(r.itens, { mostrarSetor: !doSetor })}${paginacao(r)}`
        : vazio("Nenhuma solicitação encontrada", filtros.q || filtros.setor || filtros.etapa ? "Ajuste os filtros para ver outros resultados." : "Ainda não há solicitações por aqui.",
          pode("solicitacao.criar") ? html`<a class="botao" href="/solicitacoes/nova">${icone("mais")}Nova solicitação</a>` : "", "documento"));
    } catch (e) {
      if (e.name !== "AbortError") { renderizar(lista, vazio("Não foi possível carregar", e.message, "", "alerta")); }
    } finally { lista.removeAttribute("aria-busy"); }
  }

  const aplicar = debounce(() => { Object.assign(filtros, lerForm(), { pagina: 1 }); carregar(); }, 300);
  function lerForm() {
    const d = Object.fromEntries(new FormData(form));
    return { q: d.q || "", setor: d.setor || "", urgencia: d.urgencia || "", tipo: d.tipo || "", sla: d.sla || "", ordem: d.ordem || "recentes", minhas: d.minhas === "on" };
  }
  form.addEventListener("input", aplicar);
  form.addEventListener("change", aplicar);
  form.addEventListener("submit", (e) => e.preventDefault());
  on(alvoAbas, "click", "[data-etapa]", (e, b) => {
    filtros.etapa = b.dataset.etapa; filtros.status = ""; filtros.pagina = 1;
    alvoAbas.querySelectorAll("[data-etapa]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    carregar();
  });
  on(lista, "click", "[data-pagina]", (e, b) => { filtros.pagina = Number(b.dataset.pagina); carregar(); raiz.scrollIntoView({ block: "start" }); });
  ativarLinhasClicaveis(lista);
  raiz.querySelector("#btn-csv").addEventListener("click", (e) => comCarregamento(e.currentTarget, api.baixar("/solicitacoes/exportar.csv", parametros())).catch(toastErro));
  raiz.querySelector("#btn-pdf").addEventListener("click", (e) => comCarregamento(e.currentTarget, api.baixar("/solicitacoes/relatorio.pdf", parametros())).catch(toastErro));

  await Promise.all([carregarContagem(), carregar()]);
}

export { rotulo };
