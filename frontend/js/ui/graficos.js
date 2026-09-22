// Gráficos SVG/HTML acessíveis: barras horizontais, linhas (2 séries) e colunas.
// Especificação: marcas finas, extremidades arredondadas de 4px, linhas de 2px, grade discreta,
// legenda para >= 2 séries, tooltip ao passar o mouse/foco e tabela de dados alternativa.
import { html, seguro, escapar } from "./dom.js";
import { formato } from "./componentes.js";

function escalaBonita(maximo) {
  if (maximo <= 0) return { max: 1, passos: [0, 1] };
  const bruto = maximo / 4;
  const mag = 10 ** Math.floor(Math.log10(bruto));
  const passo = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= bruto) || bruto;
  const max = Math.ceil(maximo / passo) * passo;
  const passos = [];
  for (let v = 0; v <= max + 1e-9; v += passo) passos.push(v);
  return { max, passos };
}

/** Lista de barras horizontais (uma série). Rótulo de valor na ponta de cada barra. */
export function barrasHorizontais(itens, { formatar = formato.numero, link = null, vazioTexto = "Sem dados no período." } = {}) {
  if (!itens.length || itens.every((i) => !i.valor)) return html`<p class="texto-3 pequeno">${vazioTexto}</p>`;
  const max = Math.max(...itens.map((i) => i.valor)) || 1;
  return html`<div class="barras-lista" role="list">${itens.map((i) => {
    const conteudo = html`<span class="rot">${i.cor ? html`<i data-cor="${i.cor}"></i>` : ""}<span title="${i.rotulo}">${i.rotulo}</span></span>
      <span class="trilho"><span class="preench" data-largura="${((i.valor / max) * 100).toFixed(1)}"></span></span>
      <span class="v">${formatar(i.valor)}</span>`;
    return link && i.href
      ? html`<a class="barra-linha" role="listitem" href="${i.href}" data-link aria-label="${i.rotulo}: ${formatar(i.valor)}">${conteudo}</a>`
      : html`<div class="barra-linha" role="listitem" aria-label="${i.rotulo}: ${formatar(i.valor)}">${conteudo}</div>`;
  })}</div>`;
}

/** Gráfico de linhas com até 2 séries, eixo Y único, cursor vertical e tooltip. */
export function linhas({ categorias, series, formatar = formato.numero, altura = 240, titulo = "" }) {
  const W = 640, H = altura, m = { t: 16, r: 56, b: 28, l: 44 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const todos = series.flatMap((s) => s.valores);
  const { max, passos } = escalaBonita(Math.max(0, ...todos));
  const n = categorias.length;
  const x = (i) => m.l + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v) => m.t + ih - (v / max) * ih;
  const grade = passos.map((p) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(p)}" y2="${y(p)}"/>`).join("");
  const eixoY = passos.map((p) => `<text x="${m.l - 8}" y="${y(p) + 4}" text-anchor="end">${escapar(formato.numero(p))}</text>`).join("");
  const salto = Math.ceil(n / 8);
  const eixoX = categorias.map((c, i) => (i % salto === 0 || i === n - 1 ? `<text x="${x(i)}" y="${H - 8}" text-anchor="middle">${escapar(c)}</text>` : "")).join("");
  const desenhos = series.map((s, si) => {
    const pts = s.valores.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    const area = si === 0 && n > 1 ? `<polygon class="area-1" points="${m.l},${y(0)} ${pts} ${x(n - 1)},${y(0)}"/>` : "";
    const ultimo = s.valores[n - 1] ?? 0;
    return `${area}<polyline class="linha-${si + 1}" points="${pts}" fill="none" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      <circle class="ponto-${si + 1}" cx="${x(n - 1)}" cy="${y(ultimo)}" r="4.5"/>
      <text class="rotulo-valor" x="${x(n - 1) + 9}" y="${y(ultimo) + 4 + (si ? 12 : -2) * (series.length > 1 && Math.abs(y(series[0].valores[n - 1] ?? 0) - y(series[1]?.valores[n - 1] ?? 0)) < 14 ? 1 : 0)}">${escapar(formatar(ultimo))}</text>`;
  }).join("");
  const largura = n > 1 ? iw / (n - 1) : iw;
  const alvos = categorias.map((c, i) => {
    const dica = series.map((s) => `${s.nome}: ${formatar(s.valores[i])}`).join(", ");
    return `<rect class="alvo" tabindex="0" data-i="${i}" x="${x(i) - largura / 2}" y="${m.t}" width="${largura}" height="${ih}" aria-label="${escapar(c)} — ${escapar(dica)}"/>`;
  }).join("");
  const dados = encodeURIComponent(JSON.stringify({ categorias, series: series.map((s) => ({ nome: s.nome, valores: s.valores })), x: categorias.map((_, i) => x(i) / W), ys: series.map((s) => s.valores.map((v) => y(v) / H)) }));
  return html`
    ${series.length > 1 ? html`<div class="legenda">${series.map((s, i) => html`<span><i class="s${i + 1}"></i>${s.nome}</span>`)}</div>` : ""}
    <div class="grafico" data-grafico="linhas" data-dados="${dados}" data-formato="${formatar === formato.moeda ? "moeda" : "numero"}">
      <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${titulo}">
        ${seguro(`<g class="grade">${grade}</g><g class="eixo">${eixoY}${eixoX}</g>
        <line class="cursor oculto" x1="0" x2="0" y1="${m.t}" y2="${m.t + ih}"/>${desenhos}<g>${alvos}</g>`)}
      </svg>
    </div>`;
}

/** Colunas verticais (uma série) com tooltip e valor no topo da maior coluna. */
export function colunas({ categorias, valores, formatar = formato.numero, altura = 220, titulo = "" }) {
  const W = 640, H = altura, m = { t: 22, r: 12, b: 28, l: 56 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const { max, passos } = escalaBonita(Math.max(0, ...valores));
  const n = categorias.length || 1;
  const banda = iw / n;
  const larg = Math.min(24, banda * 0.6);
  const y = (v) => m.t + ih - (v / max) * ih;
  const grade = passos.map((p) => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(p)}" y2="${y(p)}"/>`).join("");
  const eixoY = passos.map((p) => `<text x="${m.l - 8}" y="${y(p) + 4}" text-anchor="end">${escapar(formatar === formato.moeda ? formato.moedaCompacta(p) : formato.numero(p))}</text>`).join("");
  const salto = Math.ceil(n / 8);
  const iMax = valores.indexOf(Math.max(...valores));
  const barras = valores.map((v, i) => {
    const cx = m.l + banda * i + banda / 2;
    const h = Math.max(0, y(0) - y(v));
    const r = Math.min(4, h);
    const x0 = cx - larg / 2, topo = y(v);
    const caminho = h > 0
      ? `M${x0},${y(0)} V${topo + r} Q${x0},${topo} ${x0 + r},${topo} H${x0 + larg - r} Q${x0 + larg},${topo} ${x0 + larg},${topo + r} V${y(0)} Z`
      : "";
    const rot = i % salto === 0 || i === n - 1 ? `<text x="${cx}" y="${H - 8}" text-anchor="middle">${escapar(categorias[i])}</text>` : "";
    const valorTopo = i === iMax && v > 0 ? `<text class="rotulo-valor" x="${cx}" y="${topo - 6}" text-anchor="middle">${escapar(formatar(v))}</text>` : "";
    return `${caminho ? `<path class="serie-1" d="${caminho}"/>` : ""}${valorTopo}<g class="eixo">${rot}</g>
      <rect class="alvo" tabindex="0" x="${m.l + banda * i}" y="${m.t}" width="${banda}" height="${ih}" data-dica="${escapar(categorias[i])}|${escapar(formatar(v))}" aria-label="${escapar(categorias[i])}: ${escapar(formatar(v))}"/>`;
  }).join("");
  return html`<div class="grafico" data-grafico="colunas"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${titulo}">
    ${seguro(`<g class="grade">${grade}</g><g class="eixo">${eixoY}</g>${barras}`)}</svg></div>`;
}

/** Tabela de dados alternativa (acessibilidade e leitura precisa). */
export function tabelaDados(cabecalho, linhasTabela) {
  return html`<details class="pequeno"><summary class="texto-3">Ver dados em tabela</summary>
    <div class="tabela-envoltorio"><table class="tabela"><thead><tr>${cabecalho.map((c) => html`<th scope="col">${c}</th>`)}</tr></thead>
    <tbody>${linhasTabela.map((l) => html`<tr>${l.map((c, i) => (i === 0 ? html`<th scope="row">${c}</th>` : html`<td class="num">${c}</td>`))}</tr>`)}</tbody></table></div></details>`;
}

/** Ativa tooltips e cursor dos gráficos dentro de `raiz`. */
export function ativarGraficos(raiz) {
  raiz.querySelectorAll(".grafico").forEach((g) => {
    if (g.dataset.ativo) return;
    g.dataset.ativo = "1";
    const dica = document.createElement("div");
    dica.className = "dica-grafico oculto";
    dica.setAttribute("aria-hidden", "true");
    g.appendChild(dica);
    const svg = g.querySelector("svg");
    const mostrar = (alvo) => {
      const caixaG = g.getBoundingClientRect();
      const caixaA = alvo.getBoundingClientRect();
      let conteudo = "";
      if (g.dataset.grafico === "linhas") {
        const d = JSON.parse(decodeURIComponent(g.dataset.dados));
        const i = Number(alvo.dataset.i);
        const fmt = g.dataset.formato === "moeda" ? formato.moeda : formato.numero;
        conteudo = `<div class="d-titulo">${escapar(d.categorias[i])}</div>` + d.series.map((s, si) =>
          `<div class="d-linha"><span class="legenda"><i class="s${si + 1}"></i></span>${escapar(s.nome)}<b>${escapar(fmt(s.valores[i]))}</b></div>`).join("");
        const cursor = svg.querySelector(".cursor");
        const xRel = d.x[i] * 640;
        cursor.setAttribute("x1", xRel);
        cursor.setAttribute("x2", xRel);
        cursor.classList.remove("oculto");
        dica.style.left = `${d.x[i] * caixaG.width}px`;
        dica.style.top = `${Math.min(...d.ys.map((ys) => ys[i])) * svg.getBoundingClientRect().height}px`;
      } else {
        const [titulo, valor] = (alvo.dataset.dica || "|").split("|");
        conteudo = `<div class="d-titulo">${escapar(titulo)}</div><div class="d-linha">Valor<b>${escapar(valor)}</b></div>`;
        dica.style.left = `${caixaA.left - caixaG.left + caixaA.width / 2}px`;
        dica.style.top = `${caixaA.top - caixaG.top + 20}px`;
      }
      dica.innerHTML = conteudo;
      dica.classList.remove("oculto");
    };
    const esconder = () => {
      dica.classList.add("oculto");
      svg.querySelector(".cursor")?.classList.add("oculto");
    };
    svg.querySelectorAll(".alvo").forEach((alvo) => {
      alvo.addEventListener("mouseenter", () => mostrar(alvo));
      alvo.addEventListener("focus", () => mostrar(alvo));
      alvo.addEventListener("mouseleave", esconder);
      alvo.addEventListener("blur", esconder);
    });
  });
}
