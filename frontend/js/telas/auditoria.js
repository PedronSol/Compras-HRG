// Trilha de auditoria (Administrador e Auditoria) e verificação de autenticidade de relatórios.
import { api } from "../api.js";
import { html, renderizar, on, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { aviso, cabecalho, formato, modal, opcoes, paginacao, toastErro, vazio, erroTela } from "../ui/componentes.js";

const NOMES_OPERACAO = {
  INSERT: "Criação", UPDATE: "Alteração", DELETE: "Exclusão", LOGIN: "Login", LOGOUT: "Logout", LOGIN_FALHA: "Falha de login",
  LOGIN_BLOQUEADO: "Login bloqueado", DOWNLOAD_ANEXO: "Download de anexo", RELATORIO_GERADO: "Relatório gerado",
  EXPORTACAO_CSV: "Exportação CSV", TROCA_SENHA: "Troca de senha", SENHA_REDEFINIDA_ADMIN: "Senha redefinida (admin)",
  USUARIO_APROVADO: "Usuário aprovado", USUARIO_REJEITADO: "Usuário rejeitado", USUARIO_ANONIMIZADO: "Anonimização (LGPD)",
  EXPORTACAO_DADOS_TITULAR: "Portabilidade (LGPD)", VERIFICACAO_ASSINATURA: "Verificação de assinatura",
  PARAMETRO_ALTERADO: "Parâmetro alterado", USUARIO_DESBLOQUEADO: "Usuário desbloqueado", SESSAO_ENCERRADA: "Sessão encerrada",
  TROCA_SENHA_FALHA: "Falha na troca de senha", CADASTRO_DUPLICADO: "Cadastro duplicado",
};
const OBJETOS = {
  "rg.solicitacoes": "Solicitações", "rg.solicitacao_itens": "Itens de solicitação", "rg.cotacoes": "Propostas", "rg.cotacao_itens": "Itens de proposta",
  "rg.pedidos": "Pedidos de compra", "rg.recebimentos": "Recebimentos", "rg.recebimento_itens": "Itens recebidos", "rg.anexos": "Documentos",
  "rg.assinaturas": "Assinaturas", "rg.usuarios": "Usuários", "rg.fornecedores": "Fornecedores", "rg.materiais": "Materiais",
  "rg.categorias": "Categorias", "rg.configuracoes": "Parâmetros", "rg.setores": "Setores", "rg.sessoes": "Sessões", relatorios: "Relatórios",
};

export async function montar({ raiz, consulta }) {
  const f = { tabela: consulta.tabela || "", operacao: consulta.operacao || "", registro: consulta.registro || "", inicio: consulta.inicio || "", fim: consulta.fim || "", pagina: 1 };
  let itens = [];
  let listas = null;
  renderizar(raiz, html`
    ${cabecalho({ titulo: "Auditoria", sub: "Registro imutável de todas as alterações e eventos de segurança do sistema",
      acoes: html`<button class="botao secundario" data-verificar>${icone("escudo")}Verificar relatório PDF</button>` })}
    <section class="cartao">
      <form class="barra-filtros" id="f-aud" role="search">
        <select class="entrada" id="a-tab" name="tabela" aria-label="Objeto"><option value="">Todos os objetos</option></select>
        <select class="entrada" id="a-op" name="operacao" aria-label="Operação"><option value="">Todas as operações</option></select>
        <input class="entrada mono" id="a-reg" name="registro" value="${f.registro}" placeholder="ID do registro" aria-label="ID do registro">
        <input class="entrada" id="a-ini" type="date" name="inicio" value="${f.inicio}" aria-label="De">
        <input class="entrada" id="a-fim" type="date" name="fim" value="${f.fim}" aria-label="Até">
      </form>
      <div id="lista-aud" aria-live="polite"></div>
    </section>`);
  const alvo = raiz.querySelector("#lista-aud");
  const form = raiz.querySelector("#f-aud");

  async function carregar() {
    try {
      const d = await api.get("/auditoria", { ...f, por_pagina: 50 });
      itens = d.itens;
      if (!listas) {
        listas = true;
        renderizar(form.tabela, html`<option value="">Todos os objetos</option>${opcoes(Object.fromEntries(d.tabelas.map((t) => [t, OBJETOS[t] || t])), f.tabela)}`);
        renderizar(form.operacao, html`<option value="">Todas as operações</option>${opcoes(Object.fromEntries(d.operacoes.map((o) => [o, NOMES_OPERACAO[o] || o])), f.operacao)}`);
      }
      if (!itens.length) { renderizar(alvo, vazio("Nenhum evento encontrado", "Ajuste os filtros.", "", "auditoria")); return; }
      renderizar(alvo, html`<div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Quando</th><th>Usuário</th><th>Operação</th><th>Objeto</th><th>Campos</th><th>IP</th><th class="col-acao"><span class="sr-only">Detalhes</span></th></tr></thead>
        <tbody>${itens.map((e, i) => html`<tr>
          <td data-rotulo="Quando" class="num">${formato.dataHora(e.ocorrido_em)}</td>
          <td data-rotulo="Usuário">${e.usuario_nome || html`<span class="texto-3">Sistema</span>`}</td>
          <td data-rotulo="Operação"><span class="badge ${e.operacao.includes("FALHA") || e.operacao.includes("BLOQUEADO") ? "perigo" : e.operacao === "DELETE" ? "alerta" : "contorno"}">${NOMES_OPERACAO[e.operacao] || e.operacao}</span></td>
          <td data-rotulo="Objeto">${OBJETOS[e.tabela] || e.tabela}${e.registro_id ? html`<br><small class="mono texto-3">${e.registro_id.slice(0, 13)}</small>` : ""}</td>
          <td data-rotulo="Campos" class="pequeno">${(e.campos_alterados || []).filter((c) => c !== "atualizado_em").join(", ") || "—"}</td>
          <td data-rotulo="IP" class="mono pequeno">${e.ip || "—"}</td>
          <td class="col-acao"><button class="botao fantasma pequeno" data-detalhe="${i}">${icone("olho")}Detalhes</button></td></tr>`)}</tbody></table></div>${paginacao(d)}`);
    } catch (e) { alvo.replaceChildren(erroTela(e, carregar)); }
  }

  on(alvo, "click", "[data-detalhe]", (ev, b) => {
    const e = itens[Number(b.dataset.detalhe)];
    modal({ titulo: `${NOMES_OPERACAO[e.operacao] || e.operacao} · ${OBJETOS[e.tabela] || e.tabela}`, largo: true,
      conteudo: html`<div class="pilha"><dl class="pares"><div><dt>Data/hora</dt><dd>${formato.dataHora(e.ocorrido_em)}</dd></div><div><dt>Usuário</dt><dd>${e.usuario_nome || "Sistema"}</dd></div><div><dt>IP</dt><dd>${e.ip || "—"}</dd></div><div><dt>Registro</dt><dd class="mono">${e.registro_id || "—"}</dd></div></dl>
        ${e.dados_antes ? html`<div><h3 class="pequeno texto-3">Antes</h3><pre class="json-dif">${JSON.stringify(e.dados_antes, null, 2)}</pre></div>` : ""}
        ${e.dados_depois ? html`<div><h3 class="pequeno texto-3">${e.dados_antes ? "Depois" : "Dados"}</h3><pre class="json-dif">${JSON.stringify(e.dados_depois, null, 2)}</pre></div>` : ""}</div>`,
      rodape: html`<button class="botao" data-fechar>Fechar</button>` });
  });
  on(alvo, "click", "[data-pagina]", (e, b) => { f.pagina = Number(b.dataset.pagina); carregar(); });
  form.addEventListener("input", debounce(() => {
    const d = new FormData(form);
    for (const k of ["tabela", "operacao", "registro", "inicio", "fim"]) f[k] = (d.get(k) || "").trim();
    f.pagina = 1;
    carregar();
  }, 300));
  raiz.querySelector("[data-verificar]").addEventListener("click", () => {
    const m = modal({ titulo: "Verificar autenticidade de relatório",
      conteudo: html`<form id="f-ver" class="pilha"><p class="texto-2 pequeno">Informe o código de verificação SHA-256 impresso no rodapé do PDF.</p>
        <div class="campo"><label for="v-cod">Código de verificação</label><input id="v-cod" name="codigo" class="mono" required pattern="[0-9a-fA-F]{64}" autofocus></div><div id="res-ver" aria-live="polite"></div></form>`,
      rodape: html`<button class="botao secundario" data-fechar>Fechar</button><button class="botao" type="submit" form="f-ver">Verificar</button>` });
    m.el.querySelector("#f-ver").addEventListener("submit", async (e) => {
      e.preventDefault();
      const codigo = e.target.codigo.value.trim().toLowerCase();
      try {
        const r = await api.get(`/auditoria/relatorios/${encodeURIComponent(codigo)}`);
        renderizar(m.el.querySelector("#res-ver"), r.autentico
          ? aviso("sucesso", "Relatório autêntico", `Emitido em ${formato.dataHora(r.emissao.ocorrido_em)} por ${r.emissao.usuario_nome || "—"} (IP ${r.emissao.ip || "—"}).`)
          : aviso("perigo", "Código não encontrado", "Este código não corresponde a nenhum relatório emitido pelo sistema."));
      } catch (err) { toastErro(err); }
    });
  });
  await carregar();
}
