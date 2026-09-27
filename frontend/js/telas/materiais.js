// Catálogo: materiais (com preço de referência e última compra) e categorias.
import { api } from "../api.js";
import { estado } from "../estado.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, debounce, dadosFormulario, mostrarErrosCampos } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { abas, cabecalho, carregandoBloco, comCarregamento, formato, modal, opcoes, paginacao, pode, toast, toastErro, vazio } from "../ui/componentes.js";

export async function montar({ raiz, consulta }) {
  const gerenciar = pode("material.gerenciar");
  let aba = consulta.aba === "categorias" ? "categorias" : "materiais";
  const f = { q: consulta.q || "", categoria: consulta.categoria || "", ativos: consulta.ativos !== "0", pagina: 1 };
  let categorias = (await api.get("/categorias")).itens;
  let materiais = [];

  renderizar(raiz, html`${cabecalho({ titulo: "Materiais e categorias", sub: "Catálogo padronizado usado nas solicitações, cotações e indicadores de gasto",
      acoes: gerenciar ? html`<button class="botao secundario" id="nova-cat">${icone("etiqueta")}Nova categoria</button><button class="botao" id="novo-mat">${icone("mais")}Novo material</button>` : "" })}
    <section class="cartao"><div id="abas"></div><div id="corpo-cat"></div></section>`);
  const corpo = raiz.querySelector("#corpo-cat");

  function desenharAbas() {
    renderizar(raiz.querySelector("#abas"), abas([{ valor: "materiais", rotulo: "Materiais", icone: "caixa", qtd: categorias.reduce((t, c) => t + c.materiais, 0) },
      { valor: "categorias", rotulo: "Categorias", icone: "etiqueta", qtd: categorias.length }], aba, { nome: "aba" }));
  }

  async function abaMateriais() {
    renderizar(corpo, html`<form class="barra-filtros" id="f-mat" role="search">
      <label class="busca"><span class="sr-only">Buscar</span>${icone("busca")}<input class="entrada" type="search" name="q" value="${f.q}" placeholder="Código ou nome do material"></label>
      <select class="entrada" name="categoria" aria-label="Categoria">${opcoes(Object.fromEntries(categorias.map((c) => [c.id, c.nome])), f.categoria, { vazio: "Todas as categorias" })}</select>
      <label class="checkbox pequeno"><input type="checkbox" name="ativos" ${f.ativos ? html`checked` : ""}><span>Somente ativos</span></label></form><div id="lista-mat">${carregandoBloco(6)}</div>`);
    const form = corpo.querySelector("#f-mat");
    form.addEventListener("input", debounce(() => { const d = Object.fromEntries(new FormData(form)); Object.assign(f, { q: d.q || "", categoria: d.categoria || "", ativos: d.ativos === "on", pagina: 1 }); carregarMateriais(); }, 300));
    form.addEventListener("submit", (e) => e.preventDefault());
    await carregarMateriais();
  }

  async function carregarMateriais() {
    atualizarConsulta({ q: f.q, categoria: f.categoria, ativos: f.ativos ? "" : "0", aba: "" });
    const alvo = corpo.querySelector("#lista-mat");
    const r = await api.get("/materiais", { q: f.q, categoria: f.categoria, ativos: f.ativos, pagina: f.pagina, por_pagina: 50 });
    materiais = r.itens;
    renderizar(alvo, r.itens.length ? html`<div class="tabela-envoltorio"><table class="tabela responsiva">
      <thead><tr><th>Material</th><th>Categoria</th><th>Unidade</th><th class="num">Preço de referência</th><th class="num">Última compra</th><th class="num">Solicitações</th>${gerenciar ? html`<th class="col-acao"></th>` : ""}</tr></thead>
      <tbody>${r.itens.map((m) => html`<tr>
        <td class="principal-td"><div class="principal-celula"><strong>${m.nome}</strong><small><span class="mono">${m.codigo}</span>${m.ativo ? "" : " · inativo"}</small></div></td>
        <td data-rotulo="Categoria"><span class="badge setor" data-cor="${m.categoria_cor}"><span class="ponto"></span>${m.categoria_nome}</span></td>
        <td data-rotulo="Unidade">${m.unidade} <small class="texto-3">${estado.meta.rotulos.unidade[m.unidade] || ""}</small></td>
        <td data-rotulo="Referência" class="num">${formato.moeda(m.preco_referencia)}</td>
        <td data-rotulo="Última compra" class="num">${m.ultimo_preco ? html`<strong>${formato.moeda(m.ultimo_preco)}</strong><br><small class="texto-3">${formato.data(m.ultima_compra_em)}</small>` : html`<span class="texto-3">—</span>`}</td>
        <td data-rotulo="Solicitações" class="num">${m.solicitacoes}</td>
        ${gerenciar ? html`<td class="col-acao"><button class="botao fantasma pequeno icone" data-editar-mat="${m.id}" aria-label="Editar ${m.nome}">${icone("editar")}</button></td>` : ""}</tr>`)}</tbody></table></div>${paginacao(r)}`
      : vazio("Nenhum material encontrado", "Ajuste a busca ou cadastre um novo material.", "", "caixa"));
  }

  function abaCategorias() {
    atualizarConsulta({ aba: "categorias", q: "", categoria: "", ativos: "" });
    renderizar(corpo, categorias.length ? html`<div class="tabela-envoltorio"><table class="tabela responsiva">
      <thead><tr><th>Categoria</th><th>Descrição</th><th class="num">Materiais ativos</th><th>Situação</th>${gerenciar ? html`<th class="col-acao"></th>` : ""}</tr></thead>
      <tbody>${categorias.map((c) => html`<tr><td class="principal-td"><span class="linha-flex"><span class="cor-amostra" data-cor="${c.cor}"></span><strong>${c.nome}</strong></span></td>
        <td data-rotulo="Descrição" class="texto-2 pequeno">${c.descricao || "—"}</td><td data-rotulo="Materiais" class="num">${c.materiais_ativos} de ${c.materiais}</td>
        <td data-rotulo="Situação">${c.ativo ? html`<span class="badge sucesso">Ativa</span>` : html`<span class="badge">Inativa</span>`}</td>
        ${gerenciar ? html`<td class="col-acao"><button class="botao fantasma pequeno icone" data-editar-cat="${c.id}" aria-label="Editar ${c.nome}">${icone("editar")}</button></td>` : ""}</tr>`)}</tbody></table></div>`
      : vazio("Nenhuma categoria", "", "", "etiqueta"));
  }

  function formMaterial(m = {}) {
    const md = modal({ titulo: m.id ? `Editar ${m.codigo}` : "Novo material", largo: true,
      conteudo: html`<form id="f-m" class="form-grade" novalidate>
        <div class="campo"><label for="m-nome">Nome<span class="obrigatorio">*</span></label><input id="m-nome" name="nome" required maxlength="160" value="${m.nome || ""}" autofocus placeholder="Ex.: Luva de procedimento nitrílica M — caixa 100"></div>
        <div class="campo col-6"><label for="m-cat">Categoria<span class="obrigatorio">*</span></label><select id="m-cat" name="categoria_id" required>${opcoes(Object.fromEntries(categorias.filter((c) => c.ativo || c.id === m.categoria_id).map((c) => [c.id, c.nome])), m.categoria_id || "", { vazio: "Selecione…" })}</select></div>
        <div class="campo col-3"><label for="m-un">Unidade<span class="obrigatorio">*</span></label><select id="m-un" name="unidade">${opcoes(Object.fromEntries(Object.entries(estado.meta.rotulos.unidade).map(([k, v]) => [k, `${k} · ${v}`])), m.unidade || "UN")}</select></div>
        <div class="campo col-3"><label for="m-preco">Preço de referência</label><div class="entrada-prefixo"><span>R$</span><input id="m-preco" name="preco_referencia" inputmode="decimal" value="${m.preco_referencia ? formato.entradaDecimal(m.preco_referencia) : ""}"></div></div>
        <div class="campo"><label for="m-desc">Especificação</label><textarea id="m-desc" name="descricao" maxlength="1000">${m.descricao || ""}</textarea></div>
        ${m.id ? html`<label class="checkbox"><input type="checkbox" name="ativo" ${m.ativo ? html`checked` : ""}><span>Material ativo (disponível nas solicitações)</span></label>` : ""}
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="f-m">${icone("check")}Salvar</button>` });
    const form = md.el.querySelector("#f-m");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = dadosFormulario(form);
      if (!d.preco_referencia) d.preco_referencia = null;
      try { await comCarregamento(md.el.querySelector('[type="submit"]'), m.id ? api.patch(`/materiais/${m.id}`, d) : api.post("/materiais", d)); md.fechar(); toast("sucesso", "Material salvo"); await recarregarCategorias(); if (aba === "materiais") carregarMateriais(); }
      catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
  }

  function formCategoria(c = {}) {
    const md = modal({ titulo: c.id ? `Editar ${c.nome}` : "Nova categoria",
      conteudo: html`<form id="f-c" class="form-grade" novalidate>
        <div class="campo col-9"><label for="c-nome">Nome<span class="obrigatorio">*</span></label><input id="c-nome" name="nome" required maxlength="80" value="${c.nome || ""}" autofocus></div>
        <div class="campo col-3"><label for="c-cor">Cor</label><input id="c-cor" name="cor" type="color" value="${c.cor || "#2E5C88"}"></div>
        <div class="campo"><label for="c-desc">Descrição</label><textarea id="c-desc" name="descricao" maxlength="400">${c.descricao || ""}</textarea></div>
        ${c.id ? html`<label class="checkbox"><input type="checkbox" name="ativo" ${c.ativo ? html`checked` : ""}><span>Categoria ativa</span></label>` : ""}</form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="f-c">${icone("check")}Salvar</button>` });
    const form = md.el.querySelector("#f-c");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = dadosFormulario(form);
      d.cor = (d.cor || "").toUpperCase();
      try { await comCarregamento(md.el.querySelector('[type="submit"]'), c.id ? api.patch(`/categorias/${c.id}`, d) : api.post("/categorias", d)); md.fechar(); toast("sucesso", "Categoria salva"); await recarregarCategorias(); if (aba === "categorias") abaCategorias(); }
      catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
  }

  async function recarregarCategorias() { categorias = (await api.get("/categorias")).itens; desenharAbas(); }
  const trocar = () => (aba === "materiais" ? abaMateriais() : abaCategorias());
  on(raiz, "click", "[data-aba]", (e, b) => { aba = b.dataset.aba; desenharAbas(); trocar(); });
  on(corpo, "click", "[data-pagina]", (e, b) => { f.pagina = Number(b.dataset.pagina); carregarMateriais(); });
  on(corpo, "click", "[data-editar-mat]", (e, b) => formMaterial(materiais.find((m) => m.id === b.dataset.editarMat)));
  on(corpo, "click", "[data-editar-cat]", (e, b) => formCategoria(categorias.find((c) => c.id === b.dataset.editarCat)));
  raiz.querySelector("#novo-mat")?.addEventListener("click", () => formMaterial());
  raiz.querySelector("#nova-cat")?.addEventListener("click", () => formCategoria());
  desenharAbas();
  await trocar();
}
