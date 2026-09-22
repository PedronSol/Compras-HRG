// Cliente HTTP da API REST: sessão por cookie HttpOnly + token CSRF em cabeçalho.
import { estado, emitir } from "./estado.js";

const BASE = "/api/v1";

export class ErroApi extends Error {
  constructor(status, corpo) {
    const erro = corpo?.erro || {};
    super(erro.mensagem || `Erro ${status}`);
    this.status = status;
    this.codigo = erro.codigo || "erro";
    this.campos = erro.campos || {};
  }
}

async function requisitar(metodo, caminho, { corpo, consulta, formulario, bruto = false, sinal } = {}) {
  let url = caminho.startsWith("/api/") ? caminho : BASE + caminho;
  if (consulta) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(consulta)) {
      if (v !== undefined && v !== null && v !== "" && v !== false) params.append(k, v === true ? "1" : v);
    }
    const qs = params.toString();
    if (qs) url += (url.includes("?") ? "&" : "?") + qs;
  }
  const cabecalhos = { Accept: "application/json" };
  let body;
  if (formulario) {
    body = formulario;
  } else if (corpo !== undefined) {
    cabecalhos["Content-Type"] = "application/json";
    body = JSON.stringify(corpo);
  }
  if (metodo !== "GET" && estado.csrf) cabecalhos["X-CSRF-Token"] = estado.csrf;

  let resposta;
  try {
    resposta = await fetch(url, { method: metodo, headers: cabecalhos, body, credentials: "same-origin", signal: sinal });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ErroApi(0, { erro: { codigo: "rede", mensagem: navigator.onLine ? "Não foi possível contatar o servidor." : "Sem conexão com a internet." } });
  }
  if (bruto && resposta.ok) return resposta;
  const tipo = resposta.headers.get("Content-Type") || "";
  const dados = tipo.includes("application/json") ? await resposta.json().catch(() => null) : null;
  if (!resposta.ok) {
    const erro = new ErroApi(resposta.status, dados);
    if (resposta.status === 401 && !caminho.startsWith("/auth/login")) emitir("sessao-expirada", erro);
    if (erro.codigo === "troca_senha_obrigatoria") emitir("troca-senha-obrigatoria", erro);
    throw erro;
  }
  return dados;
}

export const api = {
  get: (caminho, consulta, opcoes = {}) => requisitar("GET", caminho, { consulta, ...opcoes }),
  post: (caminho, corpo) => requisitar("POST", caminho, { corpo: corpo ?? {} }),
  patch: (caminho, corpo) => requisitar("PATCH", caminho, { corpo }),
  delete: (caminho) => requisitar("DELETE", caminho),
  enviarFormulario: (caminho, formData) => requisitar("POST", caminho, { formulario: formData }),

  /** Baixa um arquivo autenticado (PDF, CSV, anexo) e dispara o download ou abre em nova aba. */
  async baixar(caminho, consulta, { abrir = false, nomePadrao = "arquivo" } = {}) {
    const resposta = await requisitar("GET", caminho, { consulta, bruto: true });
    const blob = await resposta.blob();
    const disposicao = resposta.headers.get("Content-Disposition") || "";
    const nome = decodeURIComponent((disposicao.match(/filename\*=UTF-8''([^;]+)/) || [])[1] || "")
      || (disposicao.match(/filename="([^"]+)"/) || [])[1] || nomePadrao;
    const url = URL.createObjectURL(blob);
    if (abrir) {
      const janela = window.open(url, "_blank");
      if (janela) janela.opener = null;
      else baixarUrl(url, nome);
    } else {
      baixarUrl(url, nome);
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
};

function baixarUrl(url, nome) {
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
