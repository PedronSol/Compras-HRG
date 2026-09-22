// Zona de upload com arrastar-e-soltar, validação de tipo/tamanho e limite de arquivos.
import { estado } from "../estado.js";
import { html, renderizar, on } from "./dom.js";
import { icone } from "./icones.js";
import { formato, toast } from "./componentes.js";

const EXTENSOES = ".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.docx,.xlsx";

export function zonaUpload({ id = "arquivos", max = 3, rotulo = "Documentos", ajuda = "" } = {}) {
  const mb = estado.meta.limites.max_upload_mb;
  return html`<div class="campo" data-campo="${id}">
    <span class="rotulo" id="${id}-rotulo">${rotulo}</span>
    <div class="zona-upload" data-zona="${id}">
      ${icone("upload")}
      <p><strong>Clique para selecionar</strong> ou arraste os arquivos aqui</p>
      <p class="pequeno texto-3">PDF, imagens (PNG, JPG, WEBP, TIFF), DOCX ou XLSX · até ${mb} MB cada · máximo ${max} arquivo(s)</p>
      <input type="file" id="${id}" multiple accept="${EXTENSOES}" aria-labelledby="${id}-rotulo" aria-describedby="${id}-ajuda">
    </div>
    ${ajuda ? html`<p class="ajuda" id="${id}-ajuda">${ajuda}</p>` : html`<p class="sr-only" id="${id}-ajuda">Máximo de ${max} arquivos de até ${mb} MB.</p>`}
    <ul class="lista-arquivos" data-lista="${id}" aria-live="polite"></ul>
  </div>`;
}

/** Ativa a zona e retorna um controlador { arquivos(), limpar(), definirMaximo(n) }. */
export function ativarUpload(raiz, { id = "arquivos", max = 3, aoMudar } = {}) {
  const zona = raiz.querySelector(`[data-zona="${id}"]`);
  const input = zona.querySelector("input");
  const lista = raiz.querySelector(`[data-lista="${id}"]`);
  const mb = estado.meta.limites.max_upload_mb;
  const tipos = new Set(estado.meta.limites.tipos_arquivo);
  let arquivos = [];
  let limite = max;

  function desenhar() {
    renderizar(lista, html`${arquivos.map((a, i) => html`<li class="arquivo">
      <span class="icone-arquivo">${icone(a.type === "application/pdf" ? "pdf" : "documento")}</span>
      <span><span class="nome">${a.name}</span><br><span class="meta">${formato.tamanho(a.size)} · OCR automático após o envio</span></span>
      <span class="acoes"><button type="button" class="botao fantasma pequeno icone" data-remover="${i}" aria-label="Remover ${a.name}">${icone("lixeira")}</button></span>
    </li>`)}`);
    aoMudar?.(arquivos);
  }

  function adicionar(novos) {
    for (const f of novos) {
      const tipoOk = tipos.has(f.type) || /\.(pdf|png|jpe?g|webp|tiff?|docx|xlsx)$/i.test(f.name);
      if (!tipoOk) { toast("alerta", "Formato não permitido", `${f.name}: envie PDF, imagem, DOCX ou XLSX.`); continue; }
      if (f.size > mb * 1024 * 1024) { toast("alerta", "Arquivo muito grande", `${f.name} excede ${mb} MB.`); continue; }
      if (f.size === 0) { toast("alerta", "Arquivo vazio", f.name); continue; }
      if (arquivos.length >= limite) { toast("alerta", "Limite de anexos", `Máximo de ${limite} arquivo(s).`); break; }
      if (arquivos.some((a) => a.name === f.name && a.size === f.size)) continue;
      arquivos.push(f);
    }
    input.value = "";
    desenhar();
  }

  input.addEventListener("change", () => adicionar([...input.files]));
  ["dragenter", "dragover"].forEach((ev) => zona.addEventListener(ev, (e) => { e.preventDefault(); zona.classList.add("arrastando"); }));
  ["dragleave", "drop"].forEach((ev) => zona.addEventListener(ev, () => zona.classList.remove("arrastando")));
  zona.addEventListener("drop", (e) => { e.preventDefault(); adicionar([...e.dataTransfer.files]); });
  on(lista, "click", "[data-remover]", (e, b) => { arquivos.splice(Number(b.dataset.remover), 1); desenhar(); });

  return {
    arquivos: () => [...arquivos],
    limpar: () => { arquivos = []; desenhar(); },
    definirMaximo: (n) => { limite = n; if (arquivos.length > n) { arquivos = arquivos.slice(0, n); desenhar(); } },
  };
}
