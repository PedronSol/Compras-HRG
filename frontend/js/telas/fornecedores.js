// Fornecedores: cadastro, desempenho (pedidos, pontualidade, conformidade) e histórico.
import { api } from "../api.js";

import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, debounce, dadosFormulario, mostrarErrosCampos } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import {
  badgePedido, badgeStatus, cabecalho, carregandoBloco, comCarregamento, formato, modal, opcoes, paginacao, pode,
  toast, toastErro, vazio,
} from "../ui/componentes.js";

const UFS = "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ");

/** Formulário de cadastro/edição. Resolve com o fornecedor salvo (ou null). */
export function formularioFornecedor(f = {}) {
  return new Promise((resolve) => {
    let salvo = null;
    const m = modal({
      titulo: f.id ? "Editar fornecedor" : "Novo fornecedor", sub: "O CNPJ é validado pelos dígitos verificadores (numérico ou alfanumérico).", largo: true,
      conteudo: html`<form id="form-forn" class="form-grade" novalidate>
        <div class="campo col-8"><label for="f-razao">Razão social<span class="obrigatorio">*</span></label><input id="f-razao" name="razao_social" required maxlength="160" value="${f.razao_social || ""}" autofocus></div>
        <div class="campo col-4"><label for="f-cnpj">CNPJ<span class="obrigatorio">*</span></label><input id="f-cnpj" name="cnpj" required maxlength="20" value="${f.cnpj ? formato.cnpj(f.cnpj) : ""}" placeholder="00.000.000/0000-00" ${f.id ? html`readonly` : ""}></div>
        <div class="campo col-6"><label for="f-fantasia">Nome fantasia</label><input id="f-fantasia" name="nome_fantasia" maxlength="160" value="${f.nome_fantasia || ""}"></div>
        <div class="campo col-6"><label for="f-contato">Pessoa de contato</label><input id="f-contato" name="contato" maxlength="120" value="${f.contato || ""}"></div>
        <div class="campo col-6"><label for="f-email">E-mail comercial</label><input id="f-email" name="email" type="email" maxlength="254" value="${f.email || ""}"></div>
        <div class="campo col-6"><label for="f-tel">Telefone</label><input id="f-tel" name="telefone" type="tel" maxlength="30" value="${f.telefone || ""}"></div>
        <div class="campo col-8"><label for="f-cidade">Cidade</label><input id="f-cidade" name="cidade" maxlength="80" value="${f.cidade || ""}"></div>
        <div class="campo col-4"><label for="f-uf">UF</label><select id="f-uf" name="uf">${opcoes(Object.fromEntries(UFS.map((u) => [u, u])), f.uf || "RS", { vazio: "—" })}</select></div>
        <div class="campo"><label for="f-obs">Observações</label><textarea id="f-obs" name="observacoes" maxlength="1000">${f.observacoes || ""}</textarea></div>
        ${f.id ? html`<label class="checkbox"><input type="checkbox" name="ativo" ${f.ativo ? html`checked` : ""}><span>Fornecedor ativo (pode receber novas cotações)</span></label>` : ""}
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="form-forn">${icone("check")}Salvar fornecedor</button>`,
      aoFechar: () => resolve(salvo),
    });
    const form = m.el.querySelector("#form-forn");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const dados = dadosFormulario(form);
      if (f.id) delete dados.cnpj;
      try {
        salvo = await comCarregamento(m.el.querySelector('[type="submit"]'), f.id ? api.patch(`/fornecedores/${f.id}`, dados) : api.post("/fornecedores", dados));
        toast("sucesso", f.id ? "Fornecedor atualizado" : "Fornecedor cadastrado", salvo.nome_fantasia || salvo.razao_social);
        m.fechar();
      } catch (erro) { mostrarErrosCampos(form, erro.campos); toastErro(erro); }
    });
  });
}

function indicador(valor, sufixo = "%") {
  if (valor === null || valor === undefined) return html`<span class="texto-3">—</span>`;
  const tom = valor >= 90 ? "sucesso" : valor >= 70 ? "alerta" : "perigo";
  return html`<span class="badge ${tom}">${Math.round(valor)}${sufixo}</span>`;
}

async function abrirDetalhe(id, aoEditar) {
  const m = modal({ titulo: "Fornecedor", gaveta: true, conteudo: carregandoBloco(8) });
  try {
    const d = await api.get(`/fornecedores/${id}`);
    const f = d.fornecedor;
    m.el.querySelector("h2").firstChild.textContent = f.nome_fantasia || f.razao_social;
    renderizar(m.corpo, html`<div class="pilha">
      <div><p class="texto-2">${f.razao_social}</p><p class="mono texto-3">${formato.cnpj(f.cnpj)}</p>
        <div class="linha-flex">${f.ativo ? html`<span class="badge sucesso">${icone("check")}Ativo</span>` : html`<span class="badge">Inativo</span>`}${f.cidade ? html`<span class="badge contorno">${f.cidade}/${f.uf}</span>` : ""}</div></div>
      <div class="kpis compactos">
        <div class="kpi"><div class="kpi-topo">Valor contratado</div><div class="valor">${formato.moedaCompacta(f.valor_contratado)}</div></div>
        <div class="kpi"><div class="kpi-topo">Pedidos</div><div class="valor">${f.pedidos}</div></div>
        <div class="kpi"><div class="kpi-topo">Taxa de vitória</div><div class="valor">${f.propostas ? Math.round((100 * f.vencedoras) / f.propostas) + "%" : "—"}</div></div>
      </div>
      <dl class="pares lista">
        <div><dt>Pontualidade nas entregas</dt><dd>${indicador(f.pontualidade)}</dd></div>
        <div><dt>Recebimentos conformes</dt><dd>${indicador(f.conformidade)}</dd></div>
        <div><dt>Propostas enviadas</dt><dd>${f.propostas} (${f.vencedoras} vencedoras)</dd></div>
        <div><dt>Contato</dt><dd>${f.contato || "—"}</dd></div>
        <div><dt>E-mail</dt><dd>${f.email ? html`<a href="mailto:${f.email}" data-externo>${f.email}</a>` : "—"}</dd></div>
        <div><dt>Telefone</dt><dd>${f.telefone || "—"}</dd></div>
      </dl>
      ${f.observacoes ? html`<p class="texto-longo pequeno">${f.observacoes}</p>` : ""}
      <div><p class="grupo-titulo-secao">Pedidos recentes</p>
        ${d.pedidos.length ? html`<ul class="lista-itens cartao">${d.pedidos.slice(0, 8).map((p) => html`<li><a class="item-lista" href="/pedidos/${p.id}"><span class="corpo-item"><strong>${p.codigo} · ${p.solicitacao_titulo}</strong><small>${p.setor_nome} · ${formato.data(p.criado_em)}</small></span><span class="lado">${badgePedido(p.status)}<small class="num">${formato.moeda(p.valor_total)}</small></span></a></li>`)}</ul>` : html`<p class="texto-3 pequeno">Nenhum pedido emitido.</p>`}</div>
      <div><p class="grupo-titulo-secao">Últimas propostas</p>
        ${d.propostas.length ? html`<ul class="lista-itens cartao">${d.propostas.slice(0, 8).map((c) => html`<li><a class="item-lista" href="/solicitacoes/${c.solicitacao_id}?aba=cotacao"><span class="corpo-item"><strong>${c.solicitacao_codigo} · ${c.solicitacao_titulo}</strong><small>${formato.data(c.criado_em)} · prazo ${c.prazo_entrega_dias} dias</small></span><span class="lado">${c.selecionada ? html`<span class="badge sucesso">${icone("estrela")}Vencedora</span>` : badgeStatus(c.solicitacao_status)}<small class="num">${formato.moeda(c.valor_total)}</small></span></a></li>`)}</ul>` : html`<p class="texto-3 pequeno">Nenhuma proposta registrada.</p>`}</div>
    </div>`);
    if (pode("fornecedor.gerenciar")) {
      m.el.insertAdjacentHTML("beforeend", html`<div class="modal-rodape"><button class="botao secundario" data-editar>${icone("editar")}Editar cadastro</button></div>`.toString());
      m.el.querySelector("[data-editar]").addEventListener("click", async () => { m.fechar(); const s = await formularioFornecedor(f); if (s) aoEditar?.(); });
    }
  } catch (e) { renderizar(m.corpo, vazio("Não foi possível carregar", e.message, "", "alerta")); }
}

export async function montar({ raiz, consulta }) {
  const filtros = { q: consulta.q || "", ativos: consulta.ativos === "1", ordem: consulta.ordem || "valor", pagina: 1 };
  renderizar(raiz, html`
    ${cabecalho({ titulo: "Fornecedores", sub: "Cadastro, desempenho e histórico de propostas e pedidos",
      acoes: pode("fornecedor.gerenciar") ? html`<button class="botao" id="novo">${icone("mais")}Novo fornecedor</button>` : "" })}
    <section class="cartao">
      <form class="barra-filtros" id="filtros" role="search">
        <label class="busca"><span class="sr-only">Buscar</span>${icone("busca")}<input class="entrada" type="search" name="q" value="${filtros.q}" placeholder="Razão social, nome fantasia, cidade ou CNPJ"></label>
        <select class="entrada" name="ordem" aria-label="Ordenar">${opcoes({ valor: "Maior valor contratado", pedidos: "Mais pedidos", nome: "Nome" }, filtros.ordem)}</select>
        <label class="checkbox pequeno"><input type="checkbox" name="ativos" ${filtros.ativos ? html`checked` : ""}><span>Somente ativos</span></label>
      </form>
      <div id="lista">${carregandoBloco(6)}</div>
    </section>`);
  const lista = raiz.querySelector("#lista");
  const form = raiz.querySelector("#filtros");

  async function carregar() {
    atualizarConsulta({ q: filtros.q, ativos: filtros.ativos, ordem: filtros.ordem === "valor" ? "" : filtros.ordem });
    try {
      const r = await api.get("/fornecedores", { ...filtros, por_pagina: 50 });
      renderizar(lista, r.itens.length ? html`<div class="tabela-envoltorio"><table class="tabela responsiva">
        <thead><tr><th>Fornecedor</th><th>Cidade</th><th class="num">Pedidos</th><th class="num">Valor contratado</th><th>Pontualidade</th><th>Conformidade</th><th>Último pedido</th><th class="col-acao"><span class="sr-only">Ações</span></th></tr></thead>
        <tbody>${r.itens.map((f) => html`<tr data-fornecedor="${f.id}" tabindex="0">
          <td class="principal-td"><div class="principal-celula"><strong>${f.nome_fantasia || f.razao_social}</strong><small>${f.razao_social} · <span class="mono">${formato.cnpj(f.cnpj)}</span></small></div></td>
          <td data-rotulo="Cidade">${f.cidade ? `${f.cidade}/${f.uf}` : "—"}${f.ativo ? "" : html` <span class="badge">Inativo</span>`}</td>
          <td data-rotulo="Pedidos" class="num">${f.pedidos ?? "—"}</td>
          <td data-rotulo="Valor contratado" class="num"><strong>${formato.moeda(f.valor_contratado)}</strong></td>
          <td data-rotulo="Pontualidade">${indicador(f.pontualidade)}</td>
          <td data-rotulo="Conformidade">${indicador(f.conformidade)}</td>
          <td data-rotulo="Último pedido" class="texto-3 pequeno nowrap">${f.ultimo_pedido_em ? formato.relativo(f.ultimo_pedido_em) : "—"}</td>
          <td class="col-acao">${pode("fornecedor.gerenciar") ? html`<button class="botao fantasma pequeno icone" data-editar="${f.id}" aria-label="Editar ${f.razao_social}">${icone("editar")}</button>` : ""}</td>
        </tr>`)}</tbody></table></div>${paginacao(r)}`
        : vazio("Nenhum fornecedor encontrado", "Ajuste a busca ou cadastre um novo fornecedor.", "", "fornecedor"));
      lista._itens = r.itens;
    } catch (e) { renderizar(lista, vazio("Não foi possível carregar", e.message, "", "alerta")); }
  }
  const aplicar = debounce(() => { const d = Object.fromEntries(new FormData(form)); Object.assign(filtros, { q: d.q || "", ordem: d.ordem, ativos: d.ativos === "on" }); carregar(); }, 300);
  form.addEventListener("input", aplicar);
  form.addEventListener("submit", (e) => e.preventDefault());
  on(lista, "click", "[data-editar]", async (e, b) => { e.stopPropagation(); if (await formularioFornecedor(lista._itens.find((f) => f.id === b.dataset.editar))) carregar(); });
  on(lista, "click", "tr[data-fornecedor]", (e, tr) => { if (!e.target.closest("button")) abrirDetalhe(tr.dataset.fornecedor, carregar); });
  on(lista, "keydown", "tr[data-fornecedor]", (e, tr) => { if (e.key === "Enter") abrirDetalhe(tr.dataset.fornecedor, carregar); });
  raiz.querySelector("#novo")?.addEventListener("click", async () => { if (await formularioFornecedor()) carregar(); });
  await carregar();
  if (consulta.fornecedor) abrirDetalhe(consulta.fornecedor, carregar);
}

