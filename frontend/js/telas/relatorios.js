// Relatórios e indicadores: desempenho do processo, gastos por setor/categoria/fornecedor, compradores e exportações.
import { api } from "../api.js";
import { estado } from "../estado.js";
import { navegar } from "../roteador.js";
import { html, renderizar, on } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { barrasHorizontais, colunas, ativarGraficos } from "../ui/graficos.js";
import { cabecalho, comCarregamento, formato, kpi, opcoesSetores, pode, toast, toastErro, vazio } from "../ui/componentes.js";

export async function montar({ raiz, consulta }) {
  const doSetor = ["solicitante", "gestor"].includes(estado.usuario.papel);
  const hoje = formato.hojeISO();
  const inicio = /^\d{4}-\d{2}-\d{2}$/.test(consulta.inicio || "") ? consulta.inicio : formato.isoDias(-180);
  const fim = /^\d{4}-\d{2}-\d{2}$/.test(consulta.fim || "") ? consulta.fim : hoje;
  const setor = doSetor ? "" : consulta.setor || "";
  const p = await api.get("/painel", { inicio, fim, setor });
  const k = p.kpis;
  const params = { inicio, fim, setor };
  const totalCat = p.por_categoria.reduce((t, c) => t + (c.valor || 0), 0) || 1;

  renderizar(raiz, html`
    ${cabecalho({ titulo: "Relatórios e indicadores", sub: "Documentos institucionais com código de verificação SHA-256 registrado na auditoria" })}
    <div class="pilha-lg">
      <section class="cartao"><form class="barra-filtros" id="f-per">
        <div class="campo"><label for="r-ini">De</label><input class="entrada" id="r-ini" type="date" name="inicio" value="${inicio}" max="${hoje}"></div>
        <div class="campo"><label for="r-fim">Até</label><input class="entrada" id="r-fim" type="date" name="fim" value="${fim}" max="${hoje}"></div>
        ${doSetor ? "" : html`<div class="campo"><label for="r-setor">Setor</label><select class="entrada" id="r-setor" name="setor">${opcoesSetores(estado.meta.setores, setor, { vazio: "Todos os setores", somenteOperacionais: true })}</select></div>`}
        <button class="botao secundario" type="submit">${icone("filtro")}Aplicar</button>
        <span class="espacador"></span>
        <button class="botao" type="button" data-baixar="executivo">${icone("pdf")}Relatório executivo (PDF)</button>
      </form></section>

      <div class="kpis">
        ${kpi({ rotulo: "Valor contratado", valor: formato.moedaCompacta(k.valor_contratado), icone: "moeda", tom: "sucesso", meta: `${k.pedidos} pedidos · ticket médio ${formato.moedaCompacta(k.ticket_medio)}` })}
        ${kpi({ rotulo: "Economia sobre o estimado", valor: formato.moedaCompacta(k.economia), icone: "tendencia", meta: k.estimado_com_pedido ? `${formato.percentual(k.economia / k.estimado_com_pedido)} do valor estimado` : "—" })}
        ${kpi({ rotulo: "Solicitações no período", valor: formato.numero(k.solicitacoes), icone: "documento", meta: `${k.concluidas} concluídas · ${k.encerradas_sem_compra} reprovadas/canceladas` })}
        ${kpi({ rotulo: "Prazo de atendimento cumprido", valor: formato.percentual(k.sla_cumprimento), icone: "relogio", meta: `Abertura até pedido: ${formato.dias(k.tempo_ate_pedido_dias)}` })}
      </div>

      <div class="grade-2">
        <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("relogio")}Tempo médio por etapa do processo</h2></div>
          <div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Etapa</th><th class="num">Média</th></tr></thead><tbody>
            <tr><td>Abertura → aprovação final</td><td class="num">${formato.dias(k.tempo_aprovacao_dias)}</td></tr>
            <tr><td>Início da cotação → fornecedor definido</td><td class="num">${formato.dias(k.tempo_cotacao_dias)}</td></tr>
            <tr><td>Abertura → pedido emitido</td><td class="num">${formato.dias(k.tempo_ate_pedido_dias)}</td></tr>
            <tr><td>Abertura → entrega conferida (lead time)</td><td class="num"><strong>${formato.dias(k.lead_time_dias)}</strong></td></tr>
            <tr><td>Entregas dentro do prazo</td><td class="num">${k.pontualidade_entregas === null ? "—" : `${Math.round(k.pontualidade_entregas)}%`}</td></tr>
          </tbody></table></div></section>
        <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("moeda")}Valor contratado por mês</h2></div>
          <div class="cartao-corpo">${colunas({ categorias: p.por_mes.map((m) => m.mes.slice(0, 2) + "/" + m.mes.slice(-2)), valores: p.por_mes.map((m) => m.valor), formatar: formato.moeda, titulo: "Valor contratado por mês" })}</div></section>
      </div>

      <div class="grade-2">
        ${doSetor ? "" : html`<section class="cartao"><div class="cartao-cabecalho"><h2>${icone("predio")}Gastos por setor</h2></div>
          ${p.por_setor.length ? html`<div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Setor</th><th class="num">Pedidos</th><th class="num">Valor</th></tr></thead>
            <tbody>${p.por_setor.map((s) => html`<tr><td><span class="badge setor" data-cor="${s.setor_cor}"><span class="ponto"></span>${s.setor_nome}</span></td><td class="num">${s.pedidos}</td><td class="num"><strong>${formato.moeda(s.valor)}</strong></td></tr>`)}</tbody></table></div>`
            : vazio("Sem pedidos no período", "", "", "predio", true)}</section>`}
        <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("etiqueta")}Gastos por categoria</h2></div>
          ${p.por_categoria.length ? html`<div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Categoria</th><th class="num">Participação</th><th class="num">Valor</th></tr></thead>
            <tbody>${p.por_categoria.map((c) => html`<tr><td><span class="linha-flex"><span class="cor-amostra" data-cor="${c.cor}"></span>${c.categoria}</span></td><td class="num">${formato.percentual(c.valor / totalCat)}</td><td class="num"><strong>${formato.moeda(c.valor)}</strong></td></tr>`)}</tbody></table></div>`
            : vazio("Sem pedidos no período", "", "", "etiqueta", true)}</section>
        <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("fornecedor")}Principais fornecedores</h2></div>
          <div class="cartao-corpo">${barrasHorizontais(p.top_fornecedores.map((f) => ({ rotulo: f.fornecedor, valor: f.valor })), { formatar: formato.moedaCompacta })}</div></section>
        ${doSetor ? "" : html`<section class="cartao"><div class="cartao-cabecalho"><h2>${icone("carrinho")}Desempenho dos compradores</h2></div>
          ${p.por_comprador.length ? html`<div class="tabela-envoltorio"><table class="tabela"><thead><tr><th>Comprador</th><th class="num">Em andamento</th><th class="num">Pedidos emitidos</th><th class="num">Tempo médio de cotação</th></tr></thead>
            <tbody>${p.por_comprador.map((c) => html`<tr><td>${c.comprador_nome}</td><td class="num">${c.em_andamento}</td><td class="num">${c.pedidos}</td><td class="num">${formato.dias(c.tempo_cotacao_dias)}</td></tr>`)}</tbody></table></div>`
            : vazio("Sem dados", "", "", "carrinho", true)}</section>`}
      </div>

      <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("download")}Exportações</h2><span class="subtitulo">Os arquivos respeitam o período e o setor selecionados e o escopo do seu perfil.</span></div>
        <ul class="lista-itens">
          <li><div class="item-lista"><span class="icone-item info">${icone("relatorio")}</span><span class="corpo-item"><strong>Relatório executivo</strong><small>Indicadores, funil, gastos por setor e categoria, fornecedores</small></span>
            <span class="grupo-botoes"><button class="botao secundario pequeno" data-baixar="executivo">${icone("pdf")}PDF</button></span></div></li>
          <li><div class="item-lista"><span class="icone-item">${icone("documento")}</span><span class="corpo-item"><strong>Solicitações de compra</strong><small>Status, prazos, solicitante, comprador, fornecedor e valores</small></span>
            <span class="grupo-botoes"><button class="botao secundario pequeno" data-baixar="sol-csv">${icone("planilha")}CSV</button><button class="botao secundario pequeno" data-baixar="sol-pdf">${icone("pdf")}PDF</button></span></div></li>
          ${pode("pedido.ver") ? html`<li><div class="item-lista"><span class="icone-item petroleo">${icone("pedido")}</span><span class="corpo-item"><strong>Pedidos de compra</strong><small>Fornecedor, CNPJ, status, valores, previsão e percentual recebido</small></span>
            <span class="grupo-botoes"><button class="botao secundario pequeno" data-baixar="ped-csv">${icone("planilha")}CSV</button></span></div></li>` : ""}
        </ul></section>
    </div>`);
  ativarGraficos(raiz);

  raiz.querySelector("#f-per").addEventListener("submit", (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.currentTarget));
    if (d.inicio > d.fim) { toast("alerta", "Período inválido", "A data inicial deve ser anterior à final."); return; }
    navegar(`/relatorios?${new URLSearchParams(Object.entries(d).filter(([, v]) => v))}`, { substituir: true });
  });
  const rotas = {
    executivo: ["/painel/relatorio.pdf", params], "sol-pdf": ["/solicitacoes/relatorio.pdf", params],
    "sol-csv": ["/solicitacoes/exportar.csv", params], "ped-csv": ["/pedidos/exportar.csv", { inicio, fim, setor }],
  };
  on(raiz, "click", "[data-baixar]", async (e, b) => {
    const [caminho, q] = rotas[b.dataset.baixar];
    try { await comCarregamento(b, api.baixar(caminho, Object.fromEntries(Object.entries(q).filter(([, v]) => v)))); toast("sucesso", "Arquivo gerado", "O download foi iniciado."); }
    catch (err) { toastErro(err); }
  });
}

