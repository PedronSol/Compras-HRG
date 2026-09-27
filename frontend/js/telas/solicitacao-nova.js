// Abertura e ajuste de solicitação: identificação, itens (catálogo ou livre), justificativa e documentos.
import { api } from "../api.js";
import { estado } from "../estado.js";
import { navegar } from "../roteador.js";
import { html, renderizar, on, debounce, mostrarErrosCampos, seguro } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { aviso, cabecalho, comCarregamento, formato, opcoes, toast, toastErro } from "../ui/componentes.js";
import { ativarUpload, zonaUpload } from "../ui/upload.js";

const TIPOS = [
  ["material", "Materiais e insumos", "caixa", "Descartáveis, medicamentos, reagentes, papelaria"],
  ["equipamento", "Equipamentos", "monitor", "Equipamentos médicos, mobiliário, informática"],
  ["servico", "Serviços", "ferramenta", "Manutenção, calibração, serviços técnicos"],
];

function linhaItem(item = {}, i = 0) {
  const un = estado.meta.rotulos.unidade;
  return html`<tr data-item="${i}">
    <td class="col-desc"><div class="relativo">
      <input class="entrada" name="item_descricao" aria-label="Descrição do item ${i + 1}" placeholder="Busque no catálogo ou descreva o item" maxlength="300" autocomplete="off" value="${item.descricao || ""}" data-material="${item.material_id || ""}">
      <div class="sugestoes oculto" role="listbox"></div></div>
      <span class="material-vinculado ${item.material_id ? "" : "oculto"}">${icone("check")}<span data-cod>${item.material_codigo || "Item do catálogo"}</span></span></td>
    <td class="col-qtd"><input class="entrada num" name="quantidade" inputmode="decimal" aria-label="Quantidade" placeholder="Qtd." value="${item.quantidade ? formato.numero(item.quantidade) : ""}"></td>
    <td class="col-un"><select class="entrada" name="unidade" aria-label="Unidade">${opcoes(Object.fromEntries(Object.keys(un).map((k) => [k, k])), item.unidade || "UN")}</select></td>
    <td class="col-valor"><div class="entrada-prefixo"><span>R$</span><input class="entrada num" name="valor" inputmode="decimal" aria-label="Valor unitário estimado" placeholder="0,00" value="${item.valor_unitario_estimado ? formato.entradaDecimal(item.valor_unitario_estimado) : ""}"></div></td>
    <td class="col-total" data-total>—</td>
    <td class="col-rem"><button type="button" class="botao fantasma icone pequeno" data-remover aria-label="Remover item ${i + 1}">${icone("lixeira")}</button></td>
  </tr>`;
}

export async function montar({ raiz, params }) {
  const edicao = Boolean(params.id);
  const [parametros, detalhe] = await Promise.all([api.get("/parametros"), edicao ? api.get(`/solicitacoes/${params.id}`) : null]);
  const s = detalhe?.solicitacao || { tipo: "material", urgencia: "normal" };
  if (edicao && !detalhe.acoes.includes("reenviar")) {
    renderizar(raiz, aviso("alerta", "Esta solicitação não pode ser ajustada", "Somente solicitações devolvidas para ajustes podem ser editadas pelo setor."));
    return;
  }
  const alcada = parametros.alcada_diretoria;
  const slaDias = estado.meta.sla_dias;
  const u = estado.usuario;

  renderizar(raiz, html`
    ${cabecalho({
      titulo: edicao ? `Ajustar ${s.codigo}` : "Nova solicitação de compra",
      sub: edicao ? "Faça os ajustes pedidos e reenvie para aprovação." : html`Setor <strong>${u.setor_nome}</strong> · ${u.papel === "gestor" ? "aberta por gestor: segue direto para a Diretoria" : "será analisada pelo gestor do setor"}`,
      migalhas: [{ rotulo: "Solicitações", href: "/solicitacoes" }, ...(edicao ? [{ rotulo: s.codigo, href: `/solicitacoes/${s.id}` }] : []), { rotulo: edicao ? "Ajustar" : "Nova" }],
    })}
    ${edicao && s.motivo_devolucao ? html`<div class="pilha">${aviso("alerta", "O que precisa ser ajustado", s.motivo_devolucao)}</div>` : ""}
    <form id="form-sol" class="grade-principal" novalidate>
      <div class="pilha">
        <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("documento")}1. Identificação</h2></div>
          <div class="cartao-corpo form-grade">
            <fieldset data-campo="tipo"><legend class="campo"><span class="rotulo">Tipo de solicitação<span class="obrigatorio">*</span></span></legend>
              <div class="opcoes-cartao">${TIPOS.map(([v, r, ic, d]) => html`<label><input type="radio" name="tipo" value="${v}" ${s.tipo === v ? seguro("checked") : ""}><span class="opcao">${icone(ic)}<span><strong>${r}</strong><small>${d}</small></span></span></label>`)}</div></fieldset>
            <div class="campo"><label for="titulo">Título<span class="obrigatorio" aria-hidden="true">*</span></label>
              <input id="titulo" name="titulo" required minlength="5" maxlength="160" value="${s.titulo || ""}" placeholder="Ex.: Reposição de materiais descartáveis para a UTI"></div>
            <div class="campo col-5" data-campo="urgencia"><span class="rotulo" id="rot-urg">Urgência<span class="obrigatorio">*</span></span>
              <div class="segmentado" role="radiogroup" aria-labelledby="rot-urg">${Object.entries(estado.meta.rotulos.urgencia).map(([v, r]) => html`<label><input type="radio" name="urgencia" value="${v}" ${s.urgencia === v ? seguro("checked") : ""}><span>${r}</span></label>`)}</div>
              <p class="ajuda" data-sla>Prazo de atendimento: ${slaDias[s.urgencia]} dias até o pedido</p></div>
            <div class="campo col-3"><label for="data_necessidade">Necessário até</label><input id="data_necessidade" name="data_necessidade" type="date" min="${formato.hojeISO()}" value="${s.data_necessidade || ""}"></div>
            <div class="campo col-4"><label for="local_entrega">Local de entrega</label><input id="local_entrega" name="local_entrega" maxlength="160" value="${s.local_entrega || ""}" placeholder="Almoxarifado central"></div>
          </div></section>

        <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("caixa")}2. Itens</h2><span class="pequeno texto-3">Busque no catálogo para padronizar descrição e unidade</span></div>
          <div class="cartao-corpo" data-campo="itens">
            <div class="tabela-envoltorio"><table class="editor-itens"><thead><tr><th>Descrição</th><th>Quantidade</th><th>Unidade</th><th>Valor unit. estimado</th><th class="direita">Total</th><th><span class="sr-only">Remover</span></th></tr></thead>
              <tbody id="itens">${(detalhe?.itens?.length ? detalhe.itens : [{}]).map(linhaItem)}</tbody></table></div>
            <button type="button" class="botao secundario pequeno" id="add-item">${icone("mais")}Adicionar item</button>
          </div></section>

        <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("editar")}3. Justificativa</h2></div>
          <div class="cartao-corpo form-grade">
            <div class="campo"><label for="justificativa">Por que esta compra é necessária?<span class="obrigatorio" aria-hidden="true">*</span></label>
              <textarea id="justificativa" name="justificativa" required minlength="20" maxlength="5000" placeholder="Descreva a necessidade, o impacto assistencial e o consumo previsto.">${s.justificativa || ""}</textarea>
              <div class="contador-caracteres" data-contador></div></div>
            <div class="campo"><label for="descricao">Especificações e observações</label>
              <textarea id="descricao" name="descricao" maxlength="5000" placeholder="Especificação técnica, marcas de referência, compatibilidade, etc.">${s.descricao || ""}</textarea></div>
          </div></section>

        <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("anexo")}4. Orçamentos e documentos</h2><span class="pequeno texto-3">Opcional</span></div>
          <div class="cartao-corpo pilha">
            ${edicao && detalhe.anexos.some((a) => !a.removido_em && a.origem === "solicitante") ? html`<div><p class="grupo-titulo-secao">Documentos já anexados</p>
              <ul class="lista-arquivos">${detalhe.anexos.filter((a) => !a.removido_em && a.origem === "solicitante").map((a) => html`<li class="arquivo" data-anexo="${a.id}">
                <span class="icone-arquivo">${icone(a.mime === "application/pdf" ? "pdf" : "documento")}</span><span class="info-arquivo"><span class="nome">${a.nome_original}</span><span class="meta">${formato.tamanho(a.tamanho)} · ${formato.data(a.criado_em)}</span></span>
                <span class="acoes"><label class="checkbox pequeno"><input type="checkbox" name="remover_anexos" value="${a.id}"><span>Remover</span></label></span></li>`)}</ul></div>` : ""}
            ${zonaUpload({ id: "arquivos", max: 5, rotulo: "Anexar ou fotografar orçamentos de referência" })}
            <input type="hidden" name="tipo_documento" value="orcamento">
          </div></section>
        ${edicao ? html`<section class="cartao"><div class="cartao-corpo"><div class="campo"><label for="texto">Resumo dos ajustes realizados</label>
          <textarea id="texto" name="texto" maxlength="2000" placeholder="Ex.: especificação detalhada e quantidades revisadas conforme consumo."></textarea></div></div></section>` : ""}
      </div>

      <aside>
        <section class="cartao"><div class="cartao-cabecalho"><h2>${icone("moeda")}Resumo</h2></div>
          <div class="cartao-corpo pilha">
            <dl class="pares lista"><div><dt>Itens</dt><dd data-qtd-itens>0</dd></div><div><dt>Setor</dt><dd>${u.setor_nome}</dd></div><div><dt>Prazo de atendimento</dt><dd data-prazo>${slaDias[s.urgencia]} dias</dd></div></dl>
            <div class="resumo-total"><span class="texto-3">Total estimado</span><span class="valor-total" data-total-geral>R$ 0,00</span></div>
            <div data-alcada></div>
            <div><p class="grupo-titulo-secao">Caminho de aprovação</p><ol class="linha-tempo" data-caminho></ol></div>
          </div>
          <div class="cartao-rodape"><a class="botao secundario" href="${edicao ? `/solicitacoes/${s.id}` : "/solicitacoes"}">Cancelar</a>
            <button class="botao" type="submit">${icone(edicao ? "enviar" : "assinatura")}${edicao ? "Reenviar para aprovação" : "Assinar e enviar"}</button></div>
        </section>
        <p class="nota-privacidade">${icone("escudo")}<span>Ao enviar, sua assinatura eletrônica é registrada com data, hora e IP. Os documentos ficam cifrados e são apenas anexados — os valores são sempre informados por você.</span></p>
      </aside>
    </form>`);

  const form = raiz.querySelector("#form-sol");
  const corpoItens = raiz.querySelector("#itens");
  const upload = ativarUpload(form, { id: "arquivos", max: 5 });

  function itensAtuais() {
    return [...corpoItens.querySelectorAll("tr")].map((tr) => ({
      tr,
      material_id: tr.querySelector('[name="item_descricao"]').dataset.material || null,
      descricao: tr.querySelector('[name="item_descricao"]').value.trim(),
      unidade: tr.querySelector('[name="unidade"]').value,
      quantidade: formato.lerDecimal(tr.querySelector('[name="quantidade"]').value),
      valor: formato.lerDecimal(tr.querySelector('[name="valor"]').value),
    }));
  }

  function recalcular() {
    const itens = itensAtuais();
    let total = 0;
    for (const i of itens) {
      const t = i.quantidade * i.valor;
      total += t;
      i.tr.querySelector("[data-total]").textContent = t ? formato.moeda(t) : "—";
    }
    const validos = itens.filter((i) => i.descricao && i.quantidade > 0).length;
    raiz.querySelector("[data-qtd-itens]").textContent = validos;
    raiz.querySelector("[data-total-geral]").textContent = formato.moeda(total);
    const exigeDiretoria = u.papel === "gestor" || total >= alcada;
    renderizar(raiz.querySelector("[data-alcada]"), total >= alcada
      ? aviso("info", "Acima da alçada de " + formato.moeda(alcada), "Após o gestor, a Diretoria também aprovará esta solicitação.")
      : "");
    const passos = [
      ...(u.papel === "gestor" ? [] : [["Gestor do setor", "usuario_check"]]),
      ...(exigeDiretoria ? [["Diretoria", "maleta"]] : []),
      ["Compras: cotação e pedido", "carrinho"], ["Financeiro aprova o pedido", "carteira"], ["Recebimento e conferência", "caminhao"],
    ];
    renderizar(raiz.querySelector("[data-caminho]"), html`${passos.map(([r, ic]) => html`<li><span class="icone-t">${icone(ic)}</span><span class="t-titulo pequeno">${r}</span></li>`)}`);
    corpoItens.querySelectorAll("[data-remover]").forEach((b) => { b.disabled = itens.length === 1; });
  }

  function reindexar() { corpoItens.querySelectorAll("tr").forEach((tr, i) => { tr.dataset.item = i; }); }
  raiz.querySelector("#add-item").addEventListener("click", () => {
    corpoItens.insertAdjacentHTML("beforeend", linhaItem({}, corpoItens.children.length).toString());
    reindexar(); recalcular();
    corpoItens.lastElementChild.querySelector('[name="item_descricao"]').focus();
  });
  on(corpoItens, "click", "[data-remover]", (e, b) => { b.closest("tr").remove(); reindexar(); recalcular(); });
  form.addEventListener("input", (e) => {
    if (e.target.name === "item_descricao") {
      e.target.dataset.material = "";
      e.target.closest("td").querySelector(".material-vinculado").classList.add("oculto");
      buscarMaterial(e.target);
    }
    recalcular();
  });
  form.addEventListener("change", (e) => {
    if (e.target.name === "urgencia") {
      const d = slaDias[e.target.value];
      raiz.querySelector("[data-sla]").textContent = `Prazo de atendimento: ${d} dias até o pedido`;
      raiz.querySelector("[data-prazo]").textContent = `${d} dias`;
    }
  });

  // Autocompletar com o catálogo de materiais
  const buscarMaterial = debounce(async (input) => {
    const caixa = input.parentElement.querySelector(".sugestoes");
    const q = input.value.trim();
    if (q.length < 2) { caixa.classList.add("oculto"); return; }
    try {
      const r = await api.get("/materiais", { q, ativos: 1, por_pagina: 8 });
      if (!r.itens.length || document.activeElement !== input) { caixa.classList.add("oculto"); return; }
      renderizar(caixa, html`${r.itens.map((m) => html`<button type="button" role="option" data-id="${m.id}" data-nome="${m.nome}" data-un="${m.unidade}" data-cod="${m.codigo}" data-preco="${m.ultimo_preco ?? m.preco_referencia ?? ""}">
        <span class="cod">${m.codigo}</span><span>${m.nome}</span><span class="preco">${m.unidade}${m.ultimo_preco || m.preco_referencia ? html` · ${formato.moeda(m.ultimo_preco ?? m.preco_referencia)}` : ""}</span></button>`)}`);
      caixa.classList.remove("oculto");
    } catch { caixa.classList.add("oculto"); }
  }, 220);
  on(corpoItens, "mousedown", ".sugestoes button", (e, b) => {
    e.preventDefault();
    const tr = b.closest("tr");
    const desc = tr.querySelector('[name="item_descricao"]');
    desc.value = b.dataset.nome;
    desc.dataset.material = b.dataset.id;
    tr.querySelector('[name="unidade"]').value = b.dataset.un;
    const valor = tr.querySelector('[name="valor"]');
    if (!valor.value && b.dataset.preco) valor.value = formato.entradaDecimal(b.dataset.preco);
    const vinc = tr.querySelector(".material-vinculado");
    vinc.querySelector("[data-cod]").textContent = `${b.dataset.cod} · item do catálogo`;
    vinc.classList.remove("oculto");
    b.parentElement.classList.add("oculto");
    tr.querySelector('[name="quantidade"]').focus();
    recalcular();
  });
  corpoItens.addEventListener("focusout", (e) => { if (e.target.name === "item_descricao") setTimeout(() => e.target.parentElement.querySelector(".sugestoes")?.classList.add("oculto"), 150); });

  const just = form.justificativa;
  const contador = raiz.querySelector("[data-contador]");
  const atualizarContador = () => {
    const n = just.value.trim().length;
    contador.textContent = n < 20 ? `${n}/20 caracteres mínimos` : `${n} caracteres`;
    contador.classList.toggle("insuficiente", n < 20);
  };
  just.addEventListener("input", atualizarContador);
  atualizarContador();
  recalcular();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const itens = itensAtuais().filter((i) => i.descricao || i.quantidade);
    const erros = {};
    if (!form.tipo.value) erros.tipo = "Selecione o tipo";
    if (form.titulo.value.trim().length < 5) erros.titulo = "Informe um título com ao menos 5 caracteres";
    if (just.value.trim().length < 20) erros.justificativa = "Justifique com ao menos 20 caracteres";
    if (!itens.length) erros.itens = "Inclua ao menos um item";
    else if (itens.some((i) => !i.descricao || !(i.quantidade > 0))) erros.itens = "Cada item precisa de descrição e quantidade maior que zero";
    mostrarErrosCampos(form, erros);
    if (Object.keys(erros).length) { toast("alerta", "Revise os campos destacados"); return; }

    const fd = new FormData();
    for (const campo of ["tipo", "titulo", "urgencia", "data_necessidade", "local_entrega", "justificativa", "descricao", "tipo_documento"]) {
      const valor = form.elements[campo]?.value ?? "";
      if (valor !== "") fd.append(campo, valor);
    }
    fd.append("itens", JSON.stringify(itens.map((i) => ({
      material_id: i.material_id || undefined, descricao: i.descricao, unidade: i.unidade,
      quantidade: String(i.quantidade), valor_unitario_estimado: String(i.valor || 0),
    }))));
    upload.arquivos().forEach((f) => fd.append("arquivos", f, f.name));
    const botao = form.querySelector('button[type="submit"]');
    try {
      let r;
      if (edicao) {
        fd.append("versao", s.versao);
        if (form.texto?.value.trim()) fd.append("texto", form.texto.value.trim());
        const remover = [...form.querySelectorAll('[name="remover_anexos"]:checked')].map((c) => c.value);
        if (remover.length) fd.append("remover_anexos", remover.join(","));
        r = await comCarregamento(botao, api.enviarFormulario(`/solicitacoes/${s.id}/acoes/reenviar`, fd));
        toast("sucesso", "Solicitação reenviada", `${r.solicitacao.codigo} voltou para aprovação.`);
      } else {
        r = await comCarregamento(botao, api.enviarFormulario("/solicitacoes", fd));
        toast("sucesso", "Solicitação enviada e assinada", `${r.solicitacao.codigo} · ${r.solicitacao.status === "aguardando_diretoria" ? "aguardando a Diretoria" : "aguardando o gestor do setor"}`);
      }
      navegar(`/solicitacoes/${r.solicitacao.id}`);
    } catch (erro) {
      mostrarErrosCampos(form, erro.campos);
      toastErro(erro);
    }
  });
}
