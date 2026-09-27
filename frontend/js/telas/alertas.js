// Alertas operacionais: prazos, entregas, aprovações paradas, propostas vencendo e divergências.
import { api } from "../api.js";
import { html, renderizar, on } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { abas, cabecalho, formato, kpi, vazio } from "../ui/componentes.js";

const TIPOS = { "": "Todos", sla: "Prazo de atendimento", entrega: "Entregas", aprovacao: "Aprovações paradas", proposta: "Propostas", recebimento: "Recebimentos" };
const ICONE = { sla: "ampulheta", entrega: "caminhao", aprovacao: "carimbo", proposta: "balanca", recebimento: "devolver" };
const TOM = { critico: "perigo", alerta: "alerta", info: "info" };
const GRAVIDADE = { critico: "Crítico", alerta: "Atenção", info: "Informativo" };

export async function montar({ raiz }) {
  const r = await api.get("/alertas");
  let tipo = "";
  renderizar(raiz, html`${cabecalho({ titulo: "Alertas", sub: "Situações que merecem atenção agora, calculadas em tempo real para o seu perfil" })}
    <div class="pilha">
      <div class="kpis compactos">
        ${kpi({ rotulo: "Críticos", valor: r.resumo.critico, icone: "alerta", tom: r.resumo.critico ? "perigo" : "sucesso", meta: "Prazos estourados e entregas atrasadas" })}
        ${kpi({ rotulo: "Atenção", valor: r.resumo.alerta, icone: "relogio", tom: r.resumo.alerta ? "alerta" : "sucesso", meta: "Vencendo, paradas ou com divergência" })}
        ${kpi({ rotulo: "Informativos", valor: r.resumo.info, icone: "info", meta: "Entregas e validades próximas" })}
      </div>
      <section class="cartao"><div id="abas"></div><div id="lista"></div></section>
    </div>`);
  function desenhar() {
    const contagem = (t) => r.itens.filter((a) => !t || a.tipo === t).length;
    renderizar(raiz.querySelector("#abas"), abas(Object.entries(TIPOS).map(([v, rot]) => ({ valor: v, rotulo: rot, qtd: contagem(v) })).filter((a) => !a.valor || a.qtd), tipo, { nome: "tipo" }));
    const itens = r.itens.filter((a) => !tipo || a.tipo === tipo);
    renderizar(raiz.querySelector("#lista"), itens.length ? html`<ul class="lista-itens">${itens.map((a) => html`<li><a class="item-lista" href="${a.link}">
      <span class="icone-item ${TOM[a.gravidade]}">${icone(ICONE[a.tipo] || "alerta")}</span>
      <span class="corpo-item"><strong>${a.titulo}</strong><small>${a.descricao}${a.setor ? ` · ${a.setor}` : ""}</small></span>
      <span class="lado"><span class="badge ${TOM[a.gravidade]}">${GRAVIDADE[a.gravidade]}</span><small>${a.data ? (String(a.data).length === 10 ? formato.data(a.data) : formato.relativo(a.data)) : ""}</small></span></a></li>`)}</ul>`
      : vazio("Nenhum alerta", "Tudo sob controle para o seu perfil.", "", "check_circulo"));
  }
  on(raiz, "click", "[data-tipo]", (e, b) => { tipo = b.dataset.tipo; desenhar(); });
  desenhar();
}
