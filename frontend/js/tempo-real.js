// Cliente WebSocket com reconexão exponencial e fallback por consulta periódica.
import { emitir, estado } from "./estado.js";

let socket = null;
let tentativas = 0;
let temporizador = null;
let consultaPeriodica = null;
let ativo = false;

function url() {
  const protocolo = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocolo}//${location.host}/ws`;
}

function agendarReconexao() {
  if (!ativo) return;
  clearTimeout(temporizador);
  const espera = Math.min(30000, 1000 * 2 ** Math.min(tentativas, 5)) + Math.random() * 1000;
  tentativas += 1;
  temporizador = setTimeout(conectar, espera);
}

function conectar() {
  if (!ativo || !estado.meta?.tempo_real || !navigator.onLine) {
    iniciarConsulta();
    return;
  }
  try {
    socket = new WebSocket(url());
  } catch {
    agendarReconexao();
    return;
  }
  socket.addEventListener("open", () => {
    tentativas = 0;
    pararConsulta();
    emitir("tempo-real", true);
  });
  socket.addEventListener("message", (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.tipo === "evento") emitir("evento", msg);
    else if (msg.tipo === "ping") socket?.readyState === 1 && socket.send(JSON.stringify({ tipo: "pong" }));
  });
  socket.addEventListener("close", (e) => {
    emitir("tempo-real", false);
    socket = null;
    iniciarConsulta();
    if (e.code === 4401) { emitir("sessao-expirada"); return; }
    agendarReconexao();
  });
  socket.addEventListener("error", () => socket?.close());
}

function iniciarConsulta() {
  if (consultaPeriodica || !ativo) return;
  consultaPeriodica = setInterval(() => emitir("consulta-periodica"), 45000);
}

function pararConsulta() {
  clearInterval(consultaPeriodica);
  consultaPeriodica = null;
}

export function iniciarTempoReal() {
  ativo = true;
  tentativas = 0;
  conectar();
  window.addEventListener("online", () => { if (!socket) { tentativas = 0; conectar(); } });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && ativo && !socket) { tentativas = 0; conectar(); }
  });
}

export function pararTempoReal() {
  ativo = false;
  clearTimeout(temporizador);
  pararConsulta();
  socket?.close(1000);
  socket = null;
}
