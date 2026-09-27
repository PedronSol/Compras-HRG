// Anexar ou fotografar documentos (arrastar e soltar, seleção ou câmera do celular).
// O arquivo é apenas armazenado de forma cifrada: nenhum conteúdo é lido ou interpretado automaticamente.
import { estado } from "../estado.js";
import { html, renderizar, on } from "./dom.js";
import { icone } from "./icones.js";
import { formato, toast } from "./componentes.js";

const EXTENSOES = ".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.docx,.xlsx";

export function zonaUpload({ id = "arquivos", max = 5, rotulo = "Documentos", ajuda = "", camera = true } = {}) {
  const mb = estado.meta.limites.max_upload_mb;
  return html`<div class="campo" data-campo="${id}">
    <span class="rotulo" id="${id}-rotulo">${rotulo}</span>
    <div class="zona-upload" data-zona="${id}">
      ${icone("upload")}
      <p><strong>Arraste os arquivos aqui</strong> ou clique para selecionar</p>
      <p class="minusculo texto-3">PDF, imagem, DOCX ou XLSX · até ${mb} MB cada · máximo ${max} arquivo(s)</p>
      <input type="file" id="${id}" multiple accept="${EXTENSOES}" aria-labelledby="${id}-rotulo" aria-describedby="${id}-ajuda">
      ${camera ? html`<div class="acoes-upload">
        <label class="botao secundario pequeno">${icone("camera")}Fotografar documento<input type="file" accept="image/*" capture="environment" class="sr-only" data-camera="${id}"></label>
      </div>` : ""}
    </div>
    <p class="ajuda" id="${id}-ajuda">${ajuda || "O documento fica anexado para consulta. Nenhuma informação é extraída automaticamente."}</p>
    <ul class="lista-arquivos" data-lista="${id}" aria-live="polite"></ul>
  </div>`;
}

/** Ativa a zona e retorna um controlador { arquivos(), limpar(), definirMaximo(n) }. */
export function ativarUpload(raiz, { id = "arquivos", max = 5, aoMudar } = {}) {
  const zona = raiz.querySelector(`[data-zona="${id}"]`);
  const input = zona.querySelector(`input#${id}`);
  const camera = zona.querySelector(`[data-camera="${id}"]`);
  const lista = raiz.querySelector(`[data-lista="${id}"]`);
  const mb = estado.meta.limites.max_upload_mb;
  const tipos = new Set(estado.meta.limites.tipos_arquivo);
  let arquivos = [];
  let limite = max;

  function desenhar() {
    renderizar(lista, html`${arquivos.map((a, i) => html`<li class="arquivo">
      <span class="icone-arquivo">${icone(a.type === "application/pdf" ? "pdf" : a.type.startsWith("image/") ? "camera" : "documento")}</span>
      <span class="info-arquivo"><span class="nome">${a.name}</span><span class="meta">${formato.tamanho(a.size)} · será anexado ao enviar</span></span>
      <span class="acoes"><button type="button" class="botao fantasma pequeno icone" data-remover="${i}" aria-label="Remover ${a.name}">${icone("lixeira")}</button></span>
    </li>`)}`);
    aoMudar?.(arquivos);
  }

  function adicionar(novos, foto = false) {
    for (const original of novos) {
      let f = original;
      if (foto && f.type.startsWith("image/")) {
        const ext = f.type === "image/png" ? "png" : "jpg";
        const carimbo = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
        f = new File([f], `foto-documento-${carimbo}.${ext}`, { type: f.type });
      }
      const tipoOk = tipos.has(f.type) || /\.(pdf|png|jpe?g|webp|tiff?|docx|xlsx)$/i.test(f.name);
      if (!tipoOk) { toast("alerta", "Formato não permitido", `${f.name}: envie PDF, imagem, DOCX ou XLSX.`); continue; }
      if (f.size > mb * 1024 * 1024) { toast("alerta", "Arquivo muito grande", `${f.name} excede ${mb} MB.`); continue; }
      if (f.size === 0) { toast("alerta", "Arquivo vazio", f.name); continue; }
      if (arquivos.length >= limite) { toast("alerta", "Limite de documentos", `Máximo de ${limite} arquivo(s).`); break; }
      if (arquivos.some((a) => a.name === f.name && a.size === f.size)) continue;
      arquivos.push(f);
    }
    input.value = "";
    if (camera) camera.value = "";
    desenhar();
  }

  input.addEventListener("change", () => adicionar([...input.files]));
  camera?.addEventListener("change", () => adicionar([...camera.files], true));
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
