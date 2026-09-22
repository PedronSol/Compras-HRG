// Cadastro de fornecedores (Compras e Administração) com validação de CNPJ numérico e alfanumérico.
import { api } from "../api.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, dadosFormulario, mostrarErrosCampos, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { comCarregamento, formato, modal, paginacao, toast, toastErro, vazio, erroTela } from "../ui/componentes.js";

export function cnpjValido(valor) {
  const d = String(valor || "").toUpperCase().replace(/[^0-9A-Z]/g, "");
  if (!/^[0-9A-Z]{12}\d{2}$/.test(d) || /^(.)\1{13}$/.test(d)) return false;
  const dv = (base, pesos) => {
    const soma = [...base].reduce((acc, c, i) => acc + (c.charCodeAt(0) - 48) * pesos[i], 0);
    const r = soma % 11;
    return r < 2 ? 0 : 11 - r;
  };
  const p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  return dv(d.slice(0, 12), p1) === Number(d[12]) && dv(d.slice(0, 13), [6, ...p1]) === Number(d[13]);
}

export async function montar({ raiz, consulta }) {
  const f = { q: consulta.q || "", pagina: Number(consulta.pagina) || 1 };
  renderizar(raiz, html`
    <div class="cabecalho-pagina"><div class="titulos"><h1>Fornecedores</h1><p>Empresas habilitadas a participar das cotações.</p></div>
      <button class="botao" data-novo>${icone("mais")}Novo fornecedor</button></div>
    <section class="cartao">
      <form class="barra-filtros" role="search" id="f-forn"><div class="campo largo"><label for="fo-q">Buscar</label>
        <input id="fo-q" type="search" name="q" value="${f.q}" placeholder="Razão social, nome fantasia ou CNPJ"></div></form>
      <div id="lista-forn" aria-live="polite"></div>
    </section>`);
  const alvo = raiz.querySelector("#lista-forn");

  async function carregar() {
    try {
      const d = await api.get("/fornecedores", { q: f.q, pagina: f.pagina, por_pagina: 50 });
      if (!d.itens.length) { renderizar(alvo, vazio("Nenhum fornecedor encontrado", "Cadastre fornecedores para lançar cotações.")); return; }
      renderizar(alvo, html`<div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Fornecedor</th><th>CNPJ</th><th>Contato</th><th class="direita">Cotações</th><th>Situação</th><th><span class="sr-only">Ações</span></th></tr></thead>
        <tbody>${d.itens.map((x) => html`<tr>
          <td class="principal" data-rotulo="Fornecedor"><strong>${x.razao_social}</strong>${x.nome_fantasia ? html`<span class="sub">${x.nome_fantasia}</span>` : ""}</td>
          <td data-rotulo="CNPJ" class="mono">${formato.cnpj(x.cnpj)}</td>
          <td data-rotulo="Contato">${x.contato || "—"}<span class="sub">${[x.email, x.telefone].filter(Boolean).join(" · ")}</span></td>
          <td data-rotulo="Cotações" class="direita num">${x.cotacoes}<span class="sub">${x.vencedoras} vencedora(s)</span></td>
          <td data-rotulo="Situação">${x.ativo ? html`<span class="badge sucesso"><span class="ponto"></span>Ativo</span>` : html`<span class="badge"><span class="ponto"></span>Inativo</span>`}</td>
          <td data-rotulo="Ações"><button class="botao fantasma pequeno" data-editar="${x.id}">${icone("editar")}Editar</button></td></tr>`)}</tbody></table></div>${paginacao(d)}`);
      alvo._itens = d.itens;
    } catch (e) { alvo.replaceChildren(erroTela(e, carregar)); }
  }

  function formulario(x = null) {
    const m = modal({
      titulo: x ? "Editar fornecedor" : "Novo fornecedor",
      conteudo: html`<form id="f-fornecedor" class="form-grade" novalidate>
        <div class="campo col-8"><label for="fn-razao">Razão social<span class="obrigatorio" aria-hidden="true">*</span></label><input id="fn-razao" name="razao_social" required maxlength="160" value="${x?.razao_social ?? ""}"></div>
        <div class="campo col-4"><label for="fn-cnpj">CNPJ<span class="obrigatorio" aria-hidden="true">*</span></label><input id="fn-cnpj" name="cnpj" class="mono" required maxlength="18" value="${x ? formato.cnpj(x.cnpj) : ""}" placeholder="00.000.000/0000-00" aria-describedby="fn-cnpj-ajuda">
          <p class="ajuda" id="fn-cnpj-ajuda">Aceita o CNPJ alfanumérico vigente desde 2026.</p></div>
        <div class="campo col-6"><label for="fn-fant">Nome fantasia</label><input id="fn-fant" name="nome_fantasia" maxlength="160" value="${x?.nome_fantasia ?? ""}"></div>
        <div class="campo col-6"><label for="fn-contato">Pessoa de contato</label><input id="fn-contato" name="contato" maxlength="120" value="${x?.contato ?? ""}"></div>
        <div class="campo col-6"><label for="fn-email">E-mail</label><input id="fn-email" type="email" name="email" value="${x?.email ?? ""}"></div>
        <div class="campo col-6"><label for="fn-tel">Telefone</label><input id="fn-tel" type="tel" name="telefone" maxlength="30" value="${x?.telefone ?? ""}"></div>
        ${x ? html`<label class="checkbox"><input type="checkbox" name="ativo" ${x.ativo ? html`checked` : ""}><span>Fornecedor ativo (disponível para novas cotações)</span></label>` : ""}
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="f-fornecedor">${icone("check")}Salvar</button>`,
    });
    const form = m.el.querySelector("#f-fornecedor");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = dadosFormulario(form);
      const erros = {};
      if ((d.razao_social || "").length < 2) erros.razao_social = "Informe a razão social";
      if (!cnpjValido(d.cnpj)) erros.cnpj = "CNPJ inválido (dígito verificador não confere)";
      mostrarErrosCampos(form, erros);
      if (Object.keys(erros).length) return;
      for (const k of ["nome_fantasia", "contato", "email", "telefone"]) if (!d[k]) d[k] = null;
      try {
        await comCarregamento(m.el.querySelector('button[type="submit"]'), x ? api.patch(`/fornecedores/${x.id}`, d) : api.post("/fornecedores", d));
        m.fechar();
        toast("sucesso", x ? "Fornecedor atualizado" : "Fornecedor cadastrado");
        carregar();
      } catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
  }

  raiz.querySelector("[data-novo]").addEventListener("click", () => formulario());
  on(alvo, "click", "[data-editar]", (e, b) => formulario(alvo._itens.find((x) => x.id === b.dataset.editar)));
  on(alvo, "click", "[data-pagina]", (e, b) => { f.pagina = Number(b.dataset.pagina); atualizarConsulta({ pagina: f.pagina }); carregar(); });
  const form = raiz.querySelector("#f-forn");
  form.addEventListener("submit", (e) => e.preventDefault());
  form.addEventListener("input", debounce(() => { f.q = form.q.value.trim(); f.pagina = 1; atualizarConsulta({ q: f.q, pagina: "" }); carregar(); }, 300));
  await carregar();
}
