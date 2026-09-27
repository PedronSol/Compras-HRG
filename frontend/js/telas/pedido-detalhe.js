// Pedido de compra: aprovação (Financeiro/Diretoria), envio ao fornecedor, recebimento e conferência.
import { api } from "../api.js";
import { emitir, ouvir, rotulo } from "../estado.js";
import { html, renderizar, on, debounce, mostrarErrosCampos } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import {
  aviso, badgePedido, badgeRecebimento, badgeSetor, badgeUrgencia, cabecalho, comCarregamento, confirmar, formato,
  modal, toast, toastErro, vazio,
} from "../ui/componentes.js";
import { ativarUpload, zonaUpload } from "../ui/upload.js";

const ETAPAS_PEDIDO = ["Emitido", "Aprovação", "Enviado", "Entregue"];

function fluxoPedido(p) {
  const st = p.status;
  let atual = { aguardando_financeiro: 1, aguardando_diretoria: 1, aprovado: 2, enviado: 3, entregue_parcial: 3, entregue: 4, reprovado: 1, cancelado: 1 }[st];
  const bloq = ["reprovado", "cancelado"].includes(st);
  if (st === "cancelado") atual = p.enviado_em ? 2 : p.aprovado_financeiro_em ? 2 : 1;
  const det = [formato.dataCurta(p.criado_em),
    st === "aguardando_financeiro" ? "Financeiro" : st === "aguardando_diretoria" ? "Diretoria" : st === "reprovado" ? "Reprovado" : p.aprovado_financeiro_em ? formato.dataCurta(p.aprovado_diretoria_em || p.aprovado_financeiro_em) : "",
    p.enviado_em ? formato.dataCurta(p.enviado_em) : "", st === "entregue" ? formato.dataCurta(p.concluido_em) : st === "entregue_parcial" ? `${p.percentual_recebido}% recebido` : ""];
  return html`<ol class="fluxo quatro" aria-label="Etapas do pedido">${ETAPAS_PEDIDO.map((n, i) => {
    const estadoE = i < atual ? "concluida" : i === atual ? (bloq ? "bloqueada" : "atual") : "pendente";
    return html`<li class="etapa ${estadoE}"><span class="marcador">${estadoE === "concluida" ? icone("check") : estadoE === "bloqueada" ? icone("x") : i + 1}</span><span class="nome">${n}</span><span class="detalhe">${det[i] || " "}</span></li>`;
  })}</ol>`;
}

/** Modal de recebimento e conferência. Resolve com os dados atualizados do pedido (ou null). */
export async function modalRecebimento(pedidoId) {
  const d = await api.get(`/pedidos/${pedidoId}`);
  const p = d.pedido;
  const pendentes = d.itens.filter((i) => Number(i.saldo) > 0);
  return new Promise((resolve) => {
    let resultado = null;
    const m = modal({
      titulo: `Registrar entrega · ${p.codigo}`, sub: `${p.fornecedor_fantasia || p.fornecedor_nome} · previsão ${formato.data(p.data_prevista_entrega)}`, tamanho: "extra",
      conteudo: html`<form id="form-rec" class="pilha" novalidate>
        <div class="form-grade">
          <div class="campo col-4"><label for="r-nf">Número da nota fiscal<span class="obrigatorio">*</span></label><input id="r-nf" name="nota_fiscal" required maxlength="60" autofocus></div>
          <div class="campo col-4"><label for="r-data">Emissão da NF</label><input id="r-data" name="data_emissao_nf" type="date" max="${formato.hojeISO()}"></div>
          <div class="campo col-4"><label for="r-valor">Valor da NF</label><div class="entrada-prefixo"><span>R$</span><input id="r-valor" name="valor_nf" inputmode="decimal" placeholder="0,00"></div></div>
        </div>
        <div data-campo="itens"><p class="grupo-titulo-secao">Conferência dos itens</p>
          <div class="tabela-envoltorio"><table class="tabela densa responsiva"><thead><tr><th>Item</th><th class="num">Pedido</th><th class="num">Saldo a receber</th><th>Qtd. recebida</th><th>Qtd. aceita</th><th>Divergência</th></tr></thead>
          <tbody>${pendentes.map((i) => html`<tr data-item="${i.id}" data-saldo="${i.saldo}">
            <td class="principal-td"><div class="principal-celula"><strong>${i.descricao}</strong><small>${i.marca || ""}</small></div></td>
            <td data-rotulo="Pedido" class="num">${formato.numero(i.quantidade)} ${i.unidade}</td>
            <td data-rotulo="Saldo" class="num"><strong>${formato.numero(i.saldo)} ${i.unidade}</strong></td>
            <td data-rotulo="Recebida"><input class="entrada num" name="recebida" inputmode="decimal" value="${formato.numero(i.saldo)}" aria-label="Quantidade recebida"></td>
            <td data-rotulo="Aceita"><input class="entrada num" name="aceita" inputmode="decimal" value="${formato.numero(i.saldo)}" aria-label="Quantidade aceita"></td>
            <td data-rotulo="Divergência"><input class="entrada" name="motivo" maxlength="500" placeholder="Motivo, se houver" aria-label="Motivo da divergência"></td></tr>`)}</tbody></table></div>
          <p class="ajuda espaco-topo">Informe 0 nos itens não entregues. Se aceitar menos que o recebido, descreva o motivo. Quantidades recusadas (avaria, validade, especificação) continuam como saldo pendente.</p></div>
        <div class="campo"><label for="r-obs">Observações da conferência</label><textarea id="r-obs" name="observacoes" maxlength="2000"></textarea></div>
        ${zonaUpload({ id: "nf-arquivos", max: 3, rotulo: "Nota fiscal e fotos da entrega", ajuda: "Anexe ou fotografe a nota fiscal e, se houver divergência, fotos da carga." })}
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="form-rec">${icone("assinatura")}Assinar e registrar entrega</button>`,
      aoFechar: () => resolve(resultado),
    });
    const form = m.el.querySelector("#form-rec");
    const up = ativarUpload(form, { id: "nf-arquivos", max: 3 });
    form.addEventListener("input", (e) => {
      if (e.target.name === "recebida") e.target.closest("tr").querySelector('[name="aceita"]').value = e.target.value;
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const itens = [...form.querySelectorAll("tr[data-item]")].map((tr) => ({
        pedido_item_id: tr.dataset.item, saldo: Number(tr.dataset.saldo),
        quantidade_recebida: formato.lerDecimal(tr.querySelector('[name="recebida"]').value),
        quantidade_aceita: formato.lerDecimal(tr.querySelector('[name="aceita"]').value),
        motivo_divergencia: tr.querySelector('[name="motivo"]').value.trim(),
      }));
      const erros = {};
      if (!form.nota_fiscal.value.trim()) erros.nota_fiscal = "Informe o número da nota fiscal";
      if (!itens.some((i) => i.quantidade_recebida > 0)) erros.itens = "Informe a quantidade recebida de ao menos um item";
      else if (itens.some((i) => i.quantidade_aceita > i.quantidade_recebida)) erros.itens = "A quantidade aceita não pode superar a recebida";
      else if (itens.some((i) => i.quantidade_aceita > i.saldo)) erros.itens = "A quantidade aceita não pode superar o saldo do pedido";
      else if (itens.some((i) => i.quantidade_aceita < i.quantidade_recebida && i.motivo_divergencia.length < 5)) erros.itens = "Descreva a divergência dos itens não aceitos";
      mostrarErrosCampos(form, erros);
      if (Object.keys(erros).length) return;
      const fd = new FormData();
      ["nota_fiscal", "data_emissao_nf", "valor_nf", "observacoes"].forEach((c) => { if (form[c].value.trim()) fd.append(c, form[c].value.trim()); });
      fd.append("itens", JSON.stringify(itens.filter((i) => i.quantidade_recebida > 0).map(({ saldo, ...i }) => ({ ...i, quantidade_recebida: String(i.quantidade_recebida), quantidade_aceita: String(i.quantidade_aceita), motivo_divergencia: i.motivo_divergencia || undefined }))));
      up.arquivos().forEach((f) => fd.append("arquivos", f, f.name));
      try {
        resultado = await comCarregamento(m.el.querySelector('[type="submit"]'), api.enviarFormulario(`/pedidos/${pedidoId}/recebimentos`, fd));
        const rec = resultado.recebimentos[resultado.recebimentos.length - 1];
        toast(rec.situacao === "conforme" ? "sucesso" : "alerta", "Entrega registrada", `${rec.codigo} · ${rotulo("situacao_recebimento", rec.situacao)} · pedido ${rotulo("status_pedido", resultado.pedido.status).toLowerCase()}`);
        emitir("atualizar-contadores");
        m.fechar();
      } catch (erro) { mostrarErrosCampos(form, erro.campos); toastErro(erro); }
    });
  });
}

export async function montar({ raiz, params }) {
  let d = await api.get(`/pedidos/${params.id}`);

  function render() {
    const p = d.pedido;
    const f = d.fornecedor;
    const a = d.acoes;
    const decisao = a.includes("aprovar");
    const avisos = [];
    if (p.status === "reprovado") avisos.push(aviso("perigo", "Pedido reprovado", p.motivo_reprovacao));
    if (p.status === "cancelado") avisos.push(aviso("perigo", "Pedido cancelado", p.motivo_cancelamento));
    if (p.atrasado) avisos.push(aviso("perigo", `Entrega atrasada há ${p.dias_atraso} dia(s)`, `A previsão era ${formato.data(p.data_prevista_entrega)}. Contate o fornecedor e atualize a previsão.`));
    if (p.encerrado_com_pendencia) avisos.push(aviso("alerta", "Encerrado com pendência", p.justificativa_encerramento));
    if (p.status === "aguardando_diretoria") avisos.push(aviso("info", "Acima da alçada", "O valor do pedido ultrapassa a alçada e a solicitação não havia passado pela Diretoria."));
    renderizar(raiz, html`
      ${cabecalho({
        titulo: `Pedido ${p.codigo}`, extra: badgePedido(p.status, true),
        sub: html`${p.fornecedor_fantasia || p.fornecedor_nome} · <a href="/solicitacoes/${p.solicitacao_id}">${p.solicitacao_codigo} · ${p.solicitacao_titulo}</a>`,
        migalhas: [{ rotulo: "Pedidos de compra", href: "/pedidos" }, { rotulo: p.codigo }],
        acoes: html`${a.includes("receber") ? html`<button class="botao" data-receber>${icone("caminhao")}Registrar entrega</button>` : ""}
          ${a.includes("enviar") ? html`<button class="botao" data-enviar>${icone("enviar")}Enviar ao fornecedor</button>` : ""}
          ${a.includes("atualizar_previsao") ? html`<button class="botao secundario" data-previsao>${icone("calendario")}Atualizar previsão</button>` : ""}
          ${a.includes("encerrar") ? html`<button class="botao secundario" data-encerrar>${icone("check_circulo")}Encerrar com pendência</button>` : ""}
          ${a.includes("cancelar") ? html`<button class="botao perigo-suave" data-cancelar>${icone("x_circulo")}Cancelar</button>` : ""}
          <button class="botao secundario" data-pdf>${icone("imprimir")}Documento do pedido</button>`,
      })}
      <div class="pilha">
        <section class="cartao">${fluxoPedido(p)}</section>
        ${avisos.length ? html`<div class="pilha-sm">${avisos}</div>` : ""}
        <div class="grade-principal">
          <div class="pilha">
            <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("caixa")}Itens do pedido</h2>
              <div class="progresso-rotulado"><div class="progresso sucesso"><span data-largura="${p.percentual_recebido}"></span></div>${p.percentual_recebido}% recebido</div></div>
              <div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Item</th><th class="num">Quantidade</th><th class="num">Unitário</th><th class="num">Total</th><th>Recebido</th></tr></thead>
              <tbody>${d.itens.map((i) => { const pct = Math.round((100 * Number(i.quantidade_recebida)) / Number(i.quantidade)); return html`<tr>
                <td class="principal-td"><div class="principal-celula"><strong>${i.descricao}</strong><small>${i.material_codigo ? html`<span class="mono">${i.material_codigo}</span>` : ""}${i.marca ? ` · ${i.marca}` : ""}</small></div></td>
                <td data-rotulo="Quantidade" class="num">${formato.numero(i.quantidade)} ${i.unidade}</td><td data-rotulo="Unitário" class="num">${formato.moeda(i.valor_unitario)}</td>
                <td data-rotulo="Total" class="num"><strong>${formato.moeda(i.total)}</strong></td>
                <td data-rotulo="Recebido"><div class="progresso-rotulado"><div class="progresso ${pct >= 100 ? "sucesso" : ""}"><span data-largura="${pct}"></span></div>${formato.numero(i.quantidade_recebida)}/${formato.numero(i.quantidade)}</div></td></tr>`; })}</tbody>
              <tfoot>${Number(p.frete) || Number(p.desconto) ? html`<tr><td colspan="3">Subtotal</td><td class="num">${formato.moeda(p.valor_itens)}</td><td></td></tr>` : ""}
                ${Number(p.frete) ? html`<tr><td colspan="3">Frete</td><td class="num">${formato.moeda(p.frete)}</td><td></td></tr>` : ""}
                ${Number(p.desconto) ? html`<tr><td colspan="3">Desconto</td><td class="num">− ${formato.moeda(p.desconto)}</td><td></td></tr>` : ""}
                <tr><td colspan="3">Valor total</td><td class="num">${formato.moeda(p.valor_total)}</td><td></td></tr></tfoot></table></div></section>

            <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("caminhao")}Recebimentos</h2></div>
              ${d.recebimentos.length ? html`<ul class="lista-itens">${d.recebimentos.map((r) => html`<li><div class="cartao-corpo compacto pilha-sm">
                <div class="linha-flex"><strong>${r.codigo}</strong><span class="texto-3 pequeno">NF ${r.nota_fiscal}${r.valor_nf ? ` · ${formato.moeda(r.valor_nf)}` : ""}</span><span class="espacador"></span>${badgeRecebimento(r.situacao)}</div>
                <div class="minusculo texto-3">${r.recebido_por_nome} · ${formato.dataHora(r.recebido_em)}</div>
                <table class="tabela densa"><tbody>${r.itens.map((ri) => html`<tr><td>${ri.descricao}</td><td class="num">${formato.numero(ri.quantidade_recebida)} recebido(s)</td>
                  <td class="num">${formato.numero(ri.quantidade_aceita)} aceito(s)</td><td class="texto-3 pequeno">${ri.motivo_divergencia || ""}</td></tr>`)}</tbody></table>
                ${r.observacoes ? html`<p class="pequeno texto-2">${r.observacoes}</p>` : ""}
                ${r.anexos.length ? html`<div class="linha-flex">${r.anexos.map((an) => html`<button class="botao secundario pequeno" data-anexo="${an.id}">${icone(an.mime.startsWith("image/") ? "camera" : "pdf")}${an.nome_original}</button>`)}</div>` : ""}
              </div></li>`)}</ul>` : vazio("Nenhuma entrega registrada", p.status === "enviado" ? "O Recebimento registra a entrega na chegada da mercadoria." : "", "", "caminhao", true)}
            </section>

            <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("historico")}Histórico do pedido</h2></div>
              <div class="cartao-corpo"><ol class="linha-tempo">${[...d.historico].reverse().map((h) => html`<li>
                <span class="icone-t ${["reprovado", "cancelado"].includes(h.status_para) ? "perigo" : h.status_para === "entregue" || h.status_para === "conforme" ? "sucesso" : "info"}">${icone(h.acao === "recebimento" ? "caminhao" : "pedido")}</span>
                <div><div class="t-titulo">${h.acao === "pedido_emitido" ? "Pedido emitido" : h.acao === "recebimento" ? `Recebimento · ${rotulo("situacao_recebimento", h.status_para)}` : `${rotulo("status_pedido", h.status_de)} → ${rotulo("status_pedido", h.status_para)}`}</div>
                <div class="t-meta">${h.autor_nome || "Sistema"} · ${formato.dataHora(h.criado_em)}</div>${h.observacao ? html`<div class="t-obs">${h.observacao}</div>` : ""}</div></li>`)}</ol></div></section>
          </div>
          <aside>
            ${decisao ? html`<section class="cartao destaque"><div class="cartao-cabecalho"><h2>${icone("carimbo")}Sua decisão · ${p.status === "aguardando_financeiro" ? "Financeiro" : "Diretoria"}</h2></div>
              <form class="cartao-corpo painel-decisao" id="form-decisao" novalidate>
                <div class="destaque-valor">${formato.moeda(p.valor_total)}</div>
                <p class="pequeno texto-3">${p.setor_nome} · ${p.condicoes_pagamento || "pagamento a combinar"} · entrega em ${p.prazo_entrega_dias} dias</p>
                ${p.status === "aguardando_financeiro" && p.exige_diretoria ? aviso("info", "Após o Financeiro, segue para a Diretoria", "O valor está acima da alçada.") : ""}
                <div class="campo"><label for="parecer">Parecer <span class="texto-3">(obrigatório para reprovar)</span></label><textarea id="parecer" name="texto" maxlength="2000" placeholder="Ex.: dotação orçamentária confirmada no centro de custo."></textarea></div>
                <div class="grupo-botoes"><button type="button" class="botao sucesso" data-decisao="aprovar">${icone("check")}Aprovar pedido</button>
                  <button type="button" class="botao perigo-suave" data-decisao="reprovar">${icone("x_circulo")}Reprovar</button></div>
                <p class="minusculo texto-3">Reprovar reabre a cotação para o comprador renegociar.</p>
              </form></section>` : ""}
            <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("fornecedor")}Fornecedor</h2></div>
              <div class="cartao-corpo"><dl class="pares lista">
                <div><dt>Razão social</dt><dd>${f.razao_social}</dd></div><div><dt>CNPJ</dt><dd class="mono">${formato.cnpj(f.cnpj)}</dd></div>
                <div><dt>Contato</dt><dd>${f.contato || "—"}</dd></div><div><dt>E-mail</dt><dd>${f.email || "—"}</dd></div><div><dt>Telefone</dt><dd>${f.telefone || "—"}</dd></div>
              </dl></div></section>
            <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("pedido")}Condições</h2></div>
              <div class="cartao-corpo"><dl class="pares lista">
                <div><dt>Setor</dt><dd>${badgeSetor(p.setor_codigo, p.setor_nome, p.setor_cor)}</dd></div><div><dt>Urgência</dt><dd>${badgeUrgencia(p.urgencia)}</dd></div>
                <div><dt>Emissão</dt><dd>${formato.dataHora(p.criado_em)}</dd></div><div><dt>Comprador</dt><dd>${p.comprador_nome}</dd></div>
                <div><dt>Pagamento</dt><dd>${p.condicoes_pagamento || "—"}</dd></div><div><dt>Prazo de entrega</dt><dd>${p.prazo_entrega_dias} dias</dd></div>
                <div><dt>Previsão de entrega</dt><dd>${formato.data(p.data_prevista_entrega)}${p.atrasado ? html` <span class="badge perigo">atrasado</span>` : ""}</dd></div>
                <div><dt>Local de entrega</dt><dd>${p.local_entrega || "—"}</dd></div>
              </dl>${p.observacoes ? html`<p class="pequeno texto-2">${p.observacoes}</p>` : ""}</div></section>
            <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("assinatura")}Aprovações e assinaturas</h2></div>
              ${d.assinaturas.length ? html`<div>${d.assinaturas.map((s) => html`<div class="assinatura"><span class="selo-ass">${icone("assinatura")}</span>
                <div><strong class="pequeno">${rotulo("acao_assinatura", s.acao)}</strong><div class="minusculo texto-3">${s.usuario_nome} · ${rotulo("papel", s.papel)} · ${formato.dataHora(s.assinado_em)}</div></div><span></span></div>`)}</div>`
                : vazio("Sem assinaturas", "", "", "assinatura", true)}</section>
          </aside>
        </div>
      </div>`);
  }

  const atualizar = (novo) => { if (novo) { d = novo; render(); } };
  async function acao(nome, corpo = {}, botao = null, msg = "") {
    try {
      atualizar(await comCarregamento(botao, api.post(`/pedidos/${params.id}/acoes/${nome}`, { versao: d.pedido.versao, ...corpo })));
      if (msg) toast("sucesso", msg, `${d.pedido.codigo} · ${rotulo("status_pedido", d.pedido.status)}`);
      emitir("atualizar-contadores");
    } catch (erro) { toastErro(erro); if (erro.status === 409) atualizar(await api.get(`/pedidos/${params.id}`)); }
  }

  on(raiz, "click", "[data-decisao]", async (e, b) => {
    const texto = raiz.querySelector("#parecer").value.trim();
    if (b.dataset.decisao === "reprovar" && texto.length < 10) { mostrarErrosCampos(raiz.querySelector("#form-decisao"), { texto: "Informe o motivo (mínimo 10 caracteres)" }); return; }
    await acao(b.dataset.decisao, { texto }, b, b.dataset.decisao === "aprovar" ? "Pedido aprovado" : "Pedido reprovado");
  });
  on(raiz, "click", "[data-enviar]", async () => {
    const p = d.pedido;
    const r = await confirmar({
      titulo: "Enviar pedido ao fornecedor", rotuloConfirmar: "Assinar e marcar como enviado", icone: "enviar",
      mensagem: `Confirme o envio do pedido para ${p.fornecedor_fantasia || p.fornecedor_nome}. Baixe o documento do pedido para encaminhar por e-mail.`,
      extra: html`<div class="campo"><label for="prev">Previsão de entrega</label><input id="prev" name="data_prevista_entrega" type="date" min="${formato.hojeISO()}" value="${formato.isoDias(p.prazo_entrega_dias)}"></div>`,
    });
    if (r.confirmado) await acao("enviar", { data_prevista_entrega: r.dados.data_prevista_entrega }, null, "Pedido enviado ao fornecedor");
  });
  on(raiz, "click", "[data-previsao]", async () => {
    const r = await confirmar({ titulo: "Atualizar previsão de entrega", rotuloConfirmar: "Salvar previsão",
      extra: html`<div class="campo"><label for="prev2">Nova previsão</label><input id="prev2" name="data_prevista_entrega" type="date" value="${d.pedido.data_prevista_entrega || ""}"></div>`,
      justificativa: "Informação do fornecedor (opcional)" });
    if (r.confirmado) await acao("atualizar_previsao", { data_prevista_entrega: r.dados.data_prevista_entrega, texto: r.texto }, null, "Previsão atualizada");
  });
  on(raiz, "click", "[data-encerrar]", async () => {
    const r = await confirmar({ titulo: "Encerrar pedido com pendência?", mensagem: "O saldo não entregue será dispensado e a solicitação será concluída.", justificativa: "Justificativa", minimo: 10, rotuloConfirmar: "Encerrar pedido", tom: "alerta" });
    if (r.confirmado) await acao("encerrar", { texto: r.texto }, null, "Pedido encerrado");
  });
  on(raiz, "click", "[data-cancelar]", async () => {
    const r = await confirmar({ titulo: `Cancelar ${d.pedido.codigo}?`, mensagem: "A solicitação volta para a cotação.", justificativa: "Motivo do cancelamento", minimo: 10, rotuloConfirmar: "Cancelar pedido", tom: "perigo" });
    if (r.confirmado) await acao("cancelar", { texto: r.texto }, null, "Pedido cancelado");
  });
  on(raiz, "click", "[data-receber]", async () => atualizar(await modalRecebimento(params.id).catch((e) => { toastErro(e); return null; })));
  on(raiz, "click", "[data-pdf]", (e, b) => comCarregamento(b, api.baixar(`/pedidos/${params.id}/documento.pdf`, { inline: 1 }, { abrir: true })).catch(toastErro));
  on(raiz, "click", "[data-anexo]", (e, b) => api.baixar(`/anexos/${b.dataset.anexo}/arquivo`, { inline: 1 }, { abrir: true }).catch(toastErro));

  render();
  const recarregar = debounce(async () => { if (!document.querySelector("dialog[open]")) atualizar(await api.get(`/pedidos/${params.id}`).catch(() => null)); }, 800);
  return { desmontar: ouvir("evento", (ev) => { if (ev.id === params.id || (ev.solicitacao_id && ev.solicitacao_id === d.pedido.solicitacao_id)) recarregar(); }) };
}
