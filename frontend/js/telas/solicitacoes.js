// Lista de solicitações com filtros, paginação, exportação e fila por perfil.
import { api } from "../api.js";
import { estado, ouvir, temPapel } from "../estado.js";
import { atualizarConsulta, navegar } from "../roteador.js";
import { html, renderizar, on, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { badgeSla, badgeStatus, badgeSetor, badgeUrgencia, comCarregamento, formato, opcoes, opcoesSetores, paginacao, toastErro, vazio, erroTela } from "../ui/componentes.js";

const FILA = {
  admin: { titulo: "Aprovações pendentes", texto: "Solicitações aguardando análise da Administração." },
  compras: { titulo: "Fila de cotações", texto: "Solicitações liberadas pela Administração e cotações em andamento." },
  gestor: { titulo: "Minhas pendências", texto: "Solicitações devolvidas para nova cotação que dependem de você." },
};

async function montarLista({ raiz, consulta, fila = false }) {
  const f = {
    q: consulta.q || "", status: consulta.status || "", setor: consulta.setor || "", urgencia: consulta.urgencia || "",
    sla: consulta.sla || "", tipo: consulta.tipo || "", inicio: consulta.inicio || "", fim: consulta.fim || "",
    ordem: consulta.ordem || (fila ? "sla" : "recentes"), pagina: Number(consulta.pagina) || 1,
  };
  const papel = estado.usuario.papel;
  const rotulos = estado.meta.rotulos;
  const cab = fila ? FILA[papel] : { titulo: "Solicitações", texto: papel === "gestor" ? `Solicitações do setor ${estado.usuario.setor_nome}.` : papel === "compras" ? "Solicitações liberadas pela Administração." : "Todas as solicitações da instituição." };

  renderizar(raiz, html`
    <div class="cabecalho-pagina">
      <div class="titulos"><h1>${cab.titulo}</h1><p>${cab.texto}</p></div>
      <div class="grupo-botoes">
        ${!fila ? html`<button class="botao secundario" data-exportar="csv">${icone("planilha")}CSV</button>
          <button class="botao secundario" data-exportar="pdf">${icone("pdf")}PDF</button>` : ""}
        ${temPapel("gestor") ? html`<a class="botao" href="/solicitacoes/nova">${icone("mais")}Nova solicitação</a>` : ""}
      </div>
    </div>
    <section class="cartao">
      ${!fila ? html`<form class="barra-filtros" id="filtros" role="search" aria-label="Filtrar solicitações">
        <div class="campo largo"><label for="f-q">Buscar</label><input id="f-q" type="search" name="q" value="${f.q}" placeholder="Código, título, gestor ou termo da descrição"></div>
        <button type="button" class="botao secundario pequeno alternar-filtros" data-alternar-filtros aria-expanded="false">${icone("filtro")}Filtros</button>
        <div class="campo"><label for="f-status">Status</label><select id="f-status" name="status">${opcoes(rotulos.status_solicitacao, f.status, { vazio: "Todos" })}</select></div>
        ${papel !== "gestor" ? html`<div class="campo"><label for="f-setor">Setor</label><select id="f-setor" name="setor">${opcoesSetores(estado.meta.setores, f.setor, { vazio: "Todos", somenteOperacionais: true })}</select></div>` : ""}
        <div class="campo"><label for="f-urg">Urgência</label><select id="f-urg" name="urgencia">${opcoes(rotulos.urgencia, f.urgencia, { vazio: "Todas" })}</select></div>
        <div class="campo"><label for="f-sla">SLA</label><select id="f-sla" name="sla">${opcoes(rotulos.sla_situacao, f.sla, { vazio: "Todos" })}</select></div>
        <div class="campo"><label for="f-ini">Abertura de</label><input id="f-ini" type="date" name="inicio" value="${f.inicio}"></div>
        <div class="campo"><label for="f-fim">até</label><input id="f-fim" type="date" name="fim" value="${f.fim}"></div>
        <div class="campo"><label for="f-ordem">Ordenar por</label><select id="f-ordem" name="ordem">${opcoes({ recentes: "Mais recentes", antigas: "Mais antigas", sla: "Prazo de SLA", urgencia: "Urgência", valor: "Maior valor" }, f.ordem)}</select></div>
        <button type="button" class="botao fantasma pequeno" data-limpar>${icone("fechar")}Limpar</button>
      </form>` : ""}
      <div id="resultado" aria-live="polite"></div>
    </section>`);

  const alvo = raiz.querySelector("#resultado");
  const form = raiz.querySelector("#filtros");
  let controlador;

  const parametros = () => ({ ...f, fila: fila || undefined, por_pagina: 25 });

  async function carregar() {
    controlador?.abort();
    controlador = new AbortController();
    alvo.setAttribute("aria-busy", "true");
    try {
      const dados = await api.get("/solicitacoes", parametros(), { sinal: controlador.signal });
      desenhar(dados);
    } catch (e) {
      if (e.name !== "AbortError") alvo.replaceChildren(erroTela(e, carregar));
    } finally {
      alvo.removeAttribute("aria-busy");
    }
  }

  function desenhar(dados) {
    if (!dados.itens.length) {
      renderizar(alvo, vazio(fila ? "Nada pendente por aqui" : "Nenhuma solicitação encontrada",
        fila ? "Quando houver solicitações aguardando sua ação, elas aparecerão aqui." : "Ajuste os filtros ou crie uma nova solicitação."));
      return;
    }
    renderizar(alvo, html`<div class="tabela-envoltorio"><table class="tabela responsiva">
      <caption class="sr-only">${cab.titulo}: ${dados.total} registro(s)</caption>
      <thead><tr><th scope="col">Solicitação</th><th scope="col">Setor</th><th scope="col">Urgência</th><th scope="col">Status</th><th scope="col">SLA</th><th scope="col" class="direita">Valor</th><th scope="col">Abertura</th></tr></thead>
      <tbody>${dados.itens.map((s) => html`<tr class="clicavel" data-href="/solicitacoes/${s.id}">
        <td class="principal" data-rotulo="Solicitação"><a class="titulo-linha" href="/solicitacoes/${s.id}">${s.titulo}</a>
          <span class="sub"><span class="mono">${s.codigo}</span> · ${estado.meta.rotulos.tipo_solicitacao[s.tipo]} · ${s.gestor_nome}${s.rodada_cotacao > 1 ? ` · ${s.rodada_cotacao}ª rodada` : ""}</span></td>
        <td data-rotulo="Setor">${badgeSetor(s.setor_codigo, s.setor_nome, s.setor_cor)}</td>
        <td data-rotulo="Urgência">${badgeUrgencia(s.urgencia)}</td>
        <td data-rotulo="Status">${badgeStatus(s.status)}</td>
        <td data-rotulo="SLA">${badgeSla(s.sla_situacao, s.sla_horas_restantes)}<span class="sub">${["dentro_prazo", "alerta", "estourado"].includes(s.sla_situacao) ? formato.horasRestantes(s.sla_horas_restantes) : formato.dataHora(s.sla_prazo_limite)}</span></td>
        <td data-rotulo="Valor" class="direita num">${s.valor_final_aprovado ? html`<strong>${formato.moeda(s.valor_final_aprovado)}</strong><span class="sub">homologado</span>` : html`${formato.moeda(s.valor_estimado)}<span class="sub">estimado</span>`}</td>
        <td data-rotulo="Abertura"><time datetime="${s.criado_em}">${formato.data(s.criado_em)}</time><span class="sub">${formato.relativo(s.criado_em)}</span></td>
      </tr>`)}</tbody></table></div>${paginacao(dados)}`);
  }

  on(alvo, "click", "tr[data-href]", (e, tr) => { if (!e.target.closest("a")) navegar(tr.dataset.href); });
  on(alvo, "click", "[data-pagina]", (e, b) => {
    f.pagina = Number(b.dataset.pagina);
    atualizarConsulta({ pagina: f.pagina > 1 ? f.pagina : "" });
    carregar();
    raiz.scrollIntoView({ block: "start" });
  });

  if (form) {
    const aplicar = debounce(() => {
      const d = new FormData(form);
      for (const chave of ["q", "status", "setor", "urgencia", "sla", "inicio", "fim", "ordem"]) f[chave] = (d.get(chave) || "").trim();
      f.pagina = 1;
      atualizarConsulta({ ...f, pagina: "" });
      carregar();
    }, 300);
    form.addEventListener("input", aplicar);
    form.addEventListener("submit", (e) => e.preventDefault());
    form.querySelector("[data-limpar]").addEventListener("click", () => { form.reset(); form.querySelectorAll("input").forEach((i) => { i.value = ""; }); form.querySelectorAll("select").forEach((s) => { s.selectedIndex = 0; }); aplicar(); });
  }
  on(raiz, "click", "[data-exportar]", (e, b) => {
    const tipo = b.dataset.exportar;
    const caminho = tipo === "csv" ? "/solicitacoes/exportar.csv" : "/solicitacoes/relatorio.pdf";
    comCarregamento(b, api.baixar(caminho, parametros(), { nomePadrao: `solicitacoes.${tipo}` })).catch(toastErro);
  });

  await carregar();
  const recarregar = debounce(carregar, 800);
  const desligar = [
    ouvir("evento", (ev) => { if (ev.tabela === "solicitacoes") recarregar(); }),
    ouvir("consulta-periodica", recarregar),
  ];
  return { desmontar: () => { controlador?.abort(); desligar.forEach((fn) => fn()); } };
}

export const telas = {
  fila: (ctx) => montarLista({ ...ctx, fila: true }),
};
export const montar = (ctx) => montarLista(ctx);
