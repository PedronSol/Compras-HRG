// Lista de pedidos de compra com abas por situação, atrasos e exportação.
import { api } from "../api.js";
import { estado } from "../estado.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import {
  abas, ativarLinhasClicaveis, badgePedido, badgeSetor, cabecalho, carregandoBloco, comCarregamento, formato,
  opcoesSetores, paginacao, toastErro, vazio,
} from "../ui/componentes.js";

export const GRUPOS = {
  "": { rotulo: "Todos", status: "" },
  aprovacao: { rotulo: "Em aprovação", status: "aguardando_financeiro,aguardando_diretoria" },
  aprovado: { rotulo: "Aprovados · a enviar", status: "aprovado" },
  entrega: { rotulo: "Aguardando entrega", status: "enviado,entregue_parcial" },
  entregue: { rotulo: "Entregues", status: "entregue" },
  encerrados: { rotulo: "Reprovados e cancelados", status: "reprovado,cancelado" },
};

export function tabelaPedidos(itens, { mostrarSetor = true } = {}) {
  return html`<div class="tabela-envoltorio"><table class="tabela responsiva">
    <thead><tr><th>Pedido</th><th>Fornecedor</th>${mostrarSetor ? html`<th>Setor</th>` : ""}<th>Situação</th><th class="num">Valor</th><th>Previsão</th><th>Recebido</th></tr></thead>
    <tbody>${itens.map((p) => html`<tr data-href="/pedidos/${p.id}" tabindex="0" class="${p.atrasado ? "atrasada" : ""}">
      <td class="principal-td"><div class="principal-celula"><a href="/pedidos/${p.id}">${p.codigo}</a><small>${p.solicitacao_codigo} · ${p.solicitacao_titulo}</small></div></td>
      <td data-rotulo="Fornecedor"><div class="principal-celula"><span>${p.fornecedor_fantasia || p.fornecedor_nome}</span><small class="mono">${formato.cnpj(p.fornecedor_cnpj)}</small></div></td>
      ${mostrarSetor ? html`<td data-rotulo="Setor">${badgeSetor(p.setor_codigo, p.setor_nome, p.setor_cor)}</td>` : ""}
      <td data-rotulo="Situação">${badgePedido(p.status)}${p.atrasado ? html`<br><span class="badge perigo">${icone("alerta")}${p.dias_atraso} dia(s) de atraso</span>` : ""}</td>
      <td data-rotulo="Valor" class="num"><strong>${formato.moeda(p.valor_total)}</strong></td>
      <td data-rotulo="Previsão" class="nowrap">${formato.data(p.data_prevista_entrega)}</td>
      <td data-rotulo="Recebido"><div class="progresso-rotulado"><div class="progresso ${p.percentual_recebido >= 100 ? "sucesso" : ""}"><span data-largura="${p.percentual_recebido}"></span></div>${p.percentual_recebido}%</div></td>
    </tr>`)}</tbody></table></div>`;
}

export async function montar({ raiz, consulta }) {
  const filtros = { grupo: GRUPOS[consulta.grupo] ? consulta.grupo : "", q: consulta.q || "", setor: consulta.setor || "", atrasados: consulta.atrasados === "1", pagina: 1 };
  const doSetor = ["solicitante", "gestor"].includes(estado.usuario.papel);
  renderizar(raiz, html`
    ${cabecalho({ titulo: "Pedidos de compra", sub: "Emissão, aprovação financeira, envio ao fornecedor e acompanhamento das entregas",
      acoes: html`<button class="botao secundario" id="btn-csv">${icone("planilha")}Exportar CSV</button>` })}
    <section class="cartao"><div id="abas"></div>
      <form class="barra-filtros" id="filtros" role="search">
        <label class="busca"><span class="sr-only">Buscar</span>${icone("busca")}<input class="entrada" type="search" name="q" value="${filtros.q}" placeholder="Pedido, solicitação ou fornecedor"></label>
        ${doSetor ? "" : html`<select class="entrada" name="setor" aria-label="Setor">${opcoesSetores(estado.meta.setores, filtros.setor, { vazio: "Todos os setores", somenteOperacionais: true })}</select>`}
        <label class="checkbox pequeno"><input type="checkbox" name="atrasados" ${filtros.atrasados ? html`checked` : ""}><span>Somente entregas atrasadas</span></label>
      </form><div id="resumo"></div><div id="lista">${carregandoBloco(6)}</div></section>`);
  const lista = raiz.querySelector("#lista");
  const form = raiz.querySelector("#filtros");
  const params = () => ({ status: GRUPOS[filtros.grupo].status, q: filtros.q, setor: filtros.setor, atrasados: filtros.atrasados, pagina: filtros.pagina, por_pagina: 20 });

  async function carregarAbas() {
    const c = await api.get("/pedidos/contagem");
    const soma = (st) => st.split(",").reduce((t, s) => t + (c.por_status[s] || 0), 0);
    renderizar(raiz.querySelector("#abas"), abas(Object.entries(GRUPOS).map(([v, g]) => ({ valor: v, rotulo: g.rotulo, qtd: v ? soma(g.status) : c.total })), filtros.grupo, { nome: "grupo" }));
  }
  async function carregar() {
    atualizarConsulta({ grupo: filtros.grupo, q: filtros.q, setor: filtros.setor, atrasados: filtros.atrasados });
    try {
      const r = await api.get("/pedidos", params());
      renderizar(raiz.querySelector("#resumo"), r.total ? html`<div class="resumo-lista"><span><strong>${r.total}</strong> pedido(s)</span><span>Valor total <strong>${formato.moeda(r.valor_total)}</strong></span></div>` : "");
      renderizar(lista, r.itens.length ? html`${tabelaPedidos(r.itens, { mostrarSetor: !doSetor })}${paginacao(r)}` : vazio("Nenhum pedido encontrado", "Os pedidos são emitidos pelo comprador após a definição do fornecedor.", "", "pedido"));
    } catch (e) { renderizar(lista, vazio("Não foi possível carregar", e.message, "", "alerta")); }
  }
  const aplicar = debounce(() => { const d = Object.fromEntries(new FormData(form)); Object.assign(filtros, { q: d.q || "", setor: d.setor || "", atrasados: d.atrasados === "on", pagina: 1 }); carregar(); }, 300);
  form.addEventListener("input", aplicar);
  form.addEventListener("submit", (e) => e.preventDefault());
  on(raiz, "click", "[data-grupo]", (e, b) => { filtros.grupo = b.dataset.grupo; filtros.pagina = 1; raiz.querySelectorAll("[data-grupo]").forEach((x) => x.setAttribute("aria-selected", String(x === b))); carregar(); });
  on(lista, "click", "[data-pagina]", (e, b) => { filtros.pagina = Number(b.dataset.pagina); carregar(); });
  ativarLinhasClicaveis(lista);
  raiz.querySelector("#btn-csv").addEventListener("click", (e) => comCarregamento(e.currentTarget, api.baixar("/pedidos/exportar.csv", params())).catch(toastErro));
  await Promise.all([carregarAbas().catch(() => {}), carregar()]);
}
