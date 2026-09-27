// Minhas pendências: tudo o que aguarda uma ação do usuário, em ordem de prioridade.
import { api } from "../api.js";
import { estado, rotulo } from "../estado.js";
import { html, renderizar } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { ativarLinhasClicaveis, badgePedido, badgeSla, badgeStatus, badgeUrgencia, cabecalho, formato, pode, vazio } from "../ui/componentes.js";

const ORIENTACAO = {
  gestor: "Solicitações do seu setor aguardando aprovação.",
  diretoria: "Solicitações e pedidos acima da alçada aguardando a Diretoria.",
  solicitante: "Solicitações devolvidas ao seu setor para ajustes.",
  comprador: "Solicitações para iniciar cotação, registrar propostas ou emitir pedido, e pedidos aprovados para enviar ao fornecedor.",
  financeiro: "Pedidos de compra aguardando aprovação orçamentária.",
  recebimento: "Pedidos enviados aos fornecedores aguardando entrega e conferência.",
};
const PROXIMA = {
  aguardando_gestor: "Analisar e decidir", aguardando_diretoria: "Analisar e decidir", devolvida: "Ajustar e reenviar",
  aprovada: "Iniciar cotação", em_cotacao: "Registrar propostas e definir fornecedor", aguardando_pedido: "Emitir pedido de compra",
};
const PROXIMA_PEDIDO = { aguardando_financeiro: "Aprovar pedido", aguardando_diretoria: "Aprovar pedido", aprovado: "Enviar ao fornecedor", enviado: "Registrar entrega", entregue_parcial: "Registrar saldo da entrega" };

export async function montar({ raiz }) {
  const p = await api.get("/painel/pendencias");
  const total = p.solicitacoes.length + p.pedidos.length;
  renderizar(raiz, html`${cabecalho({ titulo: "Minhas pendências", sub: ORIENTACAO[estado.usuario.papel] || "Itens que aguardam sua ação.",
      acoes: pode("solicitacao.criar") ? html`<a class="botao" href="/solicitacoes/nova">${icone("mais")}Nova solicitação</a>` : "" })}
    <div class="pilha">
      ${!total ? html`<section class="cartao">${vazio("Nenhuma pendência", "Tudo em dia! Você será notificado quando algo precisar da sua ação.", html`<a class="botao secundario" href="/">Voltar ao painel</a>`, "check_circulo")}</section>` : ""}
      ${p.solicitacoes.length ? html`<section class="cartao"><div class="cartao-cabecalho"><h2>${icone("documento")}Solicitações</h2><span class="badge primaria">${p.solicitacoes.length}</span></div>
        <div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Solicitação</th><th>Situação</th><th>Urgência</th><th>Prazo</th><th class="num">Valor</th><th>Próximo passo</th></tr></thead>
        <tbody>${p.solicitacoes.map((s) => html`<tr data-href="/solicitacoes/${s.id}${["em_cotacao", "aprovada"].includes(s.status) ? "?aba=cotacao" : ""}" tabindex="0">
          <td class="principal-td"><div class="principal-celula"><span class="codigo">${s.codigo}</span><a href="/solicitacoes/${s.id}">${s.titulo}</a><small>${s.setor_nome} · atualizada ${formato.relativo(s.atualizado_em)}</small></div></td>
          <td data-rotulo="Situação">${badgeStatus(s.status)}</td><td data-rotulo="Urgência">${badgeUrgencia(s.urgencia)}</td>
          <td data-rotulo="Prazo">${badgeSla(s.sla_situacao, s.sla_horas_restantes)}</td><td data-rotulo="Valor" class="num">${formato.moeda(s.valor_estimado)}</td>
          <td data-rotulo="Próximo passo"><span class="linha-flex pequeno negrito">${icone("seta_direita")}${PROXIMA[s.status] || rotulo("status_solicitacao", s.status)}</span></td></tr>`)}</tbody></table></div></section>` : ""}
      ${p.pedidos.length ? html`<section class="cartao"><div class="cartao-cabecalho"><h2>${icone("pedido")}Pedidos de compra</h2><span class="badge primaria">${p.pedidos.length}</span></div>
        <div class="tabela-envoltorio"><table class="tabela responsiva"><thead><tr><th>Pedido</th><th>Fornecedor</th><th>Situação</th><th>Previsão</th><th class="num">Valor</th><th>Próximo passo</th></tr></thead>
        <tbody>${p.pedidos.map((x) => html`<tr data-href="/pedidos/${x.id}" tabindex="0" class="${x.atrasado ? "atrasada" : ""}">
          <td class="principal-td"><div class="principal-celula"><span class="codigo">${x.codigo}</span><a href="/pedidos/${x.id}">${x.solicitacao_titulo}</a><small>${x.solicitacao_codigo} · ${x.setor_nome}</small></div></td>
          <td data-rotulo="Fornecedor">${x.fornecedor_fantasia || x.fornecedor_nome}</td>
          <td data-rotulo="Situação">${badgePedido(x.status)}${x.atrasado ? html`<br><span class="badge perigo">${icone("alerta")}Atrasado</span>` : ""}</td>
          <td data-rotulo="Previsão">${formato.data(x.data_prevista_entrega)}</td><td data-rotulo="Valor" class="num">${formato.moeda(x.valor_total)}</td>
          <td data-rotulo="Próximo passo"><span class="linha-flex pequeno negrito">${icone("seta_direita")}${PROXIMA_PEDIDO[x.status] || ""}</span></td></tr>`)}</tbody></table></div></section>` : ""}
    </div>`);
  ativarLinhasClicaveis(raiz);
}
