// Detalhe da solicitação: workflow, ações por perfil, anexos com OCR, cotações, assinaturas e histórico.
import { api } from "../api.js";
import { estado, ouvir, rotulo } from "../estado.js";
import { html, renderizar, on, seguro, dadosFormulario, mostrarErrosCampos, debounce } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import {
  aviso, badgeSetor, badgeSla, badgeStatus, badgeUrgencia, comCarregamento, confirmar, formato, modal, opcoes,
  toast, toastErro, erroTela,
} from "../ui/componentes.js";
import { ativarUpload, zonaUpload } from "../ui/upload.js";

const CAMPOS_OCR = [
  ["tipo_documento", "Tipo identificado", (v) => rotulo("tipo_documento", v)],
  ["cnpj_emitente", "CNPJ do emitente"],
  ["razao_social", "Razão social"],
  ["numero_documento", "Número"],
  ["data_emissao", "Emissão", formato.data],
  ["valor_total", "Valor total", formato.moeda],
  ["prazo_entrega_dias", "Prazo de entrega", (v) => `${v} dias`],
  ["validade_dias", "Validade", (v) => `${v} dias`],
  ["validade_data", "Válido até", formato.data],
  ["condicoes_pagamento", "Pagamento"],
  ["chave_acesso", "Chave de acesso NF-e"],
  ["equipamento", "Equipamento"],
  ["numero_serie", "Nº de série"],
  ["patrimonio", "Patrimônio"],
  ["data_calibracao", "Data da calibração", formato.data],
  ["proxima_calibracao", "Próxima calibração", formato.data],
  ["resultado_laudo", "Resultado", (v) => (v === "conforme" ? "Conforme" : "Não conforme")],
];

function confianca(c) {
  const classe = c >= 0.8 ? "alta" : c >= 0.6 ? "media" : "baixa";
  return html`<span class="confianca ${classe}" title="Confiança da extração">${Math.round(c * 100)}%</span>`;
}

export function painelOcr(a) {
  if (a.ocr_status === "pendente" || a.ocr_status === "processando") {
    return html`<p class="minusculo texto-3 linha-flex">${icone("atualizar", "girando")}Extraindo dados do documento (OCR)…</p>`;
  }
  if (a.ocr_status === "falhou" || a.ocr_status === "nao_suportado") {
    return html`<p class="minusculo texto-3 linha-flex">${icone("alerta")}${a.ocr_erro || "Não foi possível extrair dados."}
      ${a.ocr_status === "falhou" ? html`<button type="button" class="botao fantasma pequeno" data-reprocessar="${a.id}">Tentar novamente</button>` : ""}</p>`;
  }
  const d = a.dados_ocr || {};
  const itens = CAMPOS_OCR.filter(([k]) => d[k]?.valor !== undefined && d[k]?.valor !== null);
  return html`<details class="ocr-painel"><summary>${icone("ocr")}Dados extraídos por OCR (${itens.length} campos)</summary>
    ${itens.length ? html`<dl class="ocr-campos">${itens.map(([k, r, fmt]) => html`<div><dt>${r}</dt><dd>${fmt ? fmt(d[k].valor) : d[k].valor}${confianca(d[k].confianca)}</dd></div>`)}</dl>`
      : html`<p class="cartao-corpo pequeno texto-3">Nenhum campo estruturado identificado.</p>`}
    ${(d.avisos || []).length ? html`<div class="cartao-corpo">${aviso("alerta", "Atenção", d.avisos.join(" "))}</div>` : ""}
  </details>`;
}

function etapas(s) {
  const st = s.status;
  const ordem = { aguardando_adm: 1, necessita_nova_cotacao: 1, rejeitado_adm: 1, aprovado_adm: 2, em_cotacao: 2, aprovado: 4, rejeitado_compras: 2, cancelado: 0 };
  const atual = ordem[st];
  const passo = (i, titulo, detalhe) => {
    let classe = "";
    if (st === "cancelado") classe = i === 0 ? "feita" : "";
    else if ((st === "rejeitado_adm" && i === 1) || (st === "rejeitado_compras" && i === 2)) classe = "recusada";
    else if (i < atual || st === "aprovado") classe = "feita";
    else if (i === atual) classe = "atual";
    const simbolo = classe === "feita" ? icone("check") : classe === "recusada" ? icone("fechar") : seguro(String(i + 1));
    return html`<li class="etapa ${classe}"><span class="bola">${simbolo}</span>${titulo}<small>${detalhe}</small></li>`;
  };
  return html`<ol class="etapas" aria-label="Etapas do fluxo de aprovação">
    ${passo(0, "Gestor", "Solicitação assinada")}
    ${passo(1, "Administração", st === "necessita_nova_cotacao" ? "Nova cotação solicitada" : "Análise de mérito")}
    ${passo(2, "Compras", st === "em_cotacao" ? "Cotação em andamento" : "Cotação e fornecedores")}
    ${passo(3, "Homologação", st === "aprovado" ? "Concluída" : "Assinatura final")}
  </ol>`;
}

function marcadorHistorico(h) {
  if (["aprovado", "aprovado_adm"].includes(h.status_para) && h.acao === "mudanca_status") return "sucesso";
  if (["rejeitado_adm", "rejeitado_compras", "cancelado"].includes(h.status_para) && h.acao === "mudanca_status") return "perigo";
  if (h.status_para === "necessita_nova_cotacao" || h.acao === "alteracao_urgencia") return "alerta";
  return "";
}

function tituloHistorico(h) {
  if (h.acao === "criacao") return "Solicitação criada e assinada";
  if (h.acao === "alteracao_urgencia") return "Urgência reclassificada";
  if (h.acao === "edicao") return "Conteúdo revisado";
  return `${rotulo("status_solicitacao", h.status_de)} → ${rotulo("status_solicitacao", h.status_para)}`;
}

export async function montar({ raiz, params }) {
  let dados = null;
  let modalAberto = false;
  const id = params.id;

  async function carregar() {
    try {
      dados = await api.get(`/solicitacoes/${id}`);
      desenhar();
    } catch (e) {
      raiz.replaceChildren(erroTela(e, carregar));
    }
  }

  function desenhar() {
    const { solicitacao: s, anexos, cotacoes, assinaturas, historico, acoes } = dados;
    document.title = `${s.codigo} · ${estado.meta.instituicao}`;
    const ativos = anexos.filter((a) => !a.removido_em);
    const removidos = anexos.filter((a) => a.removido_em);
    const pareceres = [
      ["info", "Parecer da Administração", s.justificativa_adm, ["aprovado_adm", "em_cotacao", "aprovado", "rejeitado_compras"].includes(s.status) ? "info" : "perigo"],
      ["alerta", "Nova cotação solicitada", s.status === "necessita_nova_cotacao" ? s.motivo_nova_cotacao : null],
      ["alerta", "Urgência reclassificada pela Administração", s.justificativa_urgencia],
      ["info", "Parecer de Compras", s.justificativa_compras, s.status === "rejeitado_compras" ? "perigo" : "sucesso"],
      ["perigo", "Motivo do cancelamento", s.motivo_cancelamento],
    ].filter((p) => p[2]);

    renderizar(raiz, html`
      <nav class="migalhas" aria-label="Trilha"><a href="/solicitacoes">Solicitações</a><span aria-hidden="true">›</span><span class="mono">${s.codigo}</span></nav>
      <div class="cabecalho-pagina">
        <div class="titulos"><h1>${s.titulo}</h1>
          <div class="linha-flex">${badgeStatus(s.status)}${badgeUrgencia(s.urgencia)}${badgeSetor(s.setor_codigo, s.setor_nome, s.setor_cor)}${badgeSla(s.sla_situacao, s.sla_horas_restantes)}
            <span class="pequeno texto-3"><span class="mono">${s.codigo}</span> · aberta ${formato.relativo(s.criado_em)} por ${s.gestor_nome}</span></div></div>
        <div class="grupo-botoes"><button class="botao secundario" data-dossie>${icone("pdf")}Dossiê em PDF</button></div>
      </div>

      <div class="layout-detalhe">
        <div class="pilha">
          <section class="cartao"><div class="cartao-corpo">${etapas(s)}</div></section>
          ${pareceres.map(([tom, titulo, texto, tomReal]) => aviso(tomReal || tom, titulo, texto))}

          <section class="cartao" aria-labelledby="t-dados"><div class="cartao-cabecalho"><h2 id="t-dados">Dados da solicitação</h2></div>
            <div class="cartao-corpo pilha">
              <dl class="definicoes">
                <div><dt>Tipo</dt><dd>${rotulo("tipo_solicitacao", s.tipo)}</dd></div>
                <div><dt>Valor estimado</dt><dd class="num">${formato.moeda(s.valor_estimado)}</dd></div>
                <div><dt>Valor homologado</dt><dd class="num">${s.valor_final_aprovado ? html`<strong>${formato.moeda(s.valor_final_aprovado)}</strong>` : "—"}</dd></div>
                <div><dt>Rodada de cotação</dt><dd>${s.rodada_cotacao}ª</dd></div>
                <div><dt>Comprador</dt><dd>${s.comprador_nome || "—"}</dd></div>
                <div><dt>Última atualização</dt><dd>${formato.dataHora(s.atualizado_em)}</dd></div>
              </dl>
              <div><h3 class="pequeno texto-3">Descrição</h3><p class="texto-longo">${s.descricao}</p></div>
              <div><h3 class="pequeno texto-3">Justificativa do gestor</h3><p class="texto-longo">${s.justificativa}</p></div>
            </div></section>

          <section class="cartao" aria-labelledby="t-anexos"><div class="cartao-cabecalho"><h2 id="t-anexos">Documentos</h2>
              ${acoes.includes("compras_cotacao") ? html`<button class="botao secundario pequeno" data-anexar-proposta>${icone("upload")}Anexar proposta</button>` : ""}
              ${estado.usuario.papel === "gestor" && s.status === "aguardando_adm" && ativos.filter((a) => a.origem === "solicitante").length < 3 ? html`<button class="botao secundario pequeno" data-anexar-gestor>${icone("upload")}Anexar documento</button>` : ""}</div>
            <div class="cartao-corpo">
              ${ativos.length ? html`<ul class="lista-arquivos">${ativos.map((a) => html`<li class="arquivo bloco">
                <div class="linha-flex"><span class="icone-arquivo">${icone(a.mime === "application/pdf" ? "pdf" : "documento")}</span>
                  <span class="quebra"><span class="nome">${a.nome_original}</span><br><span class="meta">${rotulo("tipo_documento", a.tipo_documento)} · ${a.origem === "compras" ? "Compras" : "Solicitante"} · ${formato.tamanho(a.tamanho)} · ${a.enviado_por_nome} · ${formato.dataHora(a.criado_em)}${a.rodada_cotacao > 1 ? ` · ${a.rodada_cotacao}ª rodada` : ""}</span></span>
                  <span class="acoes"><button class="botao fantasma pequeno icone" data-ver="${a.id}" aria-label="Visualizar ${a.nome_original}" title="Visualizar">${icone("olho")}</button>
                  <button class="botao fantasma pequeno icone" data-baixar="${a.id}" aria-label="Baixar ${a.nome_original}" title="Baixar">${icone("download")}</button></span></div>
                ${painelOcr(a)}
                <p class="mono-hash" title="SHA-256 do arquivo original">SHA-256 ${a.sha256}</p></li>`)}</ul>`
                : html`<p class="texto-3">Nenhum documento anexado.</p>`}
              ${removidos.length ? html`<details class="pequeno"><summary class="texto-3">Documentos substituídos (${removidos.length})</summary><ul class="lista-arquivos">${removidos.map((a) => html`<li class="arquivo removido"><span class="icone-arquivo">${icone("documento")}</span><span><span class="nome">${a.nome_original}</span><br><span class="meta">${a.rodada_cotacao}ª rodada · removido em ${formato.dataHora(a.removido_em)}</span></span><span class="acoes"><button class="botao fantasma pequeno icone" data-baixar="${a.id}" aria-label="Baixar ${a.nome_original}">${icone("download")}</button></span></li>`)}</ul></details>` : ""}
            </div></section>

          ${cotacoes.length || acoes.includes("compras_cotacao") ? html`<section class="cartao" aria-labelledby="t-cot"><div class="cartao-cabecalho"><h2 id="t-cot">Cotações</h2>
              ${acoes.includes("compras_cotacao") ? html`<button class="botao pequeno" data-nova-cotacao>${icone("mais")}Lançar cotação</button>` : ""}</div>
            ${cotacoes.length ? html`<div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Fornecedor</th><th class="direita">Valor</th><th>Prazo</th><th>Pagamento</th><th>Validade</th>${acoes.includes("compras_cotacao") ? html`<th><span class="sr-only">Ações</span></th>` : ""}</tr></thead>
              <tbody>${cotacoes.map((c, i) => html`<tr class="${c.selecionada ? "cotacao-vencedora" : ""}">
                <td class="principal" data-rotulo="Fornecedor"><strong>${c.razao_social}</strong>${c.selecionada ? html` <span class="badge sucesso">${icone("check")}Vencedora</span>` : i === 0 && cotacoes.length > 1 ? html` <span class="badge info">Menor preço</span>` : ""}
                  <span class="sub mono">${formato.cnpj(c.cnpj)}</span>${c.observacoes ? html`<span class="sub">${c.observacoes}</span>` : ""}</td>
                <td class="direita num" data-rotulo="Valor"><strong>${formato.moeda(c.valor)}</strong></td>
                <td data-rotulo="Prazo">${c.prazo_entrega_dias} dias</td>
                <td data-rotulo="Pagamento">${c.condicoes_pagamento || "—"}</td>
                <td data-rotulo="Validade">${formato.data(c.validade_proposta)}</td>
                ${acoes.includes("compras_cotacao") ? html`<td data-rotulo="Ações"><div class="grupo-botoes"><button class="botao fantasma pequeno icone" data-editar-cotacao="${c.id}" aria-label="Editar cotação de ${c.razao_social}">${icone("editar")}</button>
                  <button class="botao fantasma pequeno icone" data-excluir-cotacao="${c.id}" aria-label="Excluir cotação de ${c.razao_social}">${icone("lixeira")}</button></div></td>` : ""}
              </tr>`)}</tbody></table></div>` : html`<div class="cartao-corpo"><p class="texto-3">Nenhuma cotação lançada. Cadastre ao menos uma proposta para homologar.</p></div>`}
          </section>` : ""}

          <section class="cartao" aria-labelledby="t-hist"><div class="cartao-cabecalho"><h2 id="t-hist">Histórico</h2></div>
            <div class="cartao-corpo"><ol class="linha-tempo">${historico.map((h) => html`<li><span class="marcador ${marcadorHistorico(h)}"></span>
              <div class="quando"><time datetime="${h.criado_em}">${formato.dataHora(h.criado_em)}</time> · ${h.autor_nome || "Sistema"}${h.autor_papel ? ` (${rotulo("papel", h.autor_papel)})` : ""}</div>
              <div class="o-que">${tituloHistorico(h)}</div>${h.observacao ? html`<div class="obs">${h.observacao}</div>` : ""}</li>`)}</ol></div></section>
        </div>

        <aside class="pilha">
          <section class="cartao" aria-labelledby="t-acoes"><div class="cartao-cabecalho"><h2 id="t-acoes">Ações</h2></div>
            <div class="cartao-corpo acoes-fluxo">${botoesAcoes(acoes, cotacoes)}</div></section>
          <section class="cartao" aria-labelledby="t-sla"><div class="cartao-cabecalho"><h2 id="t-sla">Prazo (SLA)</h2></div>
            <div class="cartao-corpo pilha-sm">${badgeSla(s.sla_situacao, s.sla_horas_restantes)}
              <dl class="definicoes"><div><dt>Prazo limite</dt><dd>${formato.dataHora(s.sla_prazo_limite)}</dd></div>
              <div><dt>${s.sla_concluido_em ? "Concluída em" : "Tempo restante"}</dt><dd>${s.sla_concluido_em ? formato.dataHora(s.sla_concluido_em) : formato.horasRestantes(s.sla_horas_restantes)}</dd></div></dl>
              <p class="minusculo texto-3">Urgência ${rotulo("urgencia", s.urgencia)}: ${estado.meta.sla_dias[s.urgencia]} dias corridos a partir da abertura.</p></div></section>
          <section class="cartao" aria-labelledby="t-ass"><div class="cartao-cabecalho"><h2 id="t-ass">Assinaturas eletrônicas</h2></div>
            <div class="cartao-corpo">${assinaturas.map((a) => html`<div class="assinatura"><span class="selo">${icone("assinatura")}</span>
              <div class="quebra"><strong>${a.usuario_nome}</strong> <span class="minusculo texto-3">${rotulo("papel", a.usuario_papel)}</span><br>
              <span class="pequeno">${rotulo("acao_assinatura", a.acao)}</span><br>
              <span class="minusculo texto-3">${formato.dataHora(a.assinado_em)} · IP ${a.ip}</span>
              <p class="mono-hash" title="${a.algoritmo}">${a.hash_autenticidade}</p>
              <button class="botao fantasma pequeno" data-verificar="${a.id}">${icone("escudo")}Verificar autenticidade</button></div></div>`)}</div></section>
        </aside>
      </div>`);
  }

  function botoesAcoes(acoes, cotacoes) {
    if (!acoes.length) return html`<p class="pequeno texto-3">Nenhuma ação disponível para o seu perfil nesta etapa.</p>`;
    const b = {
      adm_aprovar: html`<button class="botao sucesso" data-acao="adm_aprovar">${icone("check_circulo")}Aprovar e liberar para Compras</button>`,
      adm_nova_cotacao: html`<button class="botao alerta" data-acao="adm_nova_cotacao">${icone("devolver")}Solicitar nova cotação</button>`,
      adm_rejeitar: html`<button class="botao perigo" data-acao="adm_rejeitar">${icone("x_circulo")}Rejeitar</button>`,
      adm_urgencia: html`<button class="botao secundario" data-acao="adm_urgencia">${icone("bandeira")}Alterar urgência</button>`,
      gestor_reenviar: html`<button class="botao" data-acao="gestor_reenviar">${icone("enviar")}Revisar e reenviar</button>`,
      gestor_cancelar: html`<button class="botao secundario" data-acao="gestor_cancelar">${icone("fechar")}Cancelar solicitação</button>`,
      compras_iniciar: html`<button class="botao" data-acao="compras_iniciar">${icone("play")}Iniciar cotação</button>`,
      compras_homologar: html`<button class="botao sucesso" data-acao="compras_homologar" ${cotacoes.length ? "" : seguro("disabled")}>${icone("assinatura")}Homologar</button>
        ${cotacoes.length ? "" : html`<p class="minusculo texto-3">Lance ao menos uma cotação para homologar.</p>`}`,
      compras_rejeitar: html`<button class="botao perigo" data-acao="compras_rejeitar">${icone("x_circulo")}Rejeitar</button>`,
    };
    return html`${acoes.filter((a) => b[a]).map((a) => b[a])}`;
  }

  async function executar(acao, corpo, botao) {
    const promessa = api.post(`/solicitacoes/${id}/acoes/${acao}`, { versao: dados.solicitacao.versao, ...corpo });
    dados = await (botao ? comCarregamento(botao, promessa) : promessa);
    desenhar();
  }

  async function acaoComTexto(acao, cfg, botao) {
    modalAberto = true;
    const r = await confirmar(cfg);
    modalAberto = false;
    if (!r.confirmado) return;
    try {
      await executar(acao, { texto: r.texto }, botao);
      toast("sucesso", cfg.sucesso);
    } catch (e) { toastErro(e); if (e.status === 409) carregar(); }
  }

  const acoesMap = {
    adm_aprovar: (b) => acaoComTexto("adm_aprovar", {
      titulo: "Aprovar solicitação", mensagem: "A solicitação será liberada para o setor de Compras e sua assinatura eletrônica será registrada.",
      justificativa: "Parecer da Administração (opcional)", rotuloConfirmar: "Aprovar e assinar", tom: "sucesso", sucesso: "Solicitação aprovada e liberada para Compras",
    }, b),
    adm_rejeitar: (b) => acaoComTexto("adm_rejeitar", {
      titulo: "Rejeitar solicitação", mensagem: "A solicitação será encerrada. Esta ação não pode ser desfeita.",
      justificativa: "Justificativa da rejeição", minimo: 10, rotuloConfirmar: "Rejeitar e assinar", tom: "perigo", sucesso: "Solicitação rejeitada",
    }, b),
    adm_nova_cotacao: (b) => acaoComTexto("adm_nova_cotacao", {
      titulo: "Solicitar nova cotação", mensagem: "A solicitação voltará ao gestor para anexar novos orçamentos.",
      justificativa: "Orientação ao gestor", minimo: 10, rotuloConfirmar: "Devolver ao gestor", tom: "alerta", sucesso: "Solicitação devolvida ao gestor",
    }, b),
    gestor_cancelar: (b) => acaoComTexto("gestor_cancelar", {
      titulo: "Cancelar solicitação", mensagem: "A solicitação será encerrada definitivamente.",
      justificativa: "Motivo do cancelamento", minimo: 10, rotuloConfirmar: "Cancelar solicitação", tom: "perigo", sucesso: "Solicitação cancelada",
    }, b),
    compras_rejeitar: (b) => acaoComTexto("compras_rejeitar", {
      titulo: "Rejeitar na etapa de Compras", mensagem: "A solicitação será encerrada com assinatura do setor de Compras.",
      justificativa: "Justificativa", minimo: 10, rotuloConfirmar: "Rejeitar e assinar", tom: "perigo", sucesso: "Solicitação rejeitada por Compras",
    }, b),
    compras_iniciar: async (b) => {
      const r = await confirmar({ titulo: "Iniciar cotação", mensagem: "Você será registrado como comprador responsável por esta solicitação.", rotuloConfirmar: "Iniciar cotação" });
      if (!r.confirmado) return;
      try { await executar("compras_iniciar", {}, b); toast("sucesso", "Cotação iniciada"); } catch (e) { toastErro(e); }
    },
    adm_urgencia: () => modalUrgencia(),
    gestor_reenviar: () => modalReenvio(),
    compras_homologar: () => modalHomologacao(),
  };

  function modalUrgencia() {
    const s = dados.solicitacao;
    modalAberto = true;
    const m = modal({
      titulo: "Alterar urgência",
      conteudo: html`<form id="f-urg" class="pilha" novalidate>
        <p class="texto-2">Urgência atual: <strong>${rotulo("urgencia", s.urgencia)}</strong>. O prazo de SLA será recalculado a partir da data de abertura.</p>
        <div class="campo"><label for="u-nova">Nova urgência</label><select id="u-nova" name="urgencia">${opcoes(
          Object.fromEntries(Object.entries(estado.meta.rotulos.urgencia).filter(([v]) => v !== s.urgencia).map(([v, r]) => [v, `${r} — ${estado.meta.sla_dias[v]} dias`])))}</select></div>
        <div class="campo"><label for="u-just">Justificativa administrativa<span class="obrigatorio" aria-hidden="true">*</span></label><textarea id="u-just" name="texto" minlength="10" required></textarea></div>
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="f-urg">Salvar alteração</button>`,
      aoFechar: () => { modalAberto = false; },
    });
    const form = m.el.querySelector("#f-urg");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = dadosFormulario(form);
      if ((d.texto || "").length < 10) { mostrarErrosCampos(form, { texto: "Mínimo de 10 caracteres" }); return; }
      try {
        await executar("adm_urgencia", d, m.el.querySelector('button[type="submit"]'));
        m.fechar();
        toast("sucesso", "Urgência alterada", "O SLA foi recalculado e o gestor foi notificado.");
      } catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
  }

  function modalReenvio() {
    const s = dados.solicitacao;
    const ativos = dados.anexos.filter((a) => !a.removido_em && a.origem === "solicitante");
    modalAberto = true;
    const m = modal({
      titulo: "Revisar e reenviar à Administração", largo: true,
      conteudo: html`<form id="f-reenvio" class="pilha" novalidate>
        ${aviso("alerta", "Orientação da Administração", s.motivo_nova_cotacao)}
        <div class="form-grade">
          <div class="campo"><label for="r-titulo">Título</label><input id="r-titulo" name="titulo" value="${s.titulo}" minlength="5" maxlength="160"></div>
          <div class="campo"><label for="r-desc">Descrição</label><textarea id="r-desc" name="descricao" maxlength="5000">${s.descricao}</textarea></div>
          <div class="campo"><label for="r-just">Justificativa</label><textarea id="r-just" name="justificativa" minlength="20" maxlength="5000">${s.justificativa}</textarea></div>
          <div class="campo col-6"><label for="r-valor">Valor estimado (R$)</label><input id="r-valor" name="valor_estimado" inputmode="decimal" value="${formato.entradaDecimal(s.valor_estimado)}"></div>
        </div>
        ${ativos.length ? html`<fieldset><legend>Anexos atuais — marque para substituir</legend><div class="pilha-sm">${ativos.map((a) => html`<label class="checkbox"><input type="checkbox" name="remover" value="${a.id}"><span>${a.nome_original} <span class="minusculo texto-3">(${formato.tamanho(a.tamanho)})</span></span></label>`)}</div></fieldset>` : ""}
        ${zonaUpload({ id: "novos", max: 3, rotulo: "Novos orçamentos", ajuda: "Máximo de 3 anexos ativos no total." })}
        <div class="campo"><label for="r-obs">Observação para a Administração</label><textarea id="r-obs" name="texto" maxlength="2000"></textarea></div>
        <label class="checkbox"><input type="checkbox" name="ciente" required><span>Assino eletronicamente o reenvio desta solicitação.</span></label>
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="f-reenvio">${icone("assinatura")}Assinar e reenviar</button>`,
      aoFechar: () => { modalAberto = false; },
    });
    const form = m.el.querySelector("#f-reenvio");
    const upload = ativarUpload(form, { id: "novos", max: 3 - ativos.length });
    form.addEventListener("change", (e) => {
      if (e.target.name === "remover") upload.definirMaximo(3 - ativos.length + form.querySelectorAll('input[name="remover"]:checked').length);
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!form.ciente.checked) { mostrarErrosCampos(form, { ciente: "Confirme a assinatura" }); return; }
      const fd = new FormData();
      fd.append("versao", s.versao);
      const mudou = (campo, valorAtual) => form[campo].value.trim() !== String(valorAtual ?? "").trim();
      if (mudou("titulo", s.titulo)) fd.append("titulo", form.titulo.value.trim());
      if (mudou("descricao", s.descricao)) fd.append("descricao", form.descricao.value.trim());
      if (mudou("justificativa", s.justificativa)) fd.append("justificativa", form.justificativa.value.trim());
      if (form.valor_estimado.value.trim() && mudou("valor_estimado", formato.entradaDecimal(s.valor_estimado))) fd.append("valor_estimado", form.valor_estimado.value.trim());
      const remover = [...form.querySelectorAll('input[name="remover"]:checked')].map((c) => c.value);
      if (remover.length) fd.append("remover_anexos", remover.join(","));
      if (form.texto.value.trim()) fd.append("texto", form.texto.value.trim());
      upload.arquivos().forEach((a) => fd.append("arquivos", a, a.name));
      try {
        dados = await comCarregamento(m.el.querySelector('button[type="submit"]'), api.enviarFormulario(`/solicitacoes/${id}/acoes/gestor_reenviar`, fd));
        m.fechar();
        desenhar();
        toast("sucesso", "Solicitação reenviada", "A Administração foi notificada.");
      } catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
  }

  function modalHomologacao() {
    const cot = dados.cotacoes;
    const menor = cot.reduce((a, b) => (Number(b.valor) < Number(a.valor) ? b : a), cot[0]);
    modalAberto = true;
    const m = modal({
      titulo: "Homologar solicitação", largo: true,
      conteudo: html`<form id="f-homolog" class="pilha" novalidate>
        <fieldset data-campo="cotacao_id"><legend>Cotação vencedora</legend><div class="pilha-sm">${cot.map((c) => html`<label class="checkbox arquivo">
          <input type="radio" name="cotacao_id" value="${c.id}" data-valor="${c.valor}" ${c.id === menor.id ? html`checked` : ""}>
          <span><strong>${c.razao_social}</strong> — ${formato.moeda(c.valor)} · ${c.prazo_entrega_dias} dias${c.id === menor.id ? html` <span class="badge info">Menor preço</span>` : ""}<br>
          <span class="minusculo texto-3 mono">${formato.cnpj(c.cnpj)}</span></span></label>`)}</div></fieldset>
        <div class="form-grade"><div class="campo col-6"><label for="h-valor">Valor final homologado (R$)</label><input id="h-valor" name="valor_final" inputmode="decimal" value="${formato.entradaDecimal(menor.valor)}"></div></div>
        <div class="campo"><label for="h-obs">Parecer de Compras</label><textarea id="h-obs" name="texto" maxlength="2000" placeholder="Critérios da escolha: preço, prazo, qualificação técnica…"></textarea></div>
        ${aviso("info", "Assinatura final", "A homologação registra sua assinatura eletrônica e encerra o fluxo com status Homologada.")}
        <label class="checkbox"><input type="checkbox" name="ciente" required><span>Confirmo a homologação e assino eletronicamente.</span></label>
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao sucesso" type="submit" form="f-homolog">${icone("assinatura")}Homologar e assinar</button>`,
      aoFechar: () => { modalAberto = false; },
    });
    const form = m.el.querySelector("#f-homolog");
    form.addEventListener("change", (e) => {
      if (e.target.name === "cotacao_id") form.valor_final.value = formato.entradaDecimal(e.target.dataset.valor);
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = dadosFormulario(form);
      if (!d.ciente) { mostrarErrosCampos(form, { ciente: "Confirme a assinatura" }); return; }
      try {
        await executar("compras_homologar", { cotacao_id: d.cotacao_id, valor_final: d.valor_final, texto: d.texto }, m.el.querySelector('button[type="submit"]'));
        m.fechar();
        toast("sucesso", "Solicitação homologada", "O gestor e a Administração foram notificados.");
      } catch (err) { mostrarErrosCampos(form, err.campos); toastErro(err); }
    });
  }

  async function modalCotacao(cotacao = null) {
    modalAberto = true;
    let fornecedores = [];
    try { fornecedores = (await api.get("/fornecedores", { ativos: 1, por_pagina: 200 })).itens; } catch (e) { toastErro(e); }
    const anexos = dados.anexos.filter((a) => !a.removido_em);
    const comOcr = anexos.filter((a) => a.ocr_status === "concluido" && a.dados_ocr);
    const m = modal({
      titulo: cotacao ? "Editar cotação" : "Lançar cotação", largo: true,
      conteudo: html`<form id="f-cot" class="pilha" novalidate>
        ${!cotacao && comOcr.length ? html`<div class="aviso info">${icone("ocr")}<div><strong>Preencher com dados do OCR</strong>
          <div class="linha-flex">${comOcr.map((a) => html`<button type="button" class="botao secundario pequeno" data-usar-ocr="${a.id}">${a.nome_original}</button>`)}</div></div></div>` : ""}
        <div class="form-grade">
          ${cotacao ? html`<div class="campo"><span class="rotulo">Fornecedor</span><p><strong>${cotacao.razao_social}</strong> · <span class="mono">${formato.cnpj(cotacao.cnpj)}</span></p></div>` : html`
          <div class="campo col-8"><label for="c-forn">Fornecedor<span class="obrigatorio" aria-hidden="true">*</span></label>
            <select id="c-forn" name="fornecedor_id">${opcoes(Object.fromEntries(fornecedores.map((f) => [f.id, `${f.razao_social} — ${formato.cnpj(f.cnpj)}`])), "", { vazio: "Selecione…" })}<option value="__novo">+ Cadastrar novo fornecedor</option></select></div>
          <div class="col-4"></div>
          <div class="form-grade oculto" data-novo-fornecedor>
            <div class="campo col-8"><label for="n-razao">Razão social<span class="obrigatorio" aria-hidden="true">*</span></label><input id="n-razao" name="razao_social" maxlength="160"></div>
            <div class="campo col-4"><label for="n-cnpj">CNPJ<span class="obrigatorio" aria-hidden="true">*</span></label><input id="n-cnpj" name="cnpj" maxlength="18" placeholder="00.000.000/0000-00" class="mono"></div>
            <div class="campo col-6"><label for="n-email">E-mail</label><input id="n-email" name="email" type="email"></div>
            <div class="campo col-6"><label for="n-tel">Telefone</label><input id="n-tel" name="telefone" type="tel"></div>
          </div>`}
          <div class="campo col-4"><label for="c-valor">Valor (R$)<span class="obrigatorio" aria-hidden="true">*</span></label><input id="c-valor" name="valor" inputmode="decimal" required value="${cotacao ? formato.entradaDecimal(cotacao.valor) : ""}"></div>
          <div class="campo col-4"><label for="c-prazo">Prazo de entrega (dias)<span class="obrigatorio" aria-hidden="true">*</span></label><input id="c-prazo" name="prazo_entrega_dias" type="number" min="0" max="3650" required value="${cotacao?.prazo_entrega_dias ?? ""}"></div>
          <div class="campo col-4"><label for="c-val">Validade da proposta</label><input id="c-val" name="validade_proposta" type="date" value="${cotacao?.validade_proposta ?? ""}"></div>
          <div class="campo col-6"><label for="c-pag">Condições de pagamento</label><input id="c-pag" name="condicoes_pagamento" maxlength="300" value="${cotacao?.condicoes_pagamento ?? ""}"></div>
          <div class="campo col-6"><label for="c-anexo">Documento da proposta</label><select id="c-anexo" name="anexo_id">${opcoes(Object.fromEntries(anexos.map((a) => [a.id, a.nome_original])), cotacao?.anexo_id || "", { vazio: "Nenhum" })}</select></div>
          <div class="campo"><label for="c-obs">Observações</label><textarea id="c-obs" name="observacoes" maxlength="2000">${cotacao?.observacoes ?? ""}</textarea></div>
        </div></form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="f-cot">${icone("check")}Salvar cotação</button>`,
      aoFechar: () => { modalAberto = false; },
    });
    const form = m.el.querySelector("#f-cot");
    const blocoNovo = form.querySelector("[data-novo-fornecedor]");
    form.fornecedor_id?.addEventListener("change", () => blocoNovo.classList.toggle("oculto", form.fornecedor_id.value !== "__novo"));
    on(form, "click", "[data-usar-ocr]", (e, b) => {
      const a = comOcr.find((x) => x.id === b.dataset.usarOcr);
      const d = a.dados_ocr;
      if (d.valor_total) form.valor.value = formato.entradaDecimal(d.valor_total.valor);
      if (d.prazo_entrega_dias) form.prazo_entrega_dias.value = d.prazo_entrega_dias.valor;
      if (d.condicoes_pagamento) form.condicoes_pagamento.value = d.condicoes_pagamento.valor;
      if (d.validade_data) form.validade_proposta.value = d.validade_data.valor;
      else if (d.validade_dias && d.data_emissao) {
        const base = new Date(d.data_emissao.valor + "T12:00:00");
        base.setDate(base.getDate() + Number(d.validade_dias.valor));
        form.validade_proposta.value = base.toISOString().slice(0, 10);
      }
      form.anexo_id.value = a.id;
      const cnpj = (d.cnpj_emitente?.valor || "").replace(/[^0-9A-Z]/gi, "").toUpperCase();
      const existente = fornecedores.find((f) => f.cnpj === cnpj);
      if (existente) {
        form.fornecedor_id.value = existente.id;
        blocoNovo.classList.add("oculto");
      } else if (cnpj) {
        form.fornecedor_id.value = "__novo";
        blocoNovo.classList.remove("oculto");
        form.cnpj.value = d.cnpj_emitente.valor;
        if (d.razao_social) form.razao_social.value = d.razao_social.valor;
        if (d.emails?.[0]) form.email.value = d.emails[0];
      }
      toast("info", "Campos preenchidos pelo OCR", "Confira os valores antes de salvar.");
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = dadosFormulario(form);
      const botao = m.el.querySelector('button[type="submit"]');
      try {
        await comCarregamento(botao, (async () => {
          const corpo = { valor: d.valor, prazo_entrega_dias: d.prazo_entrega_dias, condicoes_pagamento: d.condicoes_pagamento,
            validade_proposta: d.validade_proposta || null, observacoes: d.observacoes, anexo_id: d.anexo_id || null };
          if (cotacao) {
            dados = await api.patch(`/cotacoes/${cotacao.id}`, corpo);
          } else {
            let fornecedorId = d.fornecedor_id;
            if (fornecedorId === "__novo") {
              const f = await api.post("/fornecedores", { razao_social: d.razao_social, cnpj: d.cnpj, email: d.email || null, telefone: d.telefone || null });
              fornecedorId = f.id;
            }
            if (!fornecedorId) throw Object.assign(new Error("Selecione o fornecedor"), { campos: { fornecedor_id: "Selecione o fornecedor" } });
            dados = await api.post(`/solicitacoes/${id}/cotacoes`, { ...corpo, fornecedor_id: fornecedorId });
          }
        })());
        m.fechar();
        desenhar();
        toast("sucesso", cotacao ? "Cotação atualizada" : "Cotação lançada");
      } catch (err) { mostrarErrosCampos(form, err.campos || {}); toastErro(err); }
    });
  }

  async function anexar(origemCompras) {
    modalAberto = true;
    const m = modal({
      titulo: origemCompras ? "Anexar proposta de fornecedor" : "Anexar documento",
      conteudo: html`<form id="f-anexo" class="pilha" novalidate>
        <div class="campo"><label for="a-tipo">Tipo de documento</label><select id="a-tipo" name="tipo_documento">${opcoes(origemCompras
          ? { cotacao: "Proposta de cotação", orcamento: "Orçamento", nota_fiscal: "Nota fiscal", outro: "Outro" }
          : { orcamento: "Orçamento", nota_fiscal: "Nota fiscal", laudo: "Laudo / certificado", outro: "Outro" }, origemCompras ? "cotacao" : "orcamento")}</select></div>
        ${zonaUpload({ id: "docs", max: origemCompras ? 5 : 3 - dados.anexos.filter((a) => !a.removido_em && a.origem === "solicitante").length, rotulo: "Arquivos" })}
      </form>`,
      rodape: html`<button class="botao secundario" data-fechar>Cancelar</button><button class="botao" type="submit" form="f-anexo">${icone("upload")}Enviar</button>`,
      aoFechar: () => { modalAberto = false; },
    });
    const form = m.el.querySelector("#f-anexo");
    const up = ativarUpload(form, { id: "docs", max: origemCompras ? 5 : 3 });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!up.arquivos().length) { toast("alerta", "Selecione ao menos um arquivo"); return; }
      const fd = new FormData();
      fd.append("tipo_documento", form.tipo_documento.value);
      up.arquivos().forEach((a) => fd.append("arquivos", a, a.name));
      try {
        dados = await comCarregamento(m.el.querySelector('button[type="submit"]'), api.enviarFormulario(`/solicitacoes/${id}/anexos`, fd));
        m.fechar();
        desenhar();
        toast("sucesso", "Documento anexado", "O OCR será processado em instantes.");
      } catch (err) { toastErro(err); }
    });
  }

  async function verificarAssinatura(assinaturaId) {
    try {
      const v = await api.get(`/assinaturas/${assinaturaId}/verificar`);
      modal({
        titulo: "Verificação de assinatura",
        conteudo: html`<div class="pilha">
          ${v.registro_integro ? aviso("sucesso", "Assinatura autêntica", "O hash HMAC-SHA-256 confere com os dados registrados (usuário, data/hora, IP e conteúdo).")
            : aviso("perigo", "Assinatura inválida", "Os dados do registro não correspondem ao hash de autenticidade. Acione a segurança da informação.")}
          ${v.conteudo_inalterado_desde_assinatura ? aviso("info", "Conteúdo inalterado", "A solicitação não foi modificada desde esta assinatura.")
            : aviso("alerta", "Conteúdo evoluiu após a assinatura", "Houve etapas posteriores (ex.: cotações, decisões). O conteúdo original assinado está preservado no hash.")}
          <dl class="definicoes"><div><dt>Signatário</dt><dd>${v.usuario_nome}</dd></div><div><dt>Ação</dt><dd>${rotulo("acao_assinatura", v.acao)}</dd></div>
          <div><dt>Data/hora</dt><dd>${formato.dataHora(v.assinado_em)}</dd></div><div><dt>IP</dt><dd>${v.ip}</dd></div>
          <div><dt>Algoritmo</dt><dd>${v.algoritmo}</dd></div></dl>
          <p class="mono-hash">${v.hash_autenticidade}</p></div>`,
        rodape: html`<button class="botao" data-fechar>Fechar</button>`,
      });
    } catch (e) { toastErro(e); }
  }

  on(raiz, "click", "[data-acao]", (e, b) => acoesMap[b.dataset.acao]?.(b));
  on(raiz, "click", "[data-nova-cotacao]", () => modalCotacao());
  on(raiz, "click", "[data-editar-cotacao]", (e, b) => modalCotacao(dados.cotacoes.find((c) => c.id === b.dataset.editarCotacao)));
  on(raiz, "click", "[data-excluir-cotacao]", async (e, b) => {
    const c = dados.cotacoes.find((x) => x.id === b.dataset.excluirCotacao);
    const r = await confirmar({ titulo: "Excluir cotação", mensagem: `Remover a proposta de ${c.razao_social}?`, rotuloConfirmar: "Excluir", tom: "perigo" });
    if (!r.confirmado) return;
    try { dados = await api.delete(`/cotacoes/${c.id}`); desenhar(); toast("sucesso", "Cotação removida"); } catch (err) { toastErro(err); }
  });
  on(raiz, "click", "[data-anexar-proposta]", () => anexar(true));
  on(raiz, "click", "[data-anexar-gestor]", () => anexar(false));
  on(raiz, "click", "[data-baixar]", (e, b) => api.baixar(`/anexos/${b.dataset.baixar}/arquivo`).catch(toastErro));
  on(raiz, "click", "[data-ver]", (e, b) => api.baixar(`/anexos/${b.dataset.ver}/arquivo`, { inline: 1 }, { abrir: true }).catch(toastErro));
  on(raiz, "click", "[data-reprocessar]", async (e, b) => {
    try { await api.post(`/anexos/${b.dataset.reprocessar}/reprocessar-ocr`); toast("info", "OCR reenviado para processamento"); setTimeout(carregar, 1500); } catch (err) { toastErro(err); }
  });
  on(raiz, "click", "[data-verificar]", (e, b) => verificarAssinatura(b.dataset.verificar));
  on(raiz, "click", "[data-dossie]", (e, b) => comCarregamento(b, api.baixar(`/solicitacoes/${id}/dossie.pdf`, null, { nomePadrao: "dossie.pdf" })).catch(toastErro));

  await carregar();

  const recarregar = debounce(() => {
    if (modalAberto) { toast("info", "Solicitação atualizada", "Houve alterações. Os dados serão atualizados ao fechar a janela."); return; }
    carregar();
  }, 600);
  const desligar = [
    ouvir("evento", (ev) => { if (ev.id === id || ev.solicitacao_id === id) recarregar(); }),
    ouvir("consulta-periodica", () => { if (!modalAberto) carregar(); }),
  ];
  return { desmontar: () => desligar.forEach((f) => f()) };
}
