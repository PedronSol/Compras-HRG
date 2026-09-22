// Abertura de solicitação pelo gestor, com anexos (até 3), OCR e assinatura eletrônica.
import { api } from "../api.js";
import { estado } from "../estado.js";
import { navegar } from "../roteador.js";
import { html, renderizar, dadosFormulario, mostrarErrosCampos } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { aviso, comCarregamento, opcoes, toast } from "../ui/componentes.js";
import { ativarUpload, zonaUpload } from "../ui/upload.js";

export async function montar({ raiz }) {
  const r = estado.meta.rotulos;
  const sla = estado.meta.sla_dias;
  const u = estado.usuario;
  renderizar(raiz, html`
    <nav class="migalhas" aria-label="Trilha"><a href="/solicitacoes">Solicitações</a><span aria-hidden="true">›</span><span>Nova</span></nav>
    <div class="cabecalho-pagina"><div class="titulos"><h1>Nova solicitação</h1>
      <p>Setor <strong>${u.setor_nome}</strong> · a solicitação seguirá para análise da Administração e, se aprovada, para o setor de Compras.</p></div></div>
    <form id="form-nova" class="layout-detalhe" novalidate>
      <div class="pilha">
        <section class="cartao"><div class="cartao-cabecalho"><h2>Dados da solicitação</h2></div>
          <div class="cartao-corpo form-grade">
            <fieldset class="campo" data-campo="tipo"><legend class="rotulo">Tipo<span class="obrigatorio" aria-hidden="true">*</span></legend>
              <div class="segmentado">${Object.entries(r.tipo_solicitacao).map(([v, t], i) => html`<label><input type="radio" name="tipo" value="${v}" ${i === 0 ? html`checked` : ""}><span>${t}</span></label>`)}</div></fieldset>
            <div class="campo"><label for="titulo">Título<span class="obrigatorio" aria-hidden="true">*</span></label>
              <input id="titulo" name="titulo" required minlength="5" maxlength="160" placeholder="Ex.: Aquisição de monitores multiparamétricos"></div>
            <div class="campo"><label for="descricao">Descrição detalhada<span class="obrigatorio" aria-hidden="true">*</span></label>
              <textarea id="descricao" name="descricao" required minlength="10" maxlength="5000" placeholder="Itens, quantidades, especificações técnicas, local de uso…"></textarea></div>
            <div class="campo"><label for="justificativa">Justificativa<span class="obrigatorio" aria-hidden="true">*</span></label>
              <textarea id="justificativa" name="justificativa" required minlength="20" maxlength="5000" aria-describedby="just-ajuda just-contador" placeholder="Por que esta contratação é necessária? Qual o impacto assistencial ou operacional?"></textarea>
              <p class="ajuda" id="just-ajuda">Mínimo de 20 caracteres. Uma boa justificativa acelera a análise.</p>
              <div class="contador-caracteres insuficiente" id="just-contador" aria-live="polite">0/20 caracteres mínimos</div></div>
            <div class="campo col-6"><label for="valor_estimado">Valor estimado (R$)</label>
              <input id="valor_estimado" name="valor_estimado" inputmode="decimal" placeholder="0,00" autocomplete="off"></div>
            <div class="campo col-6"><label for="tipo_documento">Tipo dos anexos</label>
              <select id="tipo_documento" name="tipo_documento">${opcoes({ orcamento: "Orçamento", nota_fiscal: "Nota fiscal", laudo: "Laudo / certificado", outro: "Outro" }, "orcamento")}</select></div>
          </div></section>
        <section class="cartao"><div class="cartao-cabecalho"><h2>Orçamentos e documentos</h2></div>
          <div class="cartao-corpo">${zonaUpload({ max: estado.meta.limites.max_anexos, rotulo: "Anexos (opcional, até 3)", ajuda: "Os dados de CNPJ, valores, datas e prazos serão extraídos automaticamente por OCR." })}</div></section>
      </div>
      <aside class="pilha">
        <section class="cartao"><div class="cartao-cabecalho"><h2>Urgência e SLA</h2></div>
          <div class="cartao-corpo pilha-sm">
            <fieldset data-campo="urgencia"><legend class="sr-only">Urgência</legend>
              ${Object.entries(r.urgencia).map(([v, t]) => html`<label class="checkbox"><input type="radio" name="urgencia" value="${v}" ${v === "normal" ? html`checked` : ""}>
                <span><strong>${t}</strong><br><span class="pequeno texto-3">Prazo de ${sla[v]} dias corridos para conclusão</span></span></label>`)}
            </fieldset>
            <p class="pequeno texto-3">A Administração pode reclassificar a urgência mediante justificativa.</p>
          </div></section>
        <section class="cartao"><div class="cartao-cabecalho"><h2>Assinatura eletrônica</h2></div>
          <div class="cartao-corpo pilha-sm">
            ${aviso("info", "Registro de autoria", "Ao enviar, sua assinatura será registrada com data/hora, IP de origem e hash SHA-256 do conteúdo.")}
            <div class="campo" data-campo="ciente"><label class="checkbox"><input type="checkbox" name="ciente" required>
              <span>Declaro que as informações são verdadeiras e assino eletronicamente esta solicitação.</span></label></div>
            <button type="submit" class="botao bloco">${icone("assinatura")}Assinar e enviar</button>
            <a class="botao secundario bloco" href="/solicitacoes">Cancelar</a>
          </div></section>
      </aside>
    </form>`);

  const form = raiz.querySelector("#form-nova");
  const upload = ativarUpload(form, { max: estado.meta.limites.max_anexos });
  const just = form.querySelector("#justificativa");
  const contador = form.querySelector("#just-contador");
  just.addEventListener("input", () => {
    const n = just.value.trim().length;
    contador.textContent = n >= 20 ? `${n} caracteres` : `${n}/20 caracteres mínimos`;
    contador.classList.toggle("insuficiente", n < 20);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = dadosFormulario(form);
    const erros = {};
    if ((d.titulo || "").length < 5) erros.titulo = "Informe um título com ao menos 5 caracteres";
    if ((d.descricao || "").length < 10) erros.descricao = "Descreva a solicitação (mínimo 10 caracteres)";
    if ((d.justificativa || "").length < 20) erros.justificativa = "A justificativa deve ter no mínimo 20 caracteres";
    if (d.valor_estimado && !/^\d{1,3}(\.?\d{3})*(,\d{1,2})?$|^\d+([.,]\d{1,2})?$/.test(d.valor_estimado)) erros.valor_estimado = "Valor inválido (ex.: 12.500,00)";
    if (!d.ciente) erros.ciente = "Confirme a assinatura eletrônica";
    mostrarErrosCampos(form, erros);
    if (Object.keys(erros).length) return;
    const fd = new FormData();
    for (const campo of ["tipo", "titulo", "descricao", "justificativa", "urgencia", "valor_estimado", "tipo_documento"]) {
      if (d[campo]) fd.append(campo, d[campo]);
    }
    upload.arquivos().forEach((a) => fd.append("arquivos", a, a.name));
    try {
      const r2 = await comCarregamento(form.querySelector('button[type="submit"]'), api.enviarFormulario("/solicitacoes", fd));
      toast("sucesso", `Solicitação ${r2.solicitacao.codigo} enviada`, "Assinada eletronicamente e encaminhada à Administração.");
      navegar(`/solicitacoes/${r2.solicitacao.id}`, { substituir: true });
    } catch (erro) {
      toast("erro", "Não foi possível enviar", erro.message);
      mostrarErrosCampos(form, erro.campos);
    }
  });
}
