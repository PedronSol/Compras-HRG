// Estado global mínimo e barramento de eventos da aplicação.

export const estado = {
  usuario: null,
  csrf: null,
  meta: null,
  naoLidas: 0,
  pendentesUsuarios: 0,
  contadores: {},
};

const ouvintes = new Map();

export function ouvir(evento, fn) {
  if (!ouvintes.has(evento)) ouvintes.set(evento, new Set());
  ouvintes.get(evento).add(fn);
  return () => ouvintes.get(evento)?.delete(fn);
}

export function emitir(evento, dados) {
  ouvintes.get(evento)?.forEach((fn) => {
    try { fn(dados); } catch (e) { console.error(`Erro no ouvinte de "${evento}"`, e); }
  });
}

export function rotulo(grupo, valor) {
  return estado.meta?.rotulos?.[grupo]?.[valor] ?? valor ?? "—";
}

export function setor(codigo) {
  return estado.meta?.setores?.find((s) => s.codigo === codigo);
}

export const temPapel = (...papeis) => papeis.includes(estado.usuario?.papel);
