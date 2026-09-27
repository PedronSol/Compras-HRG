// Detalhe da solicitação: fluxo, decisões por perfil, itens, cotação (propostas manuais e mapa comparativo),
// pedido e recebimentos, documentos, histórico e assinaturas eletrônicas.
import { api } from "../api.js";
import { estado, emitir, ouvir, rotulo } from "../estado.js";
import { atualizarConsulta, navegar } from "../roteador.js";
import { html, renderizar, on, seguro, debounce, dadosFormulario, mostrarErrosCampos } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import {
  abas, aviso, badgePedido, badgeRecebimento, badgeSetor, badgeSla, badgeStatus, badgeUrgencia, cabecalho,
  comCarregamento, confirmar, fluxo, formato, modal, opcoes, pode, toast, toastErro, vazio,
} from "../ui/componentes.js";
import { ativarUpload, zonaUpload } from "../ui/upload.js";
import { formularioFornecedor } from "./fornecedores.js";

const ICONE_DECISAO = { aprovado: ["check_circulo", "sucesso"], reprovado: ["x_circulo", "perigo"], devolvido: ["devolver", "alerta"] };

function movimentacao(h) {
  const st = (v) => rotulo(h.acao === "pedido_status" ? "status_pedido" : "status_solicitacao", v);
  switch (h.acao) {
    case "criacao": return ["Solicitação aberta e assinada", "documento", "info"];
    case "edicao": return ["Conteúdo ajustado pelo setor", "editar", ""];
    case "pedido_emitido": return ["Pedido de compra emitido", "pedido", "info"];
    case "recebimento": return [`Recebimento registrado · ${rotulo("situacao_recebimento", h.status_para)}`, "caminhao", h.status_para === "conforme" ? "sucesso" : "alerta"];
    case "pedido_status": return [`Pedido: ${st(h.status_de)} → ${st(h.status_para)}`, "pedido", ["reprovado", "cancelado"].includes(h.status_para) ? "perigo" : h.status_para === "entregue" ? "sucesso" : "info"];
    default: {
      const tom = ["reprovada", "cancelada"].includes(h.status_para) ? "perigo" : h.status_para === "devolvida" ? "alerta" : ["aprovada", "concluida", "aguardando_pedido"].includes(h.status_para) ? "sucesso" : "info";
      return [`${st(h.status_de)} → ${st(h.status_para)}`, tom === "perigo" ? "x_circulo" : tom === "alerta" ? "devolver" : "seta_direita", tom];
    }
  }
}

// ------------------------------------------------------------------ blocos
function blocoDecisao(d) {
  const s = d.solicitacao;
  const nivel = s.status === "aguardando_gestor" ? "Gestor do setor" : "Diretoria";
  return html`<section class="cartao destaque" aria-labelledby="t-decisao">
    <div class="cartao-cabecalho"><h2 id="t-decisao">${icone("carimbo")}Sua decisão · ${nivel}</h2></div>
    <form class="cartao-corpo painel-decisao" id="form-decisao" novalidate>
      <dl class="pares lista"><div><dt>Valor estimado</dt><dd class="num"><strong>${formato.moeda(s.valor_estimado)}</strong></dd></div>
        <div><dt>Alçada da Diretoria</dt><dd class="num">${formato.moeda(d.alcada_diretoria)}</dd></div></dl>
      ${s.status === "aguardando_gestor" && Number(s.valor_estimado) >= Number(d.alcada_diretoria) ? aviso("info", "Após sua aprovação, segue para a Diretoria", "O valor estimado está acima da alçada.") : ""}
      <div class="campo"><label for="parecer">Parecer <span class="texto-3">(obrigatório para devolver ou reprovar)</span></label>
        <textarea id="parecer" name="texto" maxlength="2000" placeholder="Registre sua análise. Ao devolver, indique exatamente o que deve ser ajustado."></textarea></div>
      <div class="botoes-decisao">
        <button type="button" class="botao sucesso" data-decisao="aprovar">${icone("check")}Aprovar</button>
        <button type="button" class="botao alerta" data-decisao="devolver">${icone("devolver")}Devolver</button>
        <button type="button" class="botao perigo-suave" data-decisao="reprovar">${icone("x_circulo")}Reprovar</button>
      </div>
      <p class="minusculo texto-3">Sua decisão é registrada com assinatura eletrônica (usuário, data/hora e IP).</p>
    </form></section>`;
}

function blocoDados(s) {
  return html`<section class="cartao"><div class="cartao-cabecalho"><h2>${icone("info")}Dados da solicitação</h2></div>
    <div class="cartao-corpo"><dl class="pares lista">
      <div><dt>Solicitante</dt><dd>${s.solicitante_nome}</dd></div>
      <div><dt>Setor</dt><dd>${badgeSetor(s.setor_codigo, s.setor_nome, s.setor_cor)}</dd></div>
      <div><dt>Tipo</dt><dd>${rotulo("tipo_solicitacao", s.tipo)}</dd></div>
      <div><dt>Urgência</dt><dd>${badgeUrgencia(s.urgencia)}</dd></div>
      <div><dt>Aberta em</dt><dd>${formato.dataHora(s.criado_em)}</dd></div>
      <div><dt>Necessário até</dt><dd>${formato.data(s.data_necessidade)}</dd></div>
      <div><dt>Local de entrega</dt><dd>${s.local_entrega || "—"}</dd></div>
      <div><dt>Prazo de atendimento</dt><dd>${badgeSla(s.sla_situacao, s.sla_horas_restantes)}<br><small class="texto-3">${formato.dataHora(s.sla_prazo_limite)}</small></dd></div>
      <div><dt>Comprador</dt><dd>${s.comprador_nome || "—"}</dd></div>
      <div><dt>Valor estimado</dt><dd class="num">${formato.moeda(s.valor_estimado)}</dd></div>
      <div><dt>Valor contratado</dt><dd class="num"><strong>${formato.moeda(s.valor_final)}</strong>${s.valor_final && s.valor_estimado ? html`<br><small class="${Number(s.valor_final) <= Number(s.valor_estimado) ? "texto-3" : "texto-3"}">${Number(s.valor_final) <= Number(s.valor_estimado) ? `economia de ${formato.moeda(s.valor_estimado - s.valor_final)}` : `${formato.moeda(s.valor_final - s.valor_estimado)} acima do estimado`}</small>` : ""}</dd></div>
      <div><dt>Rodada</dt><dd>${s.rodada}ª</dd></div>
    </dl></div></section>`;
}

function blocoAprovacoes(d) {
  return html`<section class="cartao"><div class="cartao-cabecalho"><h2>${icone("carimbo")}Aprovações</h2></div>
    ${d.aprovacoes.length ? html`<ul class="lista-itens">${d.aprovacoes.map((a) => { const [ic, tom] = ICONE_DECISAO[a.decisao]; return html`<li><div class="item-lista">
      <span class="icone-item ${tom}">${icone(ic)}</span><span class="corpo-item"><strong>${rotulo("nivel_aprovacao", a.nivel)} · ${rotulo("decisao_aprovacao", a.decisao)}</strong>
      <small>${a.usuario_nome} · ${formato.dataHora(a.criado_em)}</small>${a.parecer ? html`<small title="${a.parecer}">“${a.parecer}”</small>` : ""}</span></div></li>`; })}</ul>`
      : vazio("Nenhuma decisão registrada", d.solicitacao.status === "aguardando_gestor" ? "Aguardando o gestor do setor." : d.solicitacao.status === "aguardando_diretoria" ? "Aguardando a Diretoria." : "", "", "carimbo", true)}
  </section>`;
}

function tabelaItens(d) {
  return html`<div class="tabela-envoltorio"><table class="tabela responsiva">
    <thead><tr><th>#</th><th>Item</th><th class="num">Quantidade</th><th class="num">Unitário estimado</th><th class="num">Total estimado</th></tr></thead>
    <tbody>${d.itens.map((i, n) => html`<tr><td data-rotulo="Item" class="texto-3">${n + 1}</td>
      <td class="principal-td"><div class="principal-celula"><strong>${i.descricao}</strong><small>${i.material_codigo ? html`<span class="mono">${i.material_codigo}</span> · catálogo` : "Item livre"}${i.observacao ? ` · ${i.observacao}` : ""}</small></div></td>
      <td data-rotulo="Quantidade" class="num">${formato.numero(i.quantidade)} ${i.unidade}</td>
      <td data-rotulo="Unitário" class="num">${formato.moeda(i.valor_unitario_estimado)}</td>
      <td data-rotulo="Total" class="num"><strong>${formato.moeda(i.total_estimado)}</strong></td></tr>`)}</tbody>
    <tfoot><tr><td colspan="4">Total estimado</td><td class="num">${formato.moeda(d.solicitacao.valor_estimado)}</td></tr></tfoot></table></div>`;
}

function mapaComparativo(d) {
  const { cotacoes: cot, comparacao: comp, itens } = d;
  const s = d.solicitacao;
  const podeEditar = d.acoes.includes("propostas");
  const podeEscolher = d.acoes.includes("definir_fornecedor");
  const ordem = comp.ranking.map((id) => cot.find((c) => c.id === id)).filter(Boolean);
  const menorTotal = comp.menor_total !== null ? Number(comp.menor_total) : null;
  const marcaMenor = html`<span class="marca-menor" title="Menor valor">${icone("check")}<span class="sr-only">Menor valor:</span></span>`;
  const menorItem = (p, l) => Number(p.valor_unitario) === Number(l.menor_unitario) && Object.keys(l.precos).length > 1;
  const menorGlobal = (c) => ordem.length > 1 && menorTotal !== null && Number(c.valor_total) === menorTotal && c.itens.length >= itens.length;
  const anexo = (id) => d.anexos.find((a) => a.id === id);
  return html`<div class="tabela-envoltorio"><table class="comparacao">
    <thead><tr><th scope="col">Item</th>${ordem.map((c, i) => html`<th scope="col" class="${c.selecionada ? "vencedora" : ""}"><div class="forn-cab">
      ${c.selecionada ? html`<span class="badge sucesso">${icone("estrela")}Vencedora</span>` : i === 0 && menorTotal !== null && Number(c.valor_total) === menorTotal ? html`<span class="badge primaria">Menor preço</span>` : ""}
      <strong>${c.nome_fantasia || c.razao_social}</strong><small class="mono">${formato.cnpj(c.cnpj)}</small>
      ${c.numero_proposta ? html`<small>Proposta ${c.numero_proposta}</small>` : ""}</div></th>`)}</tr></thead>
    <tbody>${comp.linhas.map((l) => html`<tr><td><strong>${l.descricao}</strong><span class="sub-cell">${formato.numero(l.quantidade)} ${l.unidade} · estimado ${formato.moeda(l.estimado)}</span></td>
      ${ordem.map((c) => { const p = l.precos[c.id]; return p
        ? html`<td class="${menorItem(p, l) ? "menor" : ""} ${c.selecionada ? "vencedora" : ""}">${menorItem(p, l) ? marcaMenor : ""}${formato.moeda(p.valor_unitario)}<span class="sub-cell">${formato.moeda(p.total)}${p.marca ? ` · ${p.marca}` : ""}</span></td>`
        : html`<td class="ausente ${c.selecionada ? "vencedora" : ""}">não cotado</td>`; })}</tr>`)}</tbody>
    <tfoot>
      <tr><td>Frete</td>${ordem.map((c) => html`<td class="${c.selecionada ? "vencedora" : ""}">${formato.moeda(c.frete)}</td>`)}</tr>
      <tr><td>Desconto</td>${ordem.map((c) => html`<td class="${c.selecionada ? "vencedora" : ""}">${Number(c.desconto) ? `− ${formato.moeda(c.desconto)}` : "—"}</td>`)}</tr>
      <tr class="total"><td>Valor total</td>${ordem.map((c) => html`<td class="${menorGlobal(c) ? "menor" : ""} ${c.selecionada ? "vencedora" : ""}">${menorGlobal(c) ? marcaMenor : ""}${formato.moeda(c.valor_total)}</td>`)}</tr>
      <tr><td>Prazo de entrega</td>${ordem.map((c) => html`<td class="${c.selecionada ? "vencedora" : ""}">${c.prazo_entrega_dias} dias${Number(c.prazo_entrega_dias) === Number(comp.melhor_prazo) && ordem.length > 1 ? html`<span class="sub-cell">melhor prazo</span>` : ""}</td>`)}</tr>
      <tr><td>Pagamento</td>${ordem.map((c) => html`<td class="${c.selecionada ? "vencedora" : ""}">${c.condicoes_pagamento || "—"}</td>`)}</tr>
      <tr><td>Validade</td>${ordem.map((c) => html`<td class="${c.selecionada ? "vencedora" : ""}">${formato.data(c.validade_proposta)}</td>`)}</tr>
      <tr><td>Documento</td>${ordem.map((c) => { const a = anexo(c.anexo_id); return html`<td class="${c.selecionada ? "vencedora" : ""}">${a ? html`<button class="botao fantasma pequeno" data-ver-anexo="${a.id}">${icone("olho")}Ver</button>` : html`<span class="texto-3">—</span>`}</td>`; })}</tr>
      ${podeEditar || podeEscolher ? html`<tr><td></td>${ordem.map((c) => html`<td class="${c.selecionada ? "vencedora" : ""}"><div class="grupo-botoes">
        ${podeEscolher ? html`<button class="botao sucesso pequeno" data-escolher="${c.id}" ${c.itens.length < itens.length ? seguro('disabled title="Proposta não cota todos os itens"') : ""}>${icone("estrela")}Escolher</button>` : ""}
        ${podeEditar ? html`<button class="botao fantasma pequeno icone" data-editar-proposta="${c.id}" aria-label="Editar proposta">${icone("editar")}</button>
          <button class="botao fantasma pequeno icone" data-remover-proposta="${c.id}" aria-label="Remover proposta">${icone("lixeira")}</button>` : ""}</div></td>`)}</tr>` : ""}
    </tfoot></table></div>
    ${s.justificativa_escolha ? html`<div class="cartao-corpo">${aviso("info", "Justificativa da escolha do fornecedor", s.justificativa_escolha)}</div>` : ""}`;
}

function abaCotacao(d) {
  const s = d.solicitacao;
  const comp = d.comparacao;
  if (["aguardando_gestor", "aguardando_diretoria", "devolvida", "reprovada"].includes(s.status) || (s.status === "cancelada" && !s.cotacao_iniciada_em)) {
    return html`<section class="cartao">${vazio("Cotação ainda não disponível", "A cotação começa depois que a solicitação é aprovada.", "", "balanca")}</section>`;
  }
  if (s.status === "aprovada") {
    return html`<section class="cartao">${vazio("Aguardando o comprador iniciar a cotação", "Assim que iniciada, as propostas dos fornecedores aparecerão aqui para comparação.",
      d.acoes.includes("iniciar_cotacao") ? html`<button class="botao" data-acao="iniciar_cotacao">${icone("play")}Iniciar cotação</button>` : "", "balanca")}</section>`;
  }
  return html`<section class="cartao">
    <div class="cartao-cabecalho"><h2>${icone("balanca")}Mapa comparativo de propostas</h2>
      <span class="badge ${comp.abaixo_do_minimo ? "alerta" : "sucesso"}">${d.cotacoes.length} de ${comp.minimo_cotacoes} propostas mínimas</span>
      ${d.acoes.includes("propostas") ? html`<button class="botao" data-nova-proposta>${icone("mais")}Registrar proposta</button>` : ""}</div>
    ${d.cotacoes.length ? mapaComparativo(d) : vazio("Nenhuma proposta registrada", d.acoes.includes("propostas") ? "Anexe ou fotografe o orçamento recebido e digite os valores de cada item." : "O comprador ainda não registrou propostas.",
      d.acoes.includes("propostas") ? html`<button class="botao" data-nova-proposta>${icone("mais")}Registrar primeira proposta</button>` : "", "balanca")}
    ${d.acoes.includes("propostas") ? html`<div class="cartao-corpo"><p class="nota-privacidade">${icone("escudo")}<span>Os valores são digitados pelo comprador a partir do orçamento anexado. O sistema não lê nem interpreta documentos automaticamente.</span></p></div>` : ""}
  </section>`;
}

function abaPedido(d) {
  if (!d.pedidos.length) return html`<section class="cartao">${vazio("Nenhum pedido de compra emitido", d.acoes.includes("emitir_pedido") ? "O fornecedor já foi definido. Emita o pedido para seguir à aprovação financeira." : "O pedido é emitido pelo comprador após a definição do fornecedor.",
    d.acoes.includes("emitir_pedido") ? html`<button class="botao" data-acao="emitir_pedido">${icone("pedido")}Emitir pedido de compra</button>` : "", "pedido")}</section>`;
  return html`<div class="pilha">${d.pedidos.map((p) => html`<section class="cartao">
    <div class="cartao-cabecalho"><h2>${icone("pedido")}${p.codigo}</h2>${badgePedido(p.status, true)}${p.atrasado ? html`<span class="badge perigo">${icone("alerta")}Atrasado ${p.dias_atraso} dia(s)</span>` : ""}
      <a class="botao secundario pequeno" href="/pedidos/${p.id}">Abrir pedido${icone("seta_dir")}</a></div>
    <div class="cartao-corpo"><dl class="pares">
      <div><dt>Fornecedor</dt><dd>${p.fornecedor_fantasia || p.fornecedor_nome}</dd></div>
      <div><dt>Valor total</dt><dd class="num"><strong>${formato.moeda(p.valor_total)}</strong></dd></div>
      <div><dt>Emissão</dt><dd>${formato.dataHora(p.criado_em)}</dd></div>
      <div><dt>Previsão de entrega</dt><dd>${formato.data(p.data_prevista_entrega)}</dd></div>
      <div><dt>Recebido</dt><dd><div class="progresso-rotulado"><div class="progresso sucesso"><span data-largura="${p.percentual_recebido}"></span></div>${p.percentual_recebido}%</div></dd></div>
    </dl></div></section>`)}
    ${d.recebimentos.length ? html`<section class="cartao"><div class="cartao-cabecalho"><h2>${icone("caminhao")}Recebimentos</h2></div>
      <div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Recebimento</th><th>Nota fiscal</th><th>Conferente</th><th>Situação</th><th>Data</th></tr></thead>
      <tbody>${d.recebimentos.map((r) => html`<tr><td class="principal-td"><div class="principal-celula"><strong>${r.codigo}</strong><small>${r.pedido_codigo}</small></div></td>
        <td data-rotulo="Nota fiscal">NF ${r.nota_fiscal}${r.valor_nf ? html`<br><small class="texto-3">${formato.moeda(r.valor_nf)}</small>` : ""}</td><td data-rotulo="Conferente">${r.recebido_por_nome}</td>
        <td data-rotulo="Situação">${badgeRecebimento(r.situacao)}${r.observacoes ? html`<br><small class="texto-3">${r.observacoes}</small>` : ""}</td><td data-rotulo="Data" class="nowrap">${formato.dataHora(r.recebido_em)}</td></tr>`)}</tbody></table></div></section>` : ""}
  </div>`;
}

function abaDocumentos(d) {
  const ativos = d.anexos.filter((a) => !a.removido_em);
  const removidos = d.anexos.filter((a) => a.removido_em);
  const origem = { solicitante: "Setor solicitante", comprador: "Compras", recebimento: "Recebimento" };
  const podeAnexar = d.acoes.includes("anexar");
  return html`<section class="cartao"><div class="cartao-cabecalho"><h2>${icone("anexo")}Documentos</h2><span class="pequeno texto-3">Armazenados cifrados · integridade por SHA-256</span></div>
    <div class="cartao-corpo pilha">
      ${ativos.length ? html`<ul class="lista-arquivos">${ativos.map((a) => html`<li class="arquivo">
        <span class="icone-arquivo">${icone(a.mime === "application/pdf" ? "pdf" : a.mime.startsWith("image/") ? "camera" : "documento")}</span>
        <span class="info-arquivo"><span class="nome">${a.nome_original}</span><span class="meta">${rotulo("tipo_documento", a.tipo_documento)} · ${origem[a.origem]} · ${a.enviado_por_nome} · ${formato.dataHora(a.criado_em)} · ${formato.tamanho(a.tamanho)}</span></span>
        <span class="acoes">${["application/pdf", "image/png", "image/jpeg", "image/webp"].includes(a.mime) ? html`<button class="botao fantasma pequeno icone" data-ver-anexo="${a.id}" aria-label="Visualizar ${a.nome_original}">${icone("olho")}</button>` : ""}
          <button class="botao fantasma pequeno icone" data-baixar-anexo="${a.id}" aria-label="Baixar ${a.nome_original}">${icone("download")}</button>
          ${podeAnexar && a.origem !== "recebimento" && (a.origem === "solicitante" ? ["solicitante", "gestor"].includes(estado.usuario.papel) : estado.usuario.papel === "comprador") ? html`<button class="botao fantasma pequeno icone" data-remover-anexo="${a.id}" aria-label="Remover ${a.nome_original}">${icone("lixeira")}</button>` : ""}</span></li>`)}</ul>`
        : vazio("Nenhum documento anexado", "", "", "anexo", true)}
      ${removidos.length ? html`<details><summary class="pequeno texto-3">${removidos.length} documento(s) removido(s) — mantidos para auditoria</summary><ul class="lista-arquivos">${removidos.map((a) => html`<li class="arquivo removido"><span class="icone-arquivo">${icone("documento")}</span><span class="info-arquivo"><span class="nome">${a.nome_original}</span><span class="meta">removido em ${formato.dataHora(a.removido_em)}</span></span></li>`)}</ul></details>` : ""}
      ${podeAnexar ? html`<form id="form-anexo" class="pilha" novalidate>${zonaUpload({ id: "novos-anexos", max: 5, rotulo: "Anexar ou fotografar documentos" })}
        <div class="linha-flex"><select class="entrada" name="tipo_documento" aria-label="Tipo de documento">${opcoes(estado.usuario.papel === "comprador" ? { proposta: "Proposta comercial", orcamento: "Orçamento", laudo: "Laudo / certificado", foto: "Fotografia", outro: "Outro" } : { orcamento: "Orçamento", laudo: "Laudo / certificado", foto: "Fotografia", outro: "Outro" }, "")}</select>
        <button class="botao" type="submit">${icone("upload")}Enviar documentos</button></div></form>` : ""}
    </div></section>`;
}

function abaHistorico(d) {
  return html`<div class="grade-2">
    <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("historico")}Histórico de movimentações</h2></div>
      <div class="cartao-corpo"><ol class="linha-tempo">${[...d.historico].reverse().map((h) => { const [t, ic, tom] = movimentacao(h); return html`<li>
        <span class="icone-t ${tom}">${icone(ic)}</span><div><div class="t-titulo">${t}</div>
        <div class="t-meta">${h.autor_nome || "Sistema"}${h.autor_papel ? ` · ${rotulo("papel", h.autor_papel)}` : ""} · ${formato.dataHora(h.criado_em)}</div>
        ${h.observacao ? html`<div class="t-obs">${h.observacao}</div>` : ""}</div></li>`; })}</ol></div></section>
    <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("assinatura")}Assinaturas eletrônicas</h2><span class="subtitulo">HMAC-SHA-256 sobre usuário, data/hora, IP, ação e conteúdo</span></div>
      ${d.assinaturas.length ? html`<div>${d.assinaturas.map((a) => html`<div class="assinatura">
        <span class="selo-ass">${icone("assinatura")}</span>
        <div><strong class="pequeno">${rotulo("acao_assinatura", a.acao)}</strong><div class="minusculo texto-3">${a.usuario_nome} · ${rotulo("papel", a.papel)} · ${formato.dataHora(a.assinado_em)} · IP ${a.ip}</div>
          <div class="mono-hash">${a.hash_autenticidade}</div></div>
        <button class="botao secundario pequeno" data-verificar="${a.id}">${icone("escudo")}Verificar</button></div>`)}</div>`
        : vazio("Nenhuma assinatura", "", "", "assinatura", true)}</section>
  </div>`;
}

// ------------------------------------------------------------------ modais de ação
async function modalProposta(d, cotacao = null, aoSalvar) {
  const fornecedores = (await api.get("/fornecedores", { ativos: 1, por_pagina: 500, ordem: "nome" })).itens;
  const usados = new Set(d.cotacoes.map((c) => c.fornecedor_id));
  const docs = d.anexos.filter((a) => !a.removido_em);
  const precoDe = (itemId) => cotacao?.itens.find((i) => String(i.solicitacao_item_id) === String(itemId));
  const m = modal({
    titulo: cotacao ? `Editar proposta · ${cotacao.nome_fantasia || cotacao.razao_social}` : "Registrar proposta de fornecedor",
    sub: "Digite os dados exatamente como constam no orçamento recebido.", tamanho: "extra",
    conteudo: html`<form id="form-prop" class="pilha" novalidate>
      <div class="form-grade">
        ${cotacao ? "" : html`<div class="campo col-8" data-campo="fornecedor_id"><label for="p-forn">Fornecedor<span class="obrigatorio">*</span></label>
          <div class="linha-flex"><select id="p-forn" name="fornecedor_id" class="entrada" required>${opcoes(Object.fromEntries(fornecedores.filter((f) => !usados.has(f.id)).map((f) => [f.id, `${f.nome_fantasia || f.razao_social} · ${formato.cnpj(f.cnpj)}`])), "", { vazio: "Selecione o fornecedor…" })}</select>
          ${pode("fornecedor.gerenciar") ? html`<button type="button" class="botao secundario" data-novo-forn>${icone("mais")}Novo</button>` : ""}</div></div>`}
        <div class="campo ${cotacao ? "col-4" : "col-4"}"><label for="p-num">Nº da proposta</label><input id="p-num" name="numero_proposta" maxlength="60" value="${cotacao?.numero_proposta || ""}"></div>
        <div class="campo col-3"><label for="p-data">Data da proposta</label><input id="p-data" name="data_proposta" type="date" value="${cotacao?.data_proposta || formato.hojeISO()}"></div>
        <div class="campo col-3"><label for="p-val">Válida até</label><input id="p-val" name="validade_proposta" type="date" value="${cotacao?.validade_proposta || formato.isoDias(15)}"></div>
        <div class="campo col-3"><label for="p-prazo">Prazo de entrega (dias)<span class="obrigatorio">*</span></label><input id="p-prazo" name="prazo_entrega_dias" type="number" min="0" max="3650" required value="${cotacao?.prazo_entrega_dias ?? ""}"></div>
        <div class="campo col-3"><label for="p-pag">Condições de pagamento</label><input id="p-pag" name="condicoes_pagamento" maxlength="300" list="lista-pag" value="${cotacao?.condicoes_pagamento || ""}"><datalist id="lista-pag"><option value="28 dias"><option value="30 dias"><option value="30/60 dias"><option value="30/60/90 dias"><option value="À vista"></datalist></div>
        <div class="campo col-3"><label for="p-frete">Frete</label><div class="entrada-prefixo"><span>R$</span><input id="p-frete" name="frete" inputmode="decimal" value="${formato.entradaDecimal(cotacao?.frete || 0)}"></div></div>
        <div class="campo col-3"><label for="p-desc">Desconto</label><div class="entrada-prefixo"><span>R$</span><input id="p-desc" name="desconto" inputmode="decimal" value="${formato.entradaDecimal(cotacao?.desconto || 0)}"></div></div>
        <div class="campo col-6"><label for="p-doc">Documento da proposta</label><select id="p-doc" name="anexo_id">${opcoes(Object.fromEntries(docs.map((a) => [a.id, `${a.nome_original} (${rotulo("tipo_documento", a.tipo_documento)})`])), cotacao?.anexo_id || "", { vazio: "Nenhum" })}</select>
          <p class="ajuda">Anexe ou fotografe o orçamento abaixo, ou selecione um já anexado.</p></div>
        <div class="campo col-6"><span class="rotulo">Anexar orçamento agora</span><div class="linha-flex">
          <label class="botao secundario pequeno">${icone("upload")}Selecionar arquivo<input type="file" class="sr-only" data-doc-prop accept=".pdf,.png,.jpg,.jpeg,.webp"></label>
          <label class="botao secundario pequeno">${icone("camera")}Fotografar<input type="file" class="sr-only" data-doc-prop accept="image/*" capture="environment"></label></div></div>
      </div>
      <div data-campo="itens"><p class="grupo-titulo-secao">Preços por item</p>
        <div class="tabela-envoltorio"><table class="tabela densa responsiva"><thead><tr><th>Item solicitado</th><th class="num">Qtd. solicitada</th><th>Qtd. cotada</th><th>Valor unitário</th><th>Marca / modelo</th><th class="num">Total</th><th>Não cotado</th></tr></thead>
        <tbody>${d.itens.map((i) => { const p = precoDe(i.id); const ausente = cotacao && !p; return html`<tr data-item="${i.id}">
          <td class="principal-td"><div class="principal-celula"><strong>${i.descricao}</strong><small>Estimado ${formato.moeda(i.valor_unitario_estimado)} / ${i.unidade}</small></div></td>
          <td data-rotulo="Solicitado" class="num">${formato.numero(i.quantidade)} ${i.unidade}</td>
          <td data-rotulo="Qtd. cotada"><input class="entrada num" name="qtd" inputmode="decimal" aria-label="Quantidade cotada" value="${formato.numero(p?.quantidade ?? i.quantidade)}" ${ausente ? seguro("disabled") : ""}></td>
          <td data-rotulo="Unitário"><div class="entrada-prefixo"><span>R$</span><input class="entrada num" name="unit" inputmode="decimal" aria-label="Valor unitário" placeholder="0,00" value="${p ? formato.entradaDecimal(p.valor_unitario) : ""}" ${ausente ? seguro("disabled") : ""}></div></td>
          <td data-rotulo="Marca"><input class="entrada" name="marca" maxlength="120" aria-label="Marca" value="${p?.marca || ""}" ${ausente ? seguro("disabled") : ""}></td>
          <td data-rotulo="Total" class="num" data-total>—</td>
          <td data-rotulo="Não cotado"><input type="checkbox" name="ausente" aria-label="Item não cotado" ${ausente ? seguro("checked") : ""}></td></tr>`; })}</tbody></table></div>
        <div class="resumo-total"><span class="texto-3">Total da proposta (itens + frete − desconto)</span><span class="valor-total" data-total-prop>R$ 0,00</span></div>
      </div>
      <div class="campo"><label for="p-obs">Observações</label><textarea id="p-obs" name="observacoes" maxlength="2000">${cotacao?.observacoes || ""}</textarea></div>
    </form>`,
    rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="form-prop">${icone("check")}Salvar proposta</button>`,
  });
  const form = m.el.querySelector("#form-prop");
  const recalcular = () => {
    let total = 0;
    form.querySelectorAll("tr[data-item]").forEach((tr) => {
      const aus = tr.querySelector('[name="ausente"]').checked;
      tr.querySelectorAll('input:not([type="checkbox"])').forEach((x) => { x.disabled = aus; });
      const t = aus ? 0 : formato.lerDecimal(tr.querySelector('[name="qtd"]').value) * formato.lerDecimal(tr.querySelector('[name="unit"]').value);
      tr.querySelector("[data-total]").textContent = t ? formato.moeda(t) : "—";
      total += t;
    });
    total += formato.lerDecimal(form.frete.value) - formato.lerDecimal(form.desconto.value);
    m.el.querySelector("[data-total-prop]").textContent = formato.moeda(Math.max(0, total));
  };
  form.addEventListener("input", recalcular);
  form.addEventListener("change", recalcular);
  recalcular();
  m.el.querySelector("[data-novo-forn]")?.addEventListener("click", async () => {
    const f = await formularioFornecedor();
    if (!f) return;
    const sel = form.fornecedor_id;
    sel.insertAdjacentHTML("beforeend", html`<option value="${f.id}">${f.nome_fantasia || f.razao_social} · ${formato.cnpj(f.cnpj)}</option>`.toString());
    sel.value = f.id;
  });
  form.querySelectorAll("[data-doc-prop]").forEach((input) => input.addEventListener("change", async () => {
    const arq = input.files[0];
    if (!arq) return;
    const fd = new FormData();
    fd.append("tipo_documento", "proposta");
    fd.append("arquivos", arq, arq.type.startsWith("image/") && input.hasAttribute("capture") ? `foto-proposta-${Date.now()}.jpg` : arq.name);
    try {
      const r = await api.enviarFormulario(`/solicitacoes/${d.solicitacao.id}/anexos`, fd);
      const novo = r.anexos.find((a) => a.id === r.anexos_criados[0]);
      form.anexo_id.insertAdjacentHTML("beforeend", html`<option value="${novo.id}">${novo.nome_original} (Proposta comercial)</option>`.toString());
      form.anexo_id.value = novo.id;
      toast("sucesso", "Documento anexado", "Agora digite os valores da proposta.");
      aoSalvar?.(r, false);
    } catch (e) { toastErro(e); }
    input.value = "";
  }));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const dados = dadosFormulario(form);
    const itens = [...form.querySelectorAll("tr[data-item]")].filter((tr) => !tr.querySelector('[name="ausente"]').checked).map((tr) => ({
      solicitacao_item_id: tr.dataset.item,
      quantidade: String(formato.lerDecimal(tr.querySelector('[name="qtd"]').value)),
      valor_unitario: String(formato.lerDecimal(tr.querySelector('[name="unit"]').value)),
      marca: tr.querySelector('[name="marca"]').value.trim() || undefined,
      _vazio: !tr.querySelector('[name="unit"]').value.trim(),
    }));
    const erros = {};
    if (!cotacao && !dados.fornecedor_id) erros.fornecedor_id = "Selecione o fornecedor";
    if (dados.prazo_entrega_dias === "") erros.prazo_entrega_dias = "Informe o prazo";
    if (!itens.length) erros.itens = "Informe o preço de ao menos um item";
    else if (itens.some((i) => i._vazio)) erros.itens = "Preencha o valor unitário de todos os itens cotados (ou marque “não cotado”)";
    mostrarErrosCampos(form, erros);
    if (Object.keys(erros).length) return;
    const corpo = { ...dados, itens: itens.map(({ _vazio, ...i }) => i) };
    delete corpo.qtd; delete corpo.unit; delete corpo.marca; delete corpo.ausente;
    try {
      const r = await comCarregamento(m.el.querySelector('[type="submit"]'), cotacao ? api.put(`/propostas/${cotacao.id}`, corpo) : api.post(`/solicitacoes/${d.solicitacao.id}/propostas`, corpo));
      toast("sucesso", cotacao ? "Proposta atualizada" : "Proposta registrada", "O mapa comparativo foi atualizado.");
      m.fechar();
      aoSalvar?.(r, true);
    } catch (erro) { mostrarErrosCampos(form, erro.campos); toastErro(erro); }
  });
}

function visualizarAnexo(id, nome = "Documento") {
  api.baixar(`/anexos/${id}/arquivo`, { inline: 1 }, { abrir: true, nomePadrao: nome }).catch(toastErro);
}

// ------------------------------------------------------------------ montagem
export async function montar({ raiz, params, consulta }) {
  let d = await api.get(`/solicitacoes/${params.id}`);
  let aba = consulta.aba || "resumo";

  function renderizarTudo() {
    const s = d.solicitacao;
    const a = d.acoes;
    const decisao = a.includes("aprovar");
    const acoes = html`
      ${a.includes("reenviar") ? html`<a class="botao" href="/solicitacoes/${s.id}/ajustar">${icone("editar")}Ajustar e reenviar</a>` : ""}
      ${a.includes("iniciar_cotacao") ? html`<button class="botao" data-acao="iniciar_cotacao">${icone("play")}Iniciar cotação</button>` : ""}
      ${a.includes("emitir_pedido") ? html`<button class="botao" data-acao="emitir_pedido">${icone("pedido")}Emitir pedido de compra</button>` : ""}
      ${a.includes("reabrir_cotacao") ? html`<button class="botao secundario" data-acao="reabrir_cotacao">${icone("devolver")}Reabrir cotação</button>` : ""}
      ${a.includes("cancelar") ? html`<button class="botao perigo-suave" data-acao="cancelar">${icone("x_circulo")}Cancelar</button>` : ""}
      <button class="botao secundario" data-dossie>${icone("pdf")}Dossiê PDF</button>`;
    const avisos = [];
    if (s.status === "devolvida" && s.motivo_devolucao) avisos.push(aviso("alerta", "Devolvida para ajustes", s.motivo_devolucao, a.includes("reenviar") ? html`<a class="botao pequeno" href="/solicitacoes/${s.id}/ajustar">Ajustar agora</a>` : ""));
    if (s.status === "reprovada") avisos.push(aviso("perigo", "Solicitação reprovada", s.motivo_reprovacao));
    if (s.status === "cancelada") avisos.push(aviso("perigo", "Solicitação cancelada", s.motivo_cancelamento));
    if (s.status === "concluida") avisos.push(aviso("sucesso", "Processo concluído", `Itens recebidos e conferidos em ${formato.dataHora(s.finalizado_em)}.`));
    if (s.sla_situacao === "estourado") avisos.push(aviso("perigo", "Prazo de atendimento estourado", `O prazo venceu em ${formato.dataHora(s.sla_prazo_limite)}.`));

    renderizar(raiz, html`
      ${cabecalho({
        titulo: s.titulo, extra: badgeStatus(s.status, true),
        sub: html`<span class="mono">${s.codigo}</span> · ${s.setor_nome} · aberta por ${s.solicitante_nome} ${formato.relativo(s.criado_em)}${s.aberta_por_gestor ? " · aberta pelo gestor" : ""}`,
        migalhas: [{ rotulo: "Solicitações", href: "/solicitacoes" }, { rotulo: s.codigo }], acoes,
      })}
      <div class="pilha">
        <section class="cartao">${fluxo(s)}</section>
        ${avisos.length ? html`<div class="pilha-sm">${avisos}</div>` : ""}
        <section class="cartao">${abas([
          { valor: "resumo", rotulo: "Resumo", icone: "info" },
          { valor: "cotacao", rotulo: "Cotação", icone: "balanca", qtd: d.cotacoes.length || null },
          { valor: "pedido", rotulo: "Pedido e recebimento", icone: "pedido", qtd: d.pedidos.length || null },
          { valor: "documentos", rotulo: "Documentos", icone: "anexo", qtd: d.anexos.filter((x) => !x.removido_em).length || null },
          { valor: "historico", rotulo: "Histórico e assinaturas", icone: "historico" },
        ], aba, { nome: "aba" })}</section>
        <div id="conteudo-aba">${aba === "cotacao" ? abaCotacao(d) : aba === "pedido" ? abaPedido(d) : aba === "documentos" ? abaDocumentos(d) : aba === "historico" ? abaHistorico(d)
          : html`<div class="grade-principal">
            <div class="pilha">
              <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("caixa")}Itens solicitados</h2><span class="badge">${d.itens.length} ${d.itens.length === 1 ? "item" : "itens"}</span></div>${tabelaItens(d)}</section>
              <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("editar")}Justificativa</h2></div>
                <div class="cartao-corpo pilha"><p class="texto-longo">${s.justificativa}</p>
                ${s.descricao ? html`<div><p class="grupo-titulo-secao">Especificações e observações</p><p class="texto-longo">${s.descricao}</p></div>` : ""}</div></section>
            </div>
            <aside>${decisao ? blocoDecisao(d) : ""}${blocoDados(s)}${blocoAprovacoes(d)}</aside>
          </div>`}</div>
      </div>`);
    if (aba === "documentos" && a.includes("anexar")) ativarFormAnexo();
  }

  function atualizar(novo) { d = novo; renderizarTudo(); }
  async function recarregar() { atualizar(await api.get(`/solicitacoes/${params.id}`)); }

  function ativarFormAnexo() {
    const form = raiz.querySelector("#form-anexo");
    if (!form) return;
    const up = ativarUpload(form, { id: "novos-anexos", max: 5 });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!up.arquivos().length) { toast("alerta", "Selecione ao menos um arquivo"); return; }
      const fd = new FormData();
      fd.append("tipo_documento", form.tipo_documento.value);
      up.arquivos().forEach((f) => fd.append("arquivos", f, f.name));
      try {
        atualizar(await comCarregamento(form.querySelector('[type="submit"]'), api.enviarFormulario(`/solicitacoes/${params.id}/anexos`, fd)));
        toast("sucesso", "Documentos anexados");
      } catch (erro) { toastErro(erro); }
    });
  }

  async function executar(acao, corpo = {}, botao = null, mensagem = "") {
    try {
      const r = await comCarregamento(botao, api.post(`/solicitacoes/${params.id}/acoes/${acao}`, { versao: d.solicitacao.versao, ...corpo }));
      atualizar(r);
      if (mensagem) toast("sucesso", mensagem, `${r.solicitacao.codigo} · ${rotulo("status_solicitacao", r.solicitacao.status)}`);
      return r;
    } catch (erro) {
      toastErro(erro);
      if (erro.status === 409) recarregar();
      return null;
    }
  }

  on(raiz, "click", "[data-aba]", (e, b) => { aba = b.dataset.aba; atualizarConsulta({ aba: aba === "resumo" ? "" : aba }); renderizarTudo(); });
  on(raiz, "click", "[data-decisao]", async (e, b) => {
    const texto = raiz.querySelector("#parecer")?.value.trim() || "";
    const decisao = b.dataset.decisao;
    if (decisao !== "aprovar" && texto.length < 10) {
      mostrarErrosCampos(raiz.querySelector("#form-decisao"), { texto: "Informe o parecer (mínimo 10 caracteres)" });
      return;
    }
    const nomes = { aprovar: "Solicitação aprovada", devolver: "Solicitação devolvida ao setor", reprovar: "Solicitação reprovada" };
    await executar(decisao, { texto }, b, nomes[decisao]);
    emitir("atualizar-contadores");
  });
  on(raiz, "click", "[data-acao]", async (e, b) => {
    const acao = b.dataset.acao;
    const s = d.solicitacao;
    if (acao === "iniciar_cotacao") {
      if (await executar("iniciar_cotacao", {}, b, "Cotação iniciada")) { aba = "cotacao"; atualizarConsulta({ aba }); renderizarTudo(); }
    } else if (acao === "cancelar") {
      const r = await confirmar({ titulo: `Cancelar ${s.codigo}?`, mensagem: "O cancelamento encerra a solicitação definitivamente.", justificativa: "Motivo do cancelamento", minimo: 10, rotuloConfirmar: "Cancelar solicitação", tom: "perigo" });
      if (r.confirmado) await executar("cancelar", { texto: r.texto }, null, "Solicitação cancelada");
    } else if (acao === "reabrir_cotacao") {
      const r = await confirmar({ titulo: "Reabrir a cotação?", mensagem: "A escolha do fornecedor será desfeita e novas propostas poderão ser registradas.", justificativa: "Motivo", minimo: 10, rotuloConfirmar: "Reabrir cotação" });
      if (r.confirmado) await executar("reabrir_cotacao", { texto: r.texto }, null, "Cotação reaberta");
    } else if (acao === "emitir_pedido") {
      const v = d.cotacoes.find((c) => c.selecionada);
      const r = await confirmar({
        titulo: "Emitir pedido de compra", rotuloConfirmar: "Assinar e emitir pedido", icone: "assinatura",
        mensagem: "Os itens e valores são copiados da proposta vencedora e não podem ser alterados. O pedido segue para aprovação do Financeiro.",
        extra: html`<dl class="pares lista"><div><dt>Fornecedor</dt><dd>${v?.nome_fantasia || v?.razao_social}</dd></div><div><dt>Valor total</dt><dd><strong>${formato.moeda(v?.valor_total)}</strong></dd></div><div><dt>Prazo</dt><dd>${v?.prazo_entrega_dias} dias</dd></div></dl>
          <div class="form-grade"><div class="campo col-6"><label for="e-pag">Condições de pagamento</label><input id="e-pag" name="condicoes_pagamento" maxlength="300" value="${v?.condicoes_pagamento || ""}"></div>
          <div class="campo col-6"><label for="e-local">Local de entrega</label><input id="e-local" name="local_entrega" maxlength="160" value="${s.local_entrega || "Almoxarifado central"}"></div>
          <div class="campo"><label for="e-obs">Observações ao fornecedor</label><textarea id="e-obs" name="observacoes" maxlength="2000"></textarea></div></div>`,
      });
      if (r.confirmado) {
        const resp = await executar("emitir_pedido", r.dados, null, "Pedido de compra emitido");
        if (resp?.pedido_criado) navegar(`/pedidos/${resp.pedido_criado}`);
      }
    }
  });
  on(raiz, "click", "[data-nova-proposta]", () => modalProposta(d, null, (r) => atualizar(r)).catch(toastErro));
  on(raiz, "click", "[data-editar-proposta]", (e, b) => modalProposta(d, d.cotacoes.find((c) => c.id === b.dataset.editarProposta), (r) => atualizar(r)).catch(toastErro));
  on(raiz, "click", "[data-remover-proposta]", async (e, b) => {
    const c = d.cotacoes.find((x) => x.id === b.dataset.removerProposta);
    const r = await confirmar({ titulo: "Remover proposta?", mensagem: `A proposta de ${c.nome_fantasia || c.razao_social} será excluída do mapa comparativo.`, rotuloConfirmar: "Remover", tom: "perigo" });
    if (!r.confirmado) return;
    try { atualizar(await api.delete(`/propostas/${c.id}`)); toast("sucesso", "Proposta removida"); } catch (erro) { toastErro(erro); }
  });
  on(raiz, "click", "[data-escolher]", async (e, b) => {
    const c = d.cotacoes.find((x) => x.id === b.dataset.escolher);
    const comp = d.comparacao;
    const naoMenor = comp.menor_total !== null && Number(c.valor_total) > Number(comp.menor_total);
    const exige = comp.abaixo_do_minimo || naoMenor;
    const motivo = [comp.abaixo_do_minimo ? `há menos de ${comp.minimo_cotacoes} propostas` : "", naoMenor ? "a proposta não é a de menor valor" : ""].filter(Boolean).join(" e ");
    const r = await confirmar({
      titulo: `Escolher ${c.nome_fantasia || c.razao_social}`, rotuloConfirmar: "Assinar e definir fornecedor", tom: "sucesso", icone: "assinatura",
      mensagem: html`Valor total <strong>${formato.moeda(c.valor_total)}</strong> · prazo ${c.prazo_entrega_dias} dias · ${c.condicoes_pagamento || "pagamento a combinar"}.`,
      extra: exige ? aviso("alerta", "Justificativa obrigatória", `Neste caso ${motivo}.`) : "",
      justificativa: exige ? "Justificativa da escolha" : "Observação (opcional)", minimo: exige ? 10 : 0,
    });
    if (r.confirmado) await executar("definir_fornecedor", { cotacao_id: c.id, texto: r.texto }, null, "Fornecedor definido");
  });
  on(raiz, "click", "[data-ver-anexo]", (e, b) => visualizarAnexo(b.dataset.verAnexo));
  on(raiz, "click", "[data-baixar-anexo]", (e, b) => api.baixar(`/anexos/${b.dataset.baixarAnexo}/arquivo`).catch(toastErro));
  on(raiz, "click", "[data-remover-anexo]", async (e, b) => {
    const r = await confirmar({ titulo: "Remover documento?", mensagem: "O arquivo deixa de aparecer, mas fica preservado para auditoria.", rotuloConfirmar: "Remover", tom: "perigo" });
    if (!r.confirmado) return;
    try { await api.delete(`/anexos/${b.dataset.removerAnexo}`); await recarregar(); toast("sucesso", "Documento removido"); } catch (erro) { toastErro(erro); }
  });
  on(raiz, "click", "[data-dossie]", (e, b) => comCarregamento(b, api.baixar(`/solicitacoes/${params.id}/dossie.pdf`)).catch(toastErro));
  on(raiz, "click", "[data-verificar]", async (e, b) => {
    try {
      const v = await comCarregamento(b, api.get(`/assinaturas/${b.dataset.verificar}/verificar`));
      modal({ titulo: "Verificação da assinatura", sub: rotulo("acao_assinatura", v.acao), conteudo: html`<div class="pilha">
        ${v.registro_integro ? aviso("sucesso", "Assinatura autêntica", "O registro não foi alterado desde a assinatura.") : aviso("perigo", "Assinatura inválida", "O registro não confere com o hash de autenticidade.")}
        ${v.conteudo_inalterado_desde_assinatura ? aviso("info", "Conteúdo idêntico ao assinado") : aviso("info", "O processo avançou após esta assinatura", "É esperado: cada etapa posterior altera o conteúdo e gera nova assinatura.")}
        <dl class="pares lista"><div><dt>Assinante</dt><dd>${v.usuario_nome} · ${rotulo("papel", v.papel)}</dd></div><div><dt>Data e hora</dt><dd>${formato.dataHora(v.assinado_em)}</dd></div>
        <div><dt>IP de origem</dt><dd>${v.ip}</dd></div><div><dt>Algoritmo</dt><dd>${v.algoritmo}</dd></div></dl>
        <div><p class="grupo-titulo-secao">Hash de autenticidade</p><p class="mono-hash">${v.hash_autenticidade}</p></div></div>` });
    } catch (erro) { toastErro(erro); }
  });

  renderizarTudo();

  const recarregarDebounce = debounce(() => { if (!document.querySelector("dialog[open]")) recarregar().catch(() => {}); }, 800);
  const desligar = ouvir("evento", (ev) => { if (ev.solicitacao_id === params.id || ev.id === params.id) recarregarDebounce(); });
  return { desmontar: desligar };
}

