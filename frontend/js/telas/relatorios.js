// Central de relatórios em PDF e CSV com filtros de período, setor e status.
import { api } from "../api.js";
import { estado } from "../estado.js";
import { html, renderizar, on } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { aviso, comCarregamento, formato, opcoes, opcoesSetores, toast, toastErro } from "../ui/componentes.js";

export async function montar({ raiz }) {
  const hoje = formato.hojeISO();
  const inicio = new Date();
  inicio.setMonth(inicio.getMonth() - 3);
  const ini = inicio.toISOString().slice(0, 10);
  const gestor = estado.usuario.papel === "gestor";
  const r = estado.meta.rotulos;

  const cartao = (id, titulo, descricao, ic, campos, botoes) => html`<section class="cartao" aria-labelledby="t-${id}">
    <div class="cartao-cabecalho"><h2 id="t-${id}" class="linha-flex">${icone(ic)}${titulo}</h2><span class="subtitulo">${descricao}</span></div>
    <form class="cartao-corpo form-grade" data-relatorio="${id}" novalidate>${campos}</form>
    <div class="cartao-rodape">${botoes}</div></section>`;
  const periodo = (id) => html`<div class="campo col-6"><label for="${id}-ini">De</label><input id="${id}-ini" type="date" name="inicio" value="${ini}" max="${hoje}"></div>
    <div class="campo col-6"><label for="${id}-fim">Até</label><input id="${id}-fim" type="date" name="fim" value="${hoje}"></div>`;
  const setor = (id) => (gestor ? "" : html`<div class="campo"><label for="${id}-setor">Setor</label><select id="${id}-setor" name="setor">${opcoesSetores(estado.meta.setores, "", { vazio: "Todos os setores" })}</select></div>`);

  renderizar(raiz, html`
    <div class="cabecalho-pagina"><div class="titulos"><h1>Relatórios</h1><p>Documentos institucionais com logotipo, código de verificação SHA-256 e registro em auditoria.</p></div></div>
    ${aviso("info", "Autenticidade", "Cada PDF traz no rodapé um código de verificação. A Administração pode confirmar sua emissão em Auditoria › Verificar relatório.")}
    <div class="grade-2">
      ${cartao("executivo", "Relatório executivo", "KPIs, SLAs, custos por setor, evolução mensal e fornecedores.", "relatorio",
        html`${periodo("ex")}${setor("ex")}`, html`<button class="botao" data-gerar="executivo">${icone("pdf")}Gerar PDF</button>`)}
      ${cartao("solicitacoes", "Solicitações", "Lista detalhada com status, SLA e valores (PDF ou planilha CSV).", "documento",
        html`${periodo("so")}${setor("so")}<div class="campo col-6"><label for="so-status">Status</label><select id="so-status" name="status">${opcoes(r.status_solicitacao, "", { vazio: "Todos" })}</select></div>
          <div class="campo col-6"><label for="so-sla">SLA</label><select id="so-sla" name="sla">${opcoes(r.sla_situacao, "", { vazio: "Todos" })}</select></div>`,
        html`<button class="botao secundario" data-gerar="solicitacoes-csv">${icone("planilha")}CSV</button><button class="botao" data-gerar="solicitacoes">${icone("pdf")}Gerar PDF</button>`)}
      ${cartao("servicos", "Agenda de serviços programados", "Serviços por período, categoria e situação, com destaque aos atrasados.", "agenda",
        html`${periodo("sv")}${setor("sv")}<div class="campo"><label for="sv-cat">Categoria</label><select id="sv-cat" name="categoria">${opcoes(r.categoria_servico, "", { vazio: "Todas" })}</select></div>`,
        html`<button class="botao" data-gerar="servicos">${icone("pdf")}Gerar PDF</button>`)}
    </div>`);

  const rotas = {
    executivo: ["executivo", "/painel/relatorio.pdf", "relatorio-executivo.pdf"],
    solicitacoes: ["solicitacoes", "/solicitacoes/relatorio.pdf", "relatorio-solicitacoes.pdf"],
    "solicitacoes-csv": ["solicitacoes", "/solicitacoes/exportar.csv", "solicitacoes.csv"],
    servicos: ["servicos", "/servicos/relatorio.pdf", "servicos-programados.pdf"],
  };
  on(raiz, "click", "[data-gerar]", async (e, b) => {
    const [formId, caminho, nome] = rotas[b.dataset.gerar];
    const form = raiz.querySelector(`[data-relatorio="${formId}"]`);
    const params = Object.fromEntries([...new FormData(form)].filter(([, v]) => v));
    if (params.inicio && params.fim && params.inicio > params.fim) { toast("alerta", "Período inválido", "A data inicial deve ser anterior à final."); return; }
    try {
      await comCarregamento(b, api.baixar(caminho, params, { nomePadrao: nome }));
      toast("sucesso", "Relatório gerado", "O download foi iniciado.");
    } catch (err) { toastErro(err); }
  });
}
