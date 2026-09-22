// Painel executivo: KPIs, SLA, custos, setores, evolução e exportação em PDF.
import { api } from "../api.js";
import { estado, ouvir, rotulo, temPapel } from "../estado.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { badgeSla, badgeStatus, badgeSetor, badgeServico, comCarregamento, formato, opcoesSetores, toastErro, erroTela } from "../ui/componentes.js";
import { barrasHorizontais, linhas, colunas, tabelaDados, ativarGraficos } from "../ui/graficos.js";

function periodoPadrao(consulta) {
  const fim = consulta.fim || formato.hojeISO();
  const d = new Date(fim + "T12:00:00");
  d.setMonth(d.getMonth() - 6);
  return { inicio: consulta.inicio || d.toISOString().slice(0, 10), fim, setor: consulta.setor || "" };
}

export async function montar({ raiz, consulta }) {
  const filtros = periodoPadrao(consulta);
  const u = estado.usuario;
  renderizar(raiz, html`
    <div class="cabecalho-pagina">
      <div class="titulos"><h1>Painel executivo</h1>
        <p>Olá, ${u.nome.split(" ")[0]}. ${u.papel === "gestor" ? html`Indicadores do setor <strong>${u.setor_nome}</strong>.` : "Visão consolidada das solicitações, SLAs e serviços."}</p></div>
      <div class="grupo-botoes">
        ${temPapel("gestor") ? html`<a class="botao" href="/solicitacoes/nova">${icone("mais")}Nova solicitação</a>` : ""}
        <button class="botao secundario" data-pdf>${icone("pdf")}Exportar PDF</button>
      </div>
    </div>
    <form class="cartao barra-filtros" id="filtros-painel" role="search" aria-label="Filtros do painel">
      <div class="campo"><label for="f-inicio">De</label><input id="f-inicio" type="date" name="inicio" value="${filtros.inicio}" max="${formato.hojeISO()}"></div>
      <div class="campo"><label for="f-fim">Até</label><input id="f-fim" type="date" name="fim" value="${filtros.fim}"></div>
      ${u.papel !== "gestor" ? html`<div class="campo"><label for="f-setor">Setor</label><select id="f-setor" name="setor">${opcoesSetores(estado.meta.setores, filtros.setor, { vazio: "Todos os setores" })}</select></div>` : ""}
      <div class="grupo-botoes">
        ${[["30", "30 dias"], ["90", "90 dias"], ["365", "12 meses"]].map(([d, r]) => html`<button type="button" class="chip" data-rapido="${d}">${r}</button>`)}
      </div>
    </form>
    <div id="painel-conteudo" class="pilha" aria-live="polite"></div>`);

  const alvo = raiz.querySelector("#painel-conteudo");
  const form = raiz.querySelector("#filtros-painel");
  let controlador;

  async function carregar() {
    controlador?.abort();
    controlador = new AbortController();
    alvo.setAttribute("aria-busy", "true");
    try {
      const dados = await api.get("/painel", filtros, { sinal: controlador.signal });
      desenhar(dados);
    } catch (e) {
      if (e.name !== "AbortError") alvo.replaceChildren(erroTela(e, carregar));
    } finally {
      alvo.removeAttribute("aria-busy");
    }
  }

  function desenhar(d) {
    const k = d.kpis;
    const qs = (extra) => new URLSearchParams({ ...(filtros.setor ? { setor: filtros.setor } : {}), ...extra }).toString();
    renderizar(alvo, html`
      <section class="kpis" aria-label="Indicadores principais">
        <div class="cartao kpi destaque"><span class="rotulo">${icone("moeda")}Valor homologado no período</span>
          <span class="valor">${formato.moeda(k.valor_aprovado)}</span>
          <span class="detalhe">${k.aprovadas} solicitação(ões) · economia de ${formato.moeda(k.economia)} sobre o estimado</span></div>
        <div class="cartao kpi"><span class="rotulo">${icone("documento")}Solicitações abertas no período</span><span class="valor">${formato.numero(k.total)}</span>
          <span class="detalhe">${k.em_andamento} em andamento · ${k.rejeitadas} rejeitadas/canceladas</span></div>
        <div class="cartao kpi"><span class="rotulo">${icone("check_circulo")}Cumprimento de SLA</span><span class="valor">${formato.percentual(k.sla_cumprimento)}</span>
          <span class="detalhe">Das solicitações concluídas no período</span></div>
        <div class="cartao kpi"><span class="rotulo">${icone("ampulheta")}Ciclo médio</span>
          <span class="valor">${k.ciclo_medio_dias === null ? "—" : `${k.ciclo_medio_dias.toFixed(1).replace(".", ",")} dias`}</span>
          <span class="detalhe">Da abertura à decisão final</span></div>
      </section>

      <div class="grade-2">
        <section class="cartao" aria-labelledby="t-sla">
          <div class="cartao-cabecalho"><h2 id="t-sla">SLA das solicitações em aberto</h2><span class="badge contorno">Situação atual</span></div>
          <div class="cartao-corpo pilha">
            <div class="sla-resumo">
              <a class="sla-item dentro" href="/solicitacoes?${qs({ sla: "dentro_prazo" })}"><span class="n">${k.sla_dentro}</span><span class="r">${icone("check_circulo")}Dentro do prazo</span></a>
              <a class="sla-item alerta" href="/solicitacoes?${qs({ sla: "alerta" })}"><span class="n">${k.sla_alerta}</span><span class="r">${icone("relogio")}Alerta (&lt; 24h)</span></a>
              <a class="sla-item estourado" href="/solicitacoes?${qs({ sla: "estourado" })}"><span class="n">${k.sla_estourado}</span><span class="r">${icone("alerta")}Estourado</span></a>
            </div>
            <p class="pequeno texto-3">Prazos: Imediato ${estado.meta.sla_dias.imediato} dias · Urgente ${estado.meta.sla_dias.urgente} dias · Normal ${estado.meta.sla_dias.normal} dias.</p>
            <h3 class="pequeno texto-3">Prazos mais próximos</h3>
            ${d.criticas.length ? html`<ul class="lista-simples">${d.criticas.map((s) => html`<li><a class="linha-link" href="/solicitacoes/${s.id}">
                <span class="quebra"><strong class="t">${s.codigo}</strong> · ${s.titulo}<br><span class="minusculo texto-3">${s.setor_nome} · ${formato.horasRestantes(s.sla_horas_restantes)}</span></span>
                <span class="espacador"></span>${badgeSla(s.sla_situacao, s.sla_horas_restantes)}</a></li>`)}</ul>`
              : html`<p class="texto-3 pequeno">Nenhuma solicitação em aberto.</p>`}
          </div>
        </section>

        <section class="cartao" aria-labelledby="t-fluxo">
          <div class="cartao-cabecalho"><h2 id="t-fluxo">Etapas do fluxo</h2><span class="subtitulo">Solicitações abertas no período, por status</span></div>
          <div class="cartao-corpo pilha">
            ${barrasHorizontais(d.por_status.map((s) => ({ rotulo: rotulo("status_solicitacao", s.status), valor: s.quantidade, href: `/solicitacoes?${qs({ status: s.status })}` })), { link: true })}
            ${tabelaDados(["Status", "Quantidade"], d.por_status.map((s) => [rotulo("status_solicitacao", s.status), s.quantidade]))}
            <h3 class="pequeno texto-3">Por urgência</h3>
            ${barrasHorizontais(d.por_urgencia.map((s) => ({ rotulo: rotulo("urgencia", s.urgencia), valor: s.quantidade })))}
          </div>
        </section>
      </div>

      <section class="cartao" aria-labelledby="t-evolucao">
        <div class="cartao-cabecalho"><h2 id="t-evolucao">Evolução mensal</h2><span class="subtitulo">Solicitações abertas e homologadas por mês</span></div>
        <div class="cartao-corpo">
          ${linhas({ categorias: d.por_mes.map((m) => m.mes), titulo: "Solicitações abertas e homologadas por mês",
            series: [{ nome: "Abertas", valores: d.por_mes.map((m) => m.abertas) }, { nome: "Homologadas", valores: d.por_mes.map((m) => m.homologadas) }] })}
          ${tabelaDados(["Mês", "Abertas", "Homologadas", "Valor homologado"], d.por_mes.map((m) => [m.mes, m.abertas, m.homologadas, formato.moeda(m.valor_aprovado)]))}
        </div>
      </section>

      <div class="grade-2">
        <section class="cartao" aria-labelledby="t-custos">
          <div class="cartao-cabecalho"><h2 id="t-custos">Custos homologados por mês</h2></div>
          <div class="cartao-corpo">${colunas({ categorias: d.por_mes.map((m) => m.mes), valores: d.por_mes.map((m) => m.valor_aprovado), formatar: formato.moeda, titulo: "Valor homologado por mês" })}</div>
        </section>
        <section class="cartao" aria-labelledby="t-setores">
          <div class="cartao-cabecalho"><h2 id="t-setores">Distribuição por setor</h2><span class="subtitulo">Quantidade de solicitações no período</span></div>
          <div class="cartao-corpo pilha">
            ${barrasHorizontais(d.por_setor.map((s) => ({ rotulo: s.setor_nome, valor: s.quantidade, cor: s.setor_cor, href: `/solicitacoes?setor=${s.setor_codigo}` })), { link: true })}
            ${tabelaDados(["Setor", "Solicitações", "Em andamento", "Homologadas", "Valor homologado", "SLA estourado"],
              d.por_setor.map((s) => [s.setor_nome, s.quantidade, s.em_andamento, s.aprovadas, formato.moeda(s.valor_aprovado), s.sla_estourado]))}
          </div>
        </section>
      </div>

      <div class="grade-2">
        <section class="cartao" aria-labelledby="t-servicos">
          <div class="cartao-cabecalho"><h2 id="t-servicos">Serviços programados</h2><a class="botao fantasma pequeno" href="/servicos">Abrir agenda${icone("seta_dir")}</a></div>
          <div class="cartao-corpo pilha">
            <div class="sla-resumo">
              <div class="sla-item"><span class="n">${d.servicos.agendados}</span><span class="r">${icone("agenda")}Agendados</span></div>
              <div class="sla-item dentro"><span class="n">${d.servicos.concluidos}</span><span class="r">${icone("check_circulo")}Concluídos</span></div>
              <div class="sla-item estourado"><span class="n">${d.servicos.atrasados}</span><span class="r">${icone("alerta")}Atrasados</span></div>
            </div>
            ${d.servicos.proximos.length ? html`<ul class="lista-simples">${d.servicos.proximos.map((s) => html`<li><a class="linha-link" href="/servicos?servico=${s.id}">
              <span class="quebra"><strong class="t">${s.titulo}</strong><br><span class="minusculo texto-3">${formato.data(s.data_programada)} · ${s.hora_inicio}–${s.hora_termino} · ${s.responsavel_executor}</span></span>
              <span class="espacador"></span>${badgeServico(s.situacao, s.atrasado)}</a></li>`)}</ul>` : html`<p class="texto-3 pequeno">Nenhum serviço pendente nos próximos 7 dias.</p>`}
          </div>
        </section>
        <section class="cartao" aria-labelledby="t-fornec">
          <div class="cartao-cabecalho"><h2 id="t-fornec">Principais fornecedores</h2><span class="subtitulo">Por valor homologado no período</span></div>
          <div class="cartao-corpo">
            ${barrasHorizontais(d.top_fornecedores.map((f) => ({ rotulo: f.razao_social, valor: f.valor })), { formatar: formato.moeda, vazioTexto: "Nenhuma homologação no período." })}
          </div>
        </section>
      </div>`);
    ativarGraficos(alvo);
  }

  const aplicar = debounce(() => {
    const dados = new FormData(form);
    filtros.inicio = dados.get("inicio") || filtros.inicio;
    filtros.fim = dados.get("fim") || filtros.fim;
    filtros.setor = dados.get("setor") || "";
    atualizarConsulta(filtros);
    carregar();
  }, 250);
  form.addEventListener("change", aplicar);
  on(form, "click", "[data-rapido]", (e, b) => {
    const fim = new Date();
    const ini = new Date();
    ini.setDate(ini.getDate() - Number(b.dataset.rapido));
    form.inicio.value = ini.toISOString().slice(0, 10);
    form.fim.value = fim.toISOString().slice(0, 10);
    aplicar();
  });
  raiz.querySelector("[data-pdf]").addEventListener("click", (e) => {
    comCarregamento(e.currentTarget, api.baixar("/painel/relatorio.pdf", filtros, { nomePadrao: "relatorio-executivo.pdf" })).catch(toastErro);
  });

  await carregar();
  const recarregar = debounce(carregar, 1500);
  const desligar = [
    ouvir("evento", (ev) => { if (["solicitacoes", "servicos_programados", "cotacoes"].includes(ev.tabela)) recarregar(); }),
    ouvir("consulta-periodica", recarregar),
  ];
  return { desmontar: () => { controlador?.abort(); desligar.forEach((f) => f()); } };
}

export { badgeStatus, badgeSetor };
