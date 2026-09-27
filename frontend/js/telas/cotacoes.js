// Cotações: solicitações aprovadas aguardando o comprador, em cotação e com fornecedor definido.
import { api } from "../api.js";
import { estado } from "../estado.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { abas, ativarLinhasClicaveis, badgeSetor, badgeSla, badgeUrgencia, cabecalho, carregandoBloco, formato, paginacao, vazio } from "../ui/componentes.js";

const GRUPOS = {
  aprovada: { rotulo: "Aguardando início", icone: "play", ajuda: "Solicitações aprovadas que ainda não foram assumidas por um comprador." },
  em_cotacao: { rotulo: "Em cotação", icone: "balanca", ajuda: "Registre as propostas recebidas e compare os preços por item." },
  aguardando_pedido: { rotulo: "Fornecedor definido", icone: "fornecedor", ajuda: "Emita o pedido de compra para seguir à aprovação financeira." },
};

export async function montar({ raiz, consulta }) {
  let grupo = GRUPOS[consulta.grupo] ? consulta.grupo : "em_cotacao";
  let pagina = 1;
  const comprador = estado.usuario.papel === "comprador";
  renderizar(raiz, html`${cabecalho({ titulo: "Cotações", sub: "Condução das cotações com fornecedores, do início à definição do vencedor" })}
    <section class="cartao"><div id="abas"></div>
      <form class="barra-filtros" id="filtros" role="search"><label class="busca"><span class="sr-only">Buscar</span>${icone("busca")}<input class="entrada" type="search" name="q" placeholder="Código, título ou setor"></label>
        ${comprador ? html`<label class="checkbox pequeno"><input type="checkbox" name="minhas"><span>Somente as minhas</span></label>` : ""}</form>
      <div id="ajuda"></div><div id="lista">${carregandoBloco(5)}</div></section>`);
  const lista = raiz.querySelector("#lista");
  const form = raiz.querySelector("#filtros");

  async function carregarAbas() {
    const c = await api.get("/solicitacoes/contagem");
    renderizar(raiz.querySelector("#abas"), abas(Object.entries(GRUPOS).map(([v, g]) => ({ valor: v, rotulo: g.rotulo, icone: g.icone, qtd: c.por_status[v] || 0 })), grupo, { nome: "grupo" }));
  }
  async function carregar() {
    atualizarConsulta({ grupo: grupo === "em_cotacao" ? "" : grupo });
    renderizar(raiz.querySelector("#ajuda"), html`<div class="resumo-lista">${icone("info")}<span>${GRUPOS[grupo].ajuda}</span></div>`);
    const d = Object.fromEntries(new FormData(form));
    try {
      const r = await api.get("/solicitacoes", { status: grupo, q: d.q, minhas: d.minhas === "on", ordem: "sla", pagina, por_pagina: 25 });
      renderizar(lista, r.itens.length ? html`<div class="tabela-envoltorio"><table class="tabela responsiva">
        <thead><tr><th>Solicitação</th><th>Setor</th><th>Urgência</th><th>Prazo</th><th class="num">Propostas</th><th class="num">${grupo === "aguardando_pedido" ? "Vencedora" : "Estimado"}</th><th>Comprador</th></tr></thead>
        <tbody>${r.itens.map((s) => html`<tr data-href="/solicitacoes/${s.id}?aba=cotacao" tabindex="0">
          <td class="principal-td"><div class="principal-celula"><span class="codigo">${s.codigo}</span><a href="/solicitacoes/${s.id}?aba=cotacao">${s.titulo}</a><small>${s.itens_qtd} item(ns) · ${s.solicitante_nome}</small></div></td>
          <td data-rotulo="Setor">${badgeSetor(s.setor_codigo, s.setor_nome, s.setor_cor)}</td><td data-rotulo="Urgência">${badgeUrgencia(s.urgencia)}</td>
          <td data-rotulo="Prazo">${badgeSla(s.sla_situacao, s.sla_horas_restantes)}</td>
          <td data-rotulo="Propostas" class="num">${s.cotacoes_qtd ? html`<span class="badge ${s.cotacoes_qtd >= 3 ? "sucesso" : "alerta"}">${s.cotacoes_qtd}</span>` : html`<span class="texto-3">0</span>`}</td>
          <td data-rotulo="Valor" class="num"><strong>${formato.moeda(s.valor_final ?? s.valor_estimado)}</strong>${s.fornecedor_fantasia ? html`<br><small class="texto-3">${s.fornecedor_fantasia}</small>` : ""}</td>
          <td data-rotulo="Comprador">${s.comprador_nome || html`<span class="texto-3">A definir</span>`}</td></tr>`)}</tbody></table></div>${paginacao(r)}`
        : vazio("Nada por aqui", "Não há solicitações nesta etapa.", "", GRUPOS[grupo].icone));
    } catch (e) { renderizar(lista, vazio("Não foi possível carregar", e.message, "", "alerta")); }
  }
  on(raiz, "click", "[data-grupo]", (e, b) => { grupo = b.dataset.grupo; pagina = 1; raiz.querySelectorAll("[data-grupo]").forEach((x) => x.setAttribute("aria-selected", String(x === b))); carregar(); });
  on(lista, "click", "[data-pagina]", (e, b) => { pagina = Number(b.dataset.pagina); carregar(); });
  form.addEventListener("input", debounce(() => { pagina = 1; carregar(); }, 300));
  form.addEventListener("submit", (e) => e.preventDefault());
  ativarLinhasClicaveis(lista);
  await Promise.all([carregarAbas(), carregar()]);
}
