// Serviços programados: agenda mensal, lista por dia, filtros, cadastro, execução e laudos.
import { api } from "../api.js";
import { estado, ouvir, rotulo, temPapel } from "../estado.js";
import { atualizarConsulta } from "../roteador.js";
import { html, renderizar, on, dadosFormulario, mostrarErrosCampos, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { aviso, badgeServico, badgeSetor, comCarregamento, confirmar, formato, modal, opcoes, opcoesSetores, toast, toastErro, vazio, erroTela } from "../ui/componentes.js";
import { ativarUpload, zonaUpload } from "../ui/upload.js";
import { painelOcr } from "./solicitacao-detalhe.js";

const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
const DIAS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

function iso(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; }

export async function montar({ raiz, consulta }) {
  const hoje = new Date();
  let ref = consulta.mes ? new Date(`${consulta.mes}-01T12:00:00`) : new Date(hoje.getFullYear(), hoje.getMonth(), 1, 12);
  const f = { setor: consulta.setor || "", categoria: consulta.categoria || "", situacao: consulta.situacao || "", periodicidade: consulta.periodicidade || "", q: consulta.q || "", atrasados: consulta.atrasados === "1" };
  let visao = consulta.visao || (matchMedia("(max-width: 760px)").matches ? "lista" : "mes");
  let itens = [];
  const r = estado.meta.rotulos;
  const podeCriar = temPapel("admin", "gestor");

  renderizar(raiz, html`
    <div class="cabecalho-pagina">
      <div class="titulos"><h1>Serviços programados</h1><p>Manutenções preventivas, calibrações, higienizações, rondas e intervenções prediais.</p></div>
      <div class="grupo-botoes">
        <button class="botao secundario" data-pdf>${icone("pdf")}Agenda em PDF</button>
        ${podeCriar ? html`<button class="botao" data-novo>${icone("mais")}Programar serviço</button>` : ""}
      </div>
    </div>
    <section class="cartao">
      <form class="barra-filtros" id="filtros-servicos" role="search" aria-label="Filtrar serviços">
        <div class="campo largo"><label for="s-q">Buscar</label><input id="s-q" type="search" name="q" value="${f.q}" placeholder="Código, serviço, responsável, empresa ou local"></div>
        <button type="button" class="botao secundario pequeno alternar-filtros" data-alternar-filtros aria-expanded="false">${icone("filtro")}Filtros</button>
        ${estado.usuario.papel !== "gestor" ? html`<div class="campo"><label for="s-setor">Setor</label><select id="s-setor" name="setor">${opcoesSetores(estado.meta.setores, f.setor, { vazio: "Todos" })}</select></div>` : ""}
        <div class="campo"><label for="s-cat">Categoria</label><select id="s-cat" name="categoria">${opcoes(r.categoria_servico, f.categoria, { vazio: "Todas" })}</select></div>
        <div class="campo"><label for="s-sit">Situação</label><select id="s-sit" name="situacao">${opcoes(r.situacao_servico, f.situacao, { vazio: "Todas" })}</select></div>
        <div class="campo"><label for="s-per">Periodicidade</label><select id="s-per" name="periodicidade">${opcoes(r.periodicidade, f.periodicidade, { vazio: "Todas" })}</select></div>
        <label class="checkbox"><input type="checkbox" name="atrasados" ${f.atrasados ? html`checked` : ""}><span>Somente atrasados</span></label>
      </form>
      <div class="cartao-cabecalho">
        <div class="linha-flex"><button class="botao secundario pequeno icone" data-mes="-1" aria-label="Mês anterior">${icone("seta_esq")}</button>
          <h2 id="titulo-mes" aria-live="polite"></h2>
          <button class="botao secundario pequeno icone" data-mes="1" aria-label="Próximo mês">${icone("seta_dir")}</button>
          <button class="botao fantasma pequeno" data-hoje>Hoje</button></div>
        <div class="segmentado" role="radiogroup" aria-label="Modo de visualização">
          <label><input type="radio" name="visao" value="mes" ${visao === "mes" ? html`checked` : ""}><span>${icone("grade")} Mês</span></label>
          <label><input type="radio" name="visao" value="lista" ${visao === "lista" ? html`checked` : ""}><span>${icone("lista")} Lista</span></label>
        </div>
      </div>
      <div id="agenda" aria-live="polite"></div>
    </section>`);

  const alvo = raiz.querySelector("#agenda");
  const form = raiz.querySelector("#filtros-servicos");

  function intervalo() {
    const inicio = new Date(ref.getFullYear(), ref.getMonth(), 1, 12);
    const fim = new Date(ref.getFullYear(), ref.getMonth() + 1, 0, 12);
    return { inicio: iso(inicio), fim: iso(fim) };
  }

  async function carregar() {
    raiz.querySelector("#titulo-mes").textContent = `${MESES[ref.getMonth()]} de ${ref.getFullYear()}`;
    try {
      const dados = await api.get("/servicos", { ...intervalo(), ...f });
      itens = dados.itens;
      desenhar();
    } catch (e) { alvo.replaceChildren(erroTela(e, carregar)); }
  }

  function eventoMini(s) {
    return html`<button type="button" class="evento ${s.situacao} ${s.atrasado ? "atrasado" : ""}" data-cor="${s.setor_cor}" data-servico="${s.id}"
      aria-label="${s.hora_inicio} ${s.titulo} — ${rotulo("situacao_servico", s.situacao)}${s.atrasado ? " (atrasado)" : ""}">
      <span class="h">${s.hora_inicio}</span> <span class="t">${s.titulo}</span></button>`;
  }

  function desenhar() {
    const mobile = matchMedia("(max-width: 760px)").matches;
    if (visao === "mes" && !mobile) {
      const primeiro = new Date(ref.getFullYear(), ref.getMonth(), 1, 12);
      const inicio = new Date(primeiro);
      inicio.setDate(1 - primeiro.getDay());
      const porDia = Object.groupBy ? Object.groupBy(itens, (s) => s.data_programada) : itens.reduce((acc, s) => ((acc[s.data_programada] ||= []).push(s), acc), {});
      const celulas = [];
      for (let i = 0; i < 42; i++) {
        const d = new Date(inicio);
        d.setDate(inicio.getDate() + i);
        const chave = iso(d);
        const doDia = porDia[chave] || [];
        celulas.push(html`<div class="dia ${d.getMonth() !== ref.getMonth() ? "fora" : ""} ${chave === iso(hoje) ? "hoje" : ""}" role="gridcell" aria-label="${d.getDate()} de ${MESES[d.getMonth()]}: ${doDia.length} serviço(s)">
          <span class="numero">${d.getDate()}</span>${doDia.slice(0, 3).map(eventoMini)}
          ${doDia.length > 3 ? html`<button type="button" class="mais-eventos" data-dia="${chave}">+${doDia.length - 3} serviço(s)</button>` : ""}</div>`);
        if (i >= 34 && d.getMonth() !== ref.getMonth() && d.getDay() === 6) break;
      }
      renderizar(alvo, html`<div class="agenda-mes" role="grid" aria-label="Agenda mensal">${DIAS.map((d) => html`<div class="dia-semana" role="columnheader">${d}</div>`)}${celulas}</div>
        ${itens.length ? "" : html`<p class="cartao-corpo texto-3 centro">Nenhum serviço programado neste mês com os filtros atuais.</p>`}`);
    } else {
      desenharLista(itens);
    }
  }

  function desenharLista(lista) {
    if (!lista.length) {
      renderizar(alvo, vazio("Nenhum serviço neste período", "Ajuste os filtros ou programe um novo serviço."));
      return;
    }
    const dias = [...new Set(lista.map((s) => s.data_programada))];
    renderizar(alvo, html`<div class="agenda-lista">${dias.map((dia) => {
      const doDia = lista.filter((s) => s.data_programada === dia);
      const d = new Date(`${dia}T12:00:00`);
      return html`<section class="dia-grupo" aria-label="${formato.data(dia)}"><h3 class="dia-titulo ${dia === iso(hoje) ? "hoje" : ""}">${icone("agenda")}${DIAS[d.getDay()]}, ${formato.data(dia)}${dia === iso(hoje) ? " · Hoje" : ""}</h3>
        ${doDia.map((s) => html`<div class="servico-item" data-servico="${s.id}" data-cor="${s.setor_cor}" role="button" tabindex="0" aria-label="${s.titulo}, ${s.hora_inicio} às ${s.hora_termino}">
          <div class="horario">${s.hora_inicio}<small>até ${s.hora_termino}</small></div>
          <div class="quebra"><div class="tit">${s.titulo}</div><div class="sub">${rotulo("categoria_servico", s.categoria)} · ${s.setor_nome} · ${s.responsavel_executor}${s.empresa_terceirizada ? ` (${s.empresa_terceirizada})` : ""}${s.periodicidade !== "unica" ? ` · ${rotulo("periodicidade", s.periodicidade)}` : ""}</div></div>
          <div>${badgeServico(s.situacao, s.atrasado)}</div></div>`)}</section>`;
    })}</div>`);
  }

  async function abrirServico(servicoId) {
    let s;
    try { s = await api.get(`/servicos/${servicoId}`); } catch (e) { toastErro(e); return; }
    const m = modal({
      titulo: `${s.codigo} · ${s.titulo}`, largo: true,
      conteudo: html`<div class="pilha">
        <div class="linha-flex">${badgeServico(s.situacao, s.atrasado)}${badgeSetor(s.setor_codigo, s.setor_nome, s.setor_cor)}<span class="badge contorno">${rotulo("categoria_servico", s.categoria)}</span>
          ${s.periodicidade !== "unica" ? html`<span class="badge info">${icone("atualizar")}${rotulo("periodicidade", s.periodicidade)}</span>` : ""}</div>
        <dl class="definicoes">
          <div><dt>Data</dt><dd>${formato.data(s.data_programada)}</dd></div>
          <div><dt>Horário</dt><dd>${s.hora_inicio} às ${s.hora_termino}</dd></div>
          <div><dt>Responsável / executor</dt><dd>${s.responsavel_executor}</dd></div>
          <div><dt>Empresa terceirizada</dt><dd>${s.empresa_terceirizada || "—"}</dd></div>
          <div><dt>Local</dt><dd>${s.local || "—"}</dd></div>
          <div><dt>Programado por</dt><dd>${s.criado_por_nome}</dd></div>
          ${s.iniciado_em ? html`<div><dt>Iniciado em</dt><dd>${formato.dataHora(s.iniciado_em)}</dd></div>` : ""}
          ${s.concluido_em ? html`<div><dt>Concluído em</dt><dd>${formato.dataHora(s.concluido_em)}</dd></div>` : ""}
        </dl>
        ${s.descricao ? html`<div><h3 class="pequeno texto-3">Descrição</h3><p class="texto-longo">${s.descricao}</p></div>` : ""}
        ${s.observacoes_conclusao ? aviso("sucesso", "Registro de conclusão", s.observacoes_conclusao) : ""}
        ${s.motivo_cancelamento ? aviso("perigo", "Motivo do cancelamento", s.motivo_cancelamento) : ""}
        ${s.atrasado ? aviso("alerta", "Serviço atrasado", "O horário de término programado já passou e o serviço não foi concluído.") : ""}
        <div><h3 class="pequeno texto-3">Laudos e documentos</h3>
          ${s.anexos.length ? html`<ul class="lista-arquivos">${s.anexos.map((a) => html`<li class="arquivo bloco"><div class="linha-flex"><span class="icone-arquivo">${icone("documento")}</span>
            <span class="quebra"><span class="nome">${a.nome_original}</span><br><span class="meta">${rotulo("tipo_documento", a.tipo_documento)} · ${formato.tamanho(a.tamanho)} · ${a.enviado_por_nome}</span></span>
            <span class="acoes"><button class="botao fantasma pequeno icone" data-ver-anexo="${a.id}" aria-label="Visualizar">${icone("olho")}</button><button class="botao fantasma pequeno icone" data-baixar-anexo="${a.id}" aria-label="Baixar">${icone("download")}</button></span></div>${painelOcr(a)}</li>`)}</ul>`
            : html`<p class="pequeno texto-3">Nenhum documento.</p>`}</div>
      </div>`,
      rodape: s.pode_editar ? html`
        <button class="botao perigo" data-cancelar>${icone("x_circulo")}Cancelar</button>
        <button class="botao secundario" data-laudo>${icone("upload")}Anexar laudo</button>
        ${s.situacao === "agendado" ? html`<button class="botao secundario" data-editar>${icone("editar")}Reprogramar</button><button class="botao" data-iniciar>${icone("play")}Iniciar</button>` : ""}
        <button class="botao sucesso" data-concluir>${icone("check_circulo")}Concluir</button>` : html`<button class="botao secundario" data-fechar>Fechar</button>`,
    });
    const transicao = async (acao, corpo, botao, msg) => {
      try {
        await comCarregamento(botao, api.post(`/servicos/${s.id}/${acao}`, corpo));
        m.fechar();
        toast("sucesso", msg);
        carregar();
      } catch (e) { toastErro(e); }
    };
    on(m.el, "click", "[data-iniciar]", (e, b) => transicao("iniciar", {}, b, "Serviço iniciado"));
    on(m.el, "click", "[data-concluir]", async () => {
      const r2 = await confirmar({ titulo: "Concluir serviço", justificativa: "Registro da execução (resultado, pendências, peças trocadas)", minimo: 5, rotuloConfirmar: "Concluir", tom: "sucesso",
        mensagem: s.periodicidade !== "unica" ? `A próxima ocorrência (${rotulo("periodicidade", s.periodicidade).toLowerCase()}) será programada automaticamente.` : "" });
      if (!r2.confirmado) return;
      try { await api.post(`/servicos/${s.id}/concluir`, { observacoes: r2.texto }); m.fechar(); toast("sucesso", "Serviço concluído"); carregar(); } catch (e) { toastErro(e); }
    });
    on(m.el, "click", "[data-cancelar]", async () => {
      const r2 = await confirmar({ titulo: "Cancelar serviço", justificativa: "Motivo do cancelamento", minimo: 5, rotuloConfirmar: "Cancelar serviço", tom: "perigo" });
      if (!r2.confirmado) return;
      try { await api.post(`/servicos/${s.id}/cancelar`, { motivo: r2.texto }); m.fechar(); toast("sucesso", "Serviço cancelado"); carregar(); } catch (e) { toastErro(e); }
    });
    on(m.el, "click", "[data-editar]", () => { m.fechar(); formularioServico(s); });
    on(m.el, "click", "[data-laudo]", () => { m.fechar(); anexarLaudo(s); });
    on(m.el, "click", "[data-baixar-anexo]", (e, b) => api.baixar(`/anexos/${b.dataset.baixarAnexo}/arquivo`).catch(toastErro));
    on(m.el, "click", "[data-ver-anexo]", (e, b) => api.baixar(`/anexos/${b.dataset.verAnexo}/arquivo`, { inline: 1 }, { abrir: true }).catch(toastErro));
  }

  function anexarLaudo(s) {
    const m = modal({
      titulo: `Anexar documento · ${s.codigo}`,
      conteudo: html`<form id="f-laudo" class="pilha" novalidate>
        <div class="campo"><label for="l-tipo">Tipo</label><select id="l-tipo" name="tipo_documento">${opcoes({ laudo: "Laudo / certificado", nota_fiscal: "Nota fiscal", orcamento: "Orçamento", outro: "Outro" }, "laudo")}</select></div>
        ${zonaUpload({ id: "laudos", max: 5, rotulo: "Arquivos", ajuda: "Datas de calibração, equipamento e nº de série serão extraídos automaticamente por OCR." })}</form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="f-laudo">${icone("upload")}Enviar</button>`,
    });
    const form = m.el.querySelector("#f-laudo");
    const up = ativarUpload(form, { id: "laudos", max: 5 });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!up.arquivos().length) { toast("alerta", "Selecione ao menos um arquivo"); return; }
      const fd = new FormData();
      fd.append("tipo_documento", form.tipo_documento.value);
      up.arquivos().forEach((a) => fd.append("arquivos", a, a.name));
      try {
        await comCarregamento(m.el.querySelector('button[type="submit"]'), api.enviarFormulario(`/servicos/${s.id}/anexos`, fd));
        m.fechar();
        toast("sucesso", "Documento anexado");
        abrirServico(s.id);
      } catch (err) { toastErro(err); }
    });
  }

  function formularioServico(s = null) {
    const setores = estado.meta.setores;
    const gestor = estado.usuario.papel === "gestor";
    const m = modal({
      titulo: s ? `Reprogramar ${s.codigo}` : "Programar serviço", largo: true,
      conteudo: html`<form id="f-servico" class="form-grade" novalidate>
        <div class="campo"><label for="sv-titulo">Serviço<span class="obrigatorio" aria-hidden="true">*</span></label><input id="sv-titulo" name="titulo" required minlength="5" maxlength="160" value="${s?.titulo ?? ""}" placeholder="Ex.: Calibração de bombas de infusão"></div>
        <div class="campo col-6"><label for="sv-cat">Categoria<span class="obrigatorio" aria-hidden="true">*</span></label><select id="sv-cat" name="categoria">${opcoes(r.categoria_servico, s?.categoria || "manutencao_preventiva")}</select></div>
        <div class="campo col-6"><label for="sv-setor">Setor<span class="obrigatorio" aria-hidden="true">*</span></label><select id="sv-setor" name="setor_codigo" ${gestor || s ? html`disabled` : ""}>${opcoesSetores(setores, s?.setor_codigo || estado.usuario.setor_codigo, {})}</select></div>
        <div class="campo col-4"><label for="sv-data">Data<span class="obrigatorio" aria-hidden="true">*</span></label><input id="sv-data" type="date" name="data_programada" required value="${s?.data_programada ?? formato.hojeISO()}"></div>
        <div class="campo col-4"><label for="sv-ini">Início<span class="obrigatorio" aria-hidden="true">*</span></label><input id="sv-ini" type="time" name="hora_inicio" required value="${s?.hora_inicio ?? "08:00"}"></div>
        <div class="campo col-4"><label for="sv-fim">Término<span class="obrigatorio" aria-hidden="true">*</span></label><input id="sv-fim" type="time" name="hora_termino" required value="${s?.hora_termino ?? "10:00"}"></div>
        <div class="campo col-6"><label for="sv-resp">Responsável / executor<span class="obrigatorio" aria-hidden="true">*</span></label><input id="sv-resp" name="responsavel_executor" required minlength="3" maxlength="120" value="${s?.responsavel_executor ?? ""}"></div>
        <div class="campo col-6"><label for="sv-emp">Empresa terceirizada</label><input id="sv-emp" name="empresa_terceirizada" maxlength="160" value="${s?.empresa_terceirizada ?? ""}"></div>
        <div class="campo col-6"><label for="sv-local">Local</label><input id="sv-local" name="local" maxlength="160" value="${s?.local ?? ""}" placeholder="Ex.: UTI Adulto — leitos 1 a 10"></div>
        <div class="campo col-6"><label for="sv-per">Periodicidade</label><select id="sv-per" name="periodicidade">${opcoes(r.periodicidade, s?.periodicidade || "unica")}</select>
          <p class="ajuda">Ao concluir, a próxima ocorrência é criada automaticamente.</p></div>
        <div class="campo"><label for="sv-desc">Descrição / checklist</label><textarea id="sv-desc" name="descricao" maxlength="5000">${s?.descricao ?? ""}</textarea></div>
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="f-servico">${icone("check")}${s ? "Salvar" : "Programar"}</button>`,
    });
    const form = m.el.querySelector("#f-servico");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = dadosFormulario(form);
      if (!s) d.setor_codigo = form.setor_codigo.value;
      else delete d.setor_codigo;
      const erros = {};
      if ((d.titulo || "").length < 5) erros.titulo = "Mínimo de 5 caracteres";
      if (!d.data_programada) erros.data_programada = "Informe a data";
      if (d.hora_termino <= d.hora_inicio) erros.hora_termino = "O término deve ser posterior ao início";
      if ((d.responsavel_executor || "").length < 3) erros.responsavel_executor = "Informe o responsável";
      mostrarErrosCampos(form, erros);
      if (Object.keys(erros).length) return;
      try {
        const salvo = await comCarregamento(m.el.querySelector('button[type="submit"]'), s ? api.patch(`/servicos/${s.id}`, d) : api.post("/servicos", d));
        m.fechar();
        toast("sucesso", s ? "Serviço reprogramado" : `Serviço ${salvo.codigo} programado`);
        const data = new Date(`${salvo.data_programada}T12:00:00`);
        ref = new Date(data.getFullYear(), data.getMonth(), 1, 12);
        atualizarConsulta({ mes: iso(ref).slice(0, 7) });
        carregar();
      } catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
  }

  on(alvo, "click", "[data-servico]", (e, el) => abrirServico(el.dataset.servico));
  on(alvo, "keydown", ".servico-item", (e, el) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); abrirServico(el.dataset.servico); } });
  on(alvo, "click", "[data-dia]", (e, b) => {
    const lista = itens.filter((s) => s.data_programada === b.dataset.dia);
    const m = modal({ titulo: `Serviços de ${formato.data(b.dataset.dia)}`, conteudo: html`<div class="pilha-sm">${lista.map(eventoMini)}</div>` });
    on(m.el, "click", "[data-servico]", (ev, el) => { m.fechar(); abrirServico(el.dataset.servico); });
  });
  on(raiz, "click", "[data-mes]", (e, b) => {
    ref = new Date(ref.getFullYear(), ref.getMonth() + Number(b.dataset.mes), 1, 12);
    atualizarConsulta({ mes: iso(ref).slice(0, 7) });
    carregar();
  });
  on(raiz, "click", "[data-hoje]", () => { ref = new Date(hoje.getFullYear(), hoje.getMonth(), 1, 12); atualizarConsulta({ mes: "" }); carregar(); });
  raiz.querySelectorAll('input[name="visao"]').forEach((i) => i.addEventListener("change", () => { visao = i.value; atualizarConsulta({ visao }); desenhar(); }));
  raiz.querySelector("[data-novo]")?.addEventListener("click", () => formularioServico());
  raiz.querySelector("[data-pdf]").addEventListener("click", (e) => comCarregamento(e.currentTarget, api.baixar("/servicos/relatorio.pdf", { ...intervalo(), ...f }, { nomePadrao: "agenda-servicos.pdf" })).catch(toastErro));
  const aplicar = debounce(() => {
    const d = new FormData(form);
    for (const k of ["setor", "categoria", "situacao", "periodicidade", "q"]) f[k] = (d.get(k) || "").trim();
    f.atrasados = d.get("atrasados") === "on";
    atualizarConsulta({ ...f });
    carregar();
  }, 300);
  form.addEventListener("input", aplicar);
  form.addEventListener("submit", (e) => e.preventDefault());

  await carregar();
  if (consulta.servico) abrirServico(consulta.servico);
  const recarregar = debounce(carregar, 800);
  const aoRedimensionar = debounce(desenhar, 200);
  window.addEventListener("resize", aoRedimensionar);
  const desligar = [ouvir("evento", (ev) => { if (ev.tabela === "servicos_programados") recarregar(); }), ouvir("consulta-periodica", recarregar)];
  return { desmontar: () => { desligar.forEach((fn) => fn()); window.removeEventListener("resize", aoRedimensionar); } };
}
