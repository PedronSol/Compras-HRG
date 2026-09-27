// Recebimento: entregas aguardadas (com atrasos em destaque), registro com conferência e histórico.
import { api } from "../api.js";
import { estado } from "../estado.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import {
  abas, ativarLinhasClicaveis, badgePedido, badgeRecebimento, badgeSetor, cabecalho, carregandoBloco, formato, kpi,
  opcoes, paginacao, vazio, pode,
} from "../ui/componentes.js";
import { modalRecebimento } from "./pedido-detalhe.js";

export async function montar({ raiz, consulta }) {
  let aba = consulta.aba === "historico" ? "historico" : "aguardando";
  const podeReceber = pode("recebimento.registrar");
  renderizar(raiz, html`
    ${cabecalho({ titulo: "Recebimento e conferência", sub: "Entregas previstas, registro de notas fiscais e conferência de quantidades" })}
    <div class="pilha">
      <div class="kpis compactos" id="kpis">${carregandoBloco(1)}</div>
      <section class="cartao"><div id="abas"></div>
        <form class="barra-filtros" id="filtros" role="search"><label class="busca"><span class="sr-only">Buscar</span>${icone("busca")}<input class="entrada" type="search" name="q" placeholder="Pedido, nota fiscal ou fornecedor"></label>
          <select class="entrada oculto" name="situacao" aria-label="Situação">${opcoes(estado.meta.rotulos.situacao_recebimento, "", { vazio: "Qualquer situação" })}</select></form>
        <div id="lista">${carregandoBloco(5)}</div></section>
    </div>`);
  const lista = raiz.querySelector("#lista");
  const form = raiz.querySelector("#filtros");
  let pagina = 1;

  async function resumo() {
    const [c, recs] = await Promise.all([api.get("/pedidos/contagem"), api.get("/recebimentos", { por_pagina: 100 })]);
    const aguardando = (c.por_status.enviado || 0) + (c.por_status.entregue_parcial || 0);
    const mes = recs.itens.filter((r) => new Date(r.recebido_em) > new Date(Date.now() - 30 * 86400000));
    const diverg = mes.filter((r) => r.situacao !== "conforme").length;
    renderizar(raiz.querySelector("#kpis"), html`
      ${kpi({ rotulo: "Aguardando entrega", valor: aguardando, icone: "caminhao", tom: "petroleo" })}
      ${kpi({ rotulo: "Entregas atrasadas", valor: c.atrasados, icone: "alerta", tom: c.atrasados ? "perigo" : "sucesso", meta: c.atrasados ? "Contate os fornecedores" : "Nenhum atraso" })}
      ${kpi({ rotulo: "Recebimentos (30 dias)", valor: mes.length, icone: "check_circulo", tom: "sucesso" })}
      ${kpi({ rotulo: "Com divergência (30 dias)", valor: diverg, icone: "devolver", tom: diverg ? "alerta" : "", meta: mes.length ? `${Math.round(100 - (100 * diverg) / mes.length)}% conformes` : "" })}`);
    renderizar(raiz.querySelector("#abas"), abas([{ valor: "aguardando", rotulo: "Aguardando entrega", icone: "caminhao", qtd: aguardando }, { valor: "historico", rotulo: "Recebimentos registrados", icone: "historico", qtd: recs.total }], aba, { nome: "aba" }));
  }

  async function carregar() {
    atualizarConsulta({ aba: aba === "historico" ? "historico" : "" });
    form.situacao.classList.toggle("oculto", aba !== "historico");
    const q = form.q.value.trim();
    try {
      if (aba === "aguardando") {
        const r = await api.get("/pedidos", { status: "enviado,entregue_parcial", q, ordem: "previsao", pagina, por_pagina: 30 });
        renderizar(lista, r.itens.length ? html`<div class="tabela-envoltorio"><table class="tabela responsiva">
          <thead><tr><th>Pedido</th><th>Fornecedor</th><th>Setor</th><th>Previsão</th><th>Recebido</th><th class="col-acao"><span class="sr-only">Ações</span></th></tr></thead>
          <tbody>${r.itens.map((p) => html`<tr data-href="/pedidos/${p.id}" tabindex="0" class="${p.atrasado ? "atrasada" : ""}">
            <td class="principal-td"><div class="principal-celula"><a href="/pedidos/${p.id}">${p.codigo}</a><small>${p.solicitacao_titulo} · ${p.itens_qtd} item(ns) · ${formato.moeda(p.valor_total)}</small></div></td>
            <td data-rotulo="Fornecedor">${p.fornecedor_fantasia || p.fornecedor_nome}</td>
            <td data-rotulo="Setor">${badgeSetor(p.setor_codigo, p.setor_nome, p.setor_cor)}</td>
            <td data-rotulo="Previsão"><strong>${formato.data(p.data_prevista_entrega)}</strong><br>${p.atrasado ? html`<span class="badge perigo">${icone("alerta")}${p.dias_atraso} dia(s) de atraso</span>` : badgePedido(p.status)}</td>
            <td data-rotulo="Recebido"><div class="progresso-rotulado"><div class="progresso"><span data-largura="${p.percentual_recebido}"></span></div>${p.percentual_recebido}%</div></td>
            <td class="col-acao">${podeReceber ? html`<button class="botao pequeno" data-receber="${p.id}">${icone("caminhao")}Registrar entrega</button>` : ""}</td></tr>`)}</tbody></table></div>${paginacao(r)}`
          : vazio("Nenhuma entrega aguardada", "Os pedidos aparecem aqui quando o comprador os envia ao fornecedor.", "", "caminhao"));
      } else {
        const r = await api.get("/recebimentos", { q, situacao: form.situacao.value, pagina, por_pagina: 30 });
        renderizar(lista, r.itens.length ? html`<div class="tabela-envoltorio"><table class="tabela responsiva">
          <thead><tr><th>Recebimento</th><th>Nota fiscal</th><th>Fornecedor</th><th>Setor</th><th>Situação</th><th>Conferente</th><th>Data</th></tr></thead>
          <tbody>${r.itens.map((x) => html`<tr data-href="/pedidos/${x.pedido_id}" tabindex="0">
            <td class="principal-td"><div class="principal-celula"><strong>${x.codigo}</strong><small>${x.pedido_codigo} · ${x.solicitacao_titulo}</small></div></td>
            <td data-rotulo="Nota fiscal">NF ${x.nota_fiscal}${x.valor_nf ? html`<br><small class="texto-3">${formato.moeda(x.valor_nf)}</small>` : ""}</td>
            <td data-rotulo="Fornecedor">${x.fornecedor_fantasia || x.fornecedor_nome}</td><td data-rotulo="Setor">${badgeSetor(null, x.setor_nome, x.setor_cor)}</td>
            <td data-rotulo="Situação">${badgeRecebimento(x.situacao)}</td><td data-rotulo="Conferente">${x.recebido_por_nome}</td>
            <td data-rotulo="Data" class="nowrap">${formato.dataHora(x.recebido_em)}</td></tr>`)}</tbody></table></div>${paginacao(r)}`
          : vazio("Nenhum recebimento registrado", "", "", "historico"));
      }
    } catch (e) { renderizar(lista, vazio("Não foi possível carregar", e.message, "", "alerta")); }
  }

  on(raiz, "click", "[data-aba]", (e, b) => { aba = b.dataset.aba; pagina = 1; raiz.querySelectorAll("[data-aba]").forEach((x) => x.setAttribute("aria-selected", String(x === b))); carregar(); });
  on(lista, "click", "[data-receber]", async (e, b) => { e.stopPropagation(); const r = await modalRecebimento(b.dataset.receber); if (r) { resumo(); carregar(); } });
  on(lista, "click", "[data-pagina]", (e, b) => { pagina = Number(b.dataset.pagina); carregar(); });
  ativarLinhasClicaveis(lista);
  form.addEventListener("input", debounce(() => { pagina = 1; carregar(); }, 300));
  form.addEventListener("submit", (e) => e.preventDefault());
  await Promise.all([resumo(), carregar()]);
}
