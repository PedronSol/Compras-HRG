// Painel: pendências do usuário, indicadores, funil do fluxo, evolução, gastos por setor/categoria e prazos.
import { api } from "../api.js";
import { estado, rotulo } from "../estado.js";
import { navegar } from "../roteador.js";
import { html, renderizar } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { barrasHorizontais, colunas, linhas, tabelaDados, ativarGraficos } from "../ui/graficos.js";
import {
  badgePedido, badgeSla, badgeStatus, cabecalho, formato, kpi, opcoes, pode, toastErro, vazio, comCarregamento,
} from "../ui/componentes.js";

const PERIODOS = { 30: "Últimos 30 dias", 90: "Últimos 90 dias", 180: "Últimos 6 meses", 365: "Últimos 12 meses" };
const DO_SETOR = ["solicitante", "gestor"];
const ICONE_ETAPA = { aprovacao: "carimbo", cotacao: "balanca", fornecedor: "fornecedor", pedido: "pedido", recebimento: "caminhao" };

function saudacao() {
  const h = Number(new Intl.DateTimeFormat("pt-BR", { hour: "numeric", hourCycle: "h23", timeZone: "America/Sao_Paulo" }).format(new Date()));
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}

const ACAO_SOLICITACAO = {
  aguardando_gestor: "Aprovar", aguardando_diretoria: "Aprovar", devolvida: "Ajustar e reenviar", aprovada: "Iniciar cotação",
  em_cotacao: "Registrar propostas", aguardando_pedido: "Emitir pedido",
};
const ACAO_PEDIDO = { aguardando_financeiro: "Aprovar pedido", aguardando_diretoria: "Aprovar pedido", aprovado: "Enviar ao fornecedor", enviado: "Registrar entrega", entregue_parcial: "Registrar entrega" };

function blocoPendencias(pend) {
  const itens = [
    ...pend.solicitacoes.map((s) => ({ href: `/solicitacoes/${s.id}`, icone: "documento", tom: s.sla_situacao === "estourado" ? "perigo" : "info", titulo: `${s.codigo} · ${s.titulo}`,
      sub: html`${s.setor_nome} · ${formato.moeda(s.valor_estimado)}`, lado: badgeStatus(s.status), acao: ACAO_SOLICITACAO[s.status], quando: s.atualizado_em })),
    ...pend.pedidos.map((p) => ({ href: `/pedidos/${p.id}`, icone: p.atrasado ? "alerta" : "pedido", tom: p.atrasado ? "perigo" : "petroleo", titulo: `${p.codigo} · ${p.fornecedor_fantasia || p.fornecedor_nome}`,
      sub: html`${p.solicitacao_codigo} · ${formato.moeda(p.valor_total)}${p.data_prevista_entrega ? html` · previsão ${formato.data(p.data_prevista_entrega)}` : ""}`, lado: badgePedido(p.status), acao: ACAO_PEDIDO[p.status], quando: p.atualizado_em })),
  ];
  const total = itens.length;
  return html`<section class="cartao ${total ? "destaque" : ""}" aria-labelledby="t-pend">
    <div class="cartao-cabecalho"><h2 id="t-pend">${icone("fila")}Requer sua ação</h2>
      ${total ? html`<span class="badge primaria">${total} pendente(s)</span><a class="botao fantasma pequeno" href="/pendencias">Ver todas${icone("seta_dir")}</a>` : ""}</div>
    ${total ? html`<ul class="lista-itens">${itens.slice(0, 5).map((i) => html`<li><a class="item-lista" href="${i.href}">
        <span class="icone-item ${i.tom}">${icone(i.icone)}</span>
        <span class="corpo-item"><strong>${i.titulo}</strong><small>${i.sub}</small></span>
        <span class="lado">${i.lado}<small>${i.acao || ""} · ${formato.relativo(i.quando)}</small></span></a></li>`)}</ul>`
      : vazio("Tudo em dia", "Não há solicitações ou pedidos aguardando uma ação sua.", "", "check_circulo", true)}
  </section>`;
}

function kpisPorPerfil(k, papel) {
  const economiaPct = k.estimado_com_pedido ? k.economia / k.estimado_com_pedido : null;
  if (DO_SETOR.includes(papel)) {
    return [
      kpi({ rotulo: "Em aberto no setor", valor: formato.numero(k.abertas), icone: "documento", href: "/solicitacoes?etapa=abertas",
        meta: k.sla_estourado ? html`<span class="negativo">${k.sla_estourado} com prazo estourado</span>` : "Todas dentro do prazo" }),
      kpi({ rotulo: "Em aprovação", valor: formato.numero(k.em_aprovacao), icone: "carimbo", tom: "violeta", href: "/solicitacoes?etapa=aprovacao", meta: "Gestor ou Diretoria" }),
      kpi({ rotulo: "Com o setor de Compras", valor: formato.numero(k.em_compras), icone: "balanca", href: "/solicitacoes?etapa=cotacao", meta: "Cotação e definição do fornecedor" }),
      kpi({ rotulo: "Aguardando entrega", valor: formato.numero(k.aguardando_entrega), icone: "caminhao", tom: "petroleo", href: "/solicitacoes?etapa=pedido",
        meta: k.atrasados ? html`<span class="negativo">${k.atrasados} entrega(s) atrasada(s)</span>` : "Sem atrasos" }),
      kpi({ rotulo: "Valor contratado", valor: formato.moedaCompacta(k.valor_contratado), icone: "moeda", tom: "sucesso", meta: `${k.pedidos} pedido(s) no período` }),
    ];
  }
  return [
    kpi({ rotulo: "Valor contratado", valor: formato.moedaCompacta(k.valor_contratado), icone: "moeda", tom: "sucesso",
      meta: html`${formato.numero(k.pedidos)} pedidos · ticket médio ${formato.moedaCompacta(k.ticket_medio)}`, href: pode("pedido.ver") ? "/pedidos" : "" }),
    kpi({ rotulo: "Economia obtida", valor: formato.moedaCompacta(k.economia), icone: "tendencia",
      meta: economiaPct !== null ? html`<span class="positivo">${formato.percentual(economiaPct)}</span> abaixo do estimado` : "Sem pedidos no período" }),
    kpi({ rotulo: "Solicitações em aberto", valor: formato.numero(k.abertas), icone: "documento", href: "/solicitacoes?etapa=abertas",
      meta: k.sla_estourado ? html`<span class="negativo">${k.sla_estourado} com prazo estourado</span>${k.sla_alerta ? html`<span class="nao-quebra"> · ${k.sla_alerta} vencendo</span>` : ""}` : html`${k.imediatas_abertas} com urgência imediata` }),
    kpi({ rotulo: "Prazo de atendimento", valor: formato.percentual(k.sla_cumprimento), icone: "relogio", tom: (k.sla_cumprimento ?? 1) < 0.8 ? "alerta" : "",
      meta: `Abertura até pedido: ${formato.dias(k.tempo_ate_pedido_dias)}` }),
    kpi({ rotulo: "Entregas no prazo", valor: k.pontualidade_entregas === null ? "—" : `${Math.round(k.pontualidade_entregas)}%`, icone: "caminhao", tom: "petroleo",
      meta: k.atrasados ? html`<span class="negativo">${k.atrasados} atrasada(s) agora</span>` : "Nenhuma entrega atrasada", href: pode("recebimento.ver") ? "/recebimentos" : "" }),
  ];
}

function funil(dados) {
  const max = Math.max(1, ...dados.map((f) => f.quantidade));
  return html`<div class="funil">${dados.map((f) => html`<a href="/solicitacoes?etapa=${f.etapa}" aria-label="${f.rotulo}: ${f.quantidade} solicitação(ões)">
    <span class="f-rotulo">${icone(ICONE_ETAPA[f.etapa])}${f.rotulo}</span>
    <span class="f-valor">${formato.numero(f.quantidade)}</span>
    <span class="f-barra"><span data-largura="${((f.quantidade / max) * 100).toFixed(0)}"></span></span>
    <span class="f-meta">${formato.moedaCompacta(f.valor)}</span></a>`)}</div>`;
}

function tempos(k) {
  const itens = [
    ["Aprovação", k.tempo_aprovacao_dias, "carimbo"], ["Cotação até fornecedor", k.tempo_cotacao_dias, "balanca"],
    ["Abertura até pedido", k.tempo_ate_pedido_dias, "pedido"], ["Ciclo completo", k.lead_time_dias, "caminhao"],
  ];
  const max = Math.max(1, ...itens.map((i) => i[1] || 0));
  return html`<div class="barras-lista">${itens.map(([r, v, ic]) => html`<div class="barra-linha" aria-label="${r}: ${formato.dias(v)}">
    <span class="rot">${icone(ic)}<span>${r}</span></span><span class="trilho"><span class="preench" data-largura="${(((v || 0) / max) * 100).toFixed(1)}"></span></span>
    <span class="v">${formato.dias(v)}</span></div>`)}</div>`;
}

export async function montar({ raiz, consulta }) {
  const u = estado.usuario;
  const dias = PERIODOS[consulta.periodo] ? Number(consulta.periodo) : 180;
  const [p, pend] = await Promise.all([
    api.get("/painel", { inicio: formato.isoDias(-dias), fim: formato.hojeISO() }),
    api.get("/painel/pendencias"),
  ]);
  const k = p.kpis;
  const doSetor = DO_SETOR.includes(u.papel);
  const primeiroNome = u.nome.split(" ")[0];
  const hoje = new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "numeric", month: "long", timeZone: "America/Sao_Paulo" }).format(new Date());
  const meses = p.por_mes.slice(-12);

  renderizar(raiz, html`
    ${cabecalho({
      titulo: `${saudacao()}, ${primeiroNome}`,
      sub: html`${hoje.charAt(0).toUpperCase() + hoje.slice(1)} · ${doSetor ? html`Indicadores do setor <strong>${u.setor_nome}</strong>` : `Visão ${rotulo("papel", u.papel)} de todos os setores`}`,
      acoes: html`<select class="entrada" id="periodo" aria-label="Período dos indicadores">${opcoes(PERIODOS, dias)}</select>
        ${pode("relatorio.ver") ? html`<button class="botao secundario" id="btn-pdf">${icone("pdf")}Relatório executivo</button>` : ""}
        ${pode("solicitacao.criar") ? html`<a class="botao" href="/solicitacoes/nova">${icone("mais")}Nova solicitação</a>` : ""}`,
    })}
    <div class="pilha-lg">
      ${pend.solicitacoes.length || pend.pedidos.length || !["admin", "auditoria"].includes(u.papel) ? blocoPendencias(pend) : ""}
      <div class="kpis">${kpisPorPerfil(k, u.papel)}</div>
      <section class="cartao" aria-labelledby="t-funil">
        <div class="cartao-cabecalho"><h2 id="t-funil">${icone("fila")}Solicitações em andamento por etapa</h2><span class="pequeno texto-3">Situação atual · clique para filtrar</span></div>
        <div class="cartao-corpo">${funil(p.funil)}</div>
      </section>
      <div class="grade-2">
        <section class="cartao" aria-labelledby="t-valor"><div class="cartao-cabecalho"><h2 id="t-valor">${icone("moeda")}Valor contratado por mês</h2></div>
          <div class="cartao-corpo">${colunas({ categorias: meses.map((m) => m.mes.slice(0, 2) + "/" + m.mes.slice(-2)), valores: meses.map((m) => m.valor), formatar: formato.moeda, titulo: "Valor contratado por mês" })}
          ${tabelaDados(["Mês", "Valor contratado", "Pedidos"], meses.map((m) => [m.mes, formato.moeda(m.valor), m.pedidos]))}</div></section>
        <section class="cartao" aria-labelledby="t-vol"><div class="cartao-cabecalho"><h2 id="t-vol">${icone("tendencia")}Solicitações abertas e pedidos emitidos</h2></div>
          <div class="cartao-corpo">${linhas({ categorias: meses.map((m) => m.mes.slice(0, 2) + "/" + m.mes.slice(-2)), series: [{ nome: "Solicitações", valores: meses.map((m) => m.solicitacoes) }, { nome: "Pedidos", valores: meses.map((m) => m.pedidos) }], titulo: "Solicitações e pedidos por mês" })}
          ${tabelaDados(["Mês", "Solicitações", "Pedidos"], meses.map((m) => [m.mes, m.solicitacoes, m.pedidos]))}</div></section>
      </div>
      <div class="grade-2">
        ${doSetor ? "" : html`<section class="cartao" aria-labelledby="t-setor"><div class="cartao-cabecalho"><h2 id="t-setor">${icone("predio")}Valor contratado por setor</h2><span class="pequeno texto-3">${PERIODOS[dias]}</span></div>
          <div class="cartao-corpo">${barrasHorizontais(p.por_setor.slice(0, 8).map((s) => ({ rotulo: s.setor_nome, valor: s.valor, cor: s.setor_cor })), { formatar: formato.moedaCompacta })}</div></section>`}
        <section class="cartao" aria-labelledby="t-cat"><div class="cartao-cabecalho"><h2 id="t-cat">${icone("etiqueta")}Valor contratado por categoria</h2><span class="pequeno texto-3">${PERIODOS[dias]}</span></div>
          <div class="cartao-corpo">${barrasHorizontais(p.por_categoria.slice(0, 8).map((c) => ({ rotulo: c.categoria, valor: c.valor })), { formatar: formato.moedaCompacta })}</div></section>
        ${doSetor ? html`<section class="cartao" aria-labelledby="t-tempos"><div class="cartao-cabecalho"><h2 id="t-tempos">${icone("relogio")}Tempo médio de cada etapa</h2></div>
          <div class="cartao-corpo">${tempos(k)}</div></section>` : ""}
      </div>
      <div class="grade-3">
        <section class="cartao" aria-labelledby="t-prazo"><div class="cartao-cabecalho"><h2 id="t-prazo">${icone("ampulheta")}Próximos prazos de atendimento</h2></div>
          ${p.criticas.length ? html`<ul class="lista-itens">${p.criticas.map((s) => html`<li><a class="item-lista" href="/solicitacoes/${s.id}">
            <span class="corpo-item"><strong>${s.codigo} · ${s.titulo}</strong><small>${s.setor_nome} · ${rotulo("status_solicitacao", s.status)}</small></span>
            <span class="lado">${badgeSla(s.sla_situacao, s.sla_horas_restantes)}<small>${formato.horasRestantes(s.sla_horas_restantes)}</small></span></a></li>`)}</ul>`
            : vazio("Nenhum prazo em aberto", "", "", "check_circulo", true)}
        </section>
        <section class="cartao" aria-labelledby="t-forn"><div class="cartao-cabecalho"><h2 id="t-forn">${icone("fornecedor")}Principais fornecedores</h2><span class="pequeno texto-3">${PERIODOS[dias]}</span></div>
          ${p.top_fornecedores.length ? html`<ul class="lista-itens">${p.top_fornecedores.slice(0, 6).map((f, i) => html`<li><${pode("fornecedor.ver") ? "a" : "div"} class="item-lista" ${pode("fornecedor.ver") ? html`href="/fornecedores?fornecedor=${f.fornecedor_id}"` : ""}>
            <span class="icone-item">${i + 1}º</span><span class="corpo-item"><strong>${f.fornecedor}</strong><small>${f.pedidos} pedido(s)</small></span>
            <span class="lado"><strong class="num">${formato.moedaCompacta(f.valor)}</strong></span></${pode("fornecedor.ver") ? "a" : "div"}></li>`)}</ul>`
            : vazio("Sem pedidos no período", "", "", "fornecedor", true)}
        </section>
        ${doSetor ? html`<section class="cartao" aria-labelledby="t-rec"><div class="cartao-cabecalho"><h2 id="t-rec">${icone("historico")}Atualizações recentes</h2></div>
          <ul class="lista-itens">${p.recentes.map((s) => html`<li><a class="item-lista" href="/solicitacoes/${s.id}"><span class="corpo-item"><strong>${s.codigo} · ${s.titulo}</strong><small>${formato.relativo(s.atualizado_em)}</small></span><span class="lado">${badgeStatus(s.status)}</span></a></li>`)}</ul></section>`
          : html`<section class="cartao" aria-labelledby="t-tempos"><div class="cartao-cabecalho"><h2 id="t-tempos">${icone("relogio")}Tempo médio de cada etapa</h2></div>
          <div class="cartao-corpo">${tempos(k)}</div></section>`}
      </div>
    </div>`);
  ativarGraficos(raiz);

  raiz.querySelector("#periodo").addEventListener("change", (e) => navegar(`/?periodo=${e.target.value}`, { substituir: true }));
  raiz.querySelector("#btn-pdf")?.addEventListener("click", (e) => comCarregamento(e.currentTarget,
    api.baixar("/painel/relatorio.pdf", { inicio: formato.isoDias(-dias), fim: formato.hojeISO() })).catch(toastErro));
}

