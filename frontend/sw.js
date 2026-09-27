// Service worker do Compras · Hospital Rio Grande.
// - Estáticos (shell, CSS, JS, marca): rede primeiro (revalidação por ETag) com cache de reserva offline.
// - Navegação: rede primeiro; offline cai para o shell em cache (a SPA exibe o aviso de conexão).
// - API (/api/*) e WebSocket: nunca armazenados em cache (dados pessoais e sensíveis — LGPD).
const VERSAO = "rg-compras-v2.0.1";
const SHELL = [
  "/", "/index.html", "/offline.html", "/manifest.webmanifest", "/favicon.svg", "/favicon-48.png",
  "/css/base.css", "/css/componentes.css", "/assets/fontes/inter-latin.woff2", "/assets/fontes/inter-latin-ext.woff2",
  "/js/tema-inicial.js", "/js/app.js", "/js/api.js", "/js/estado.js", "/js/roteador.js", "/js/tempo-real.js", "/js/tema.js",
  "/js/ui/dom.js", "/js/ui/icones.js", "/js/ui/componentes.js", "/js/ui/graficos.js", "/js/ui/shell.js", "/js/ui/upload.js",
  "/js/telas/acesso.js", "/js/telas/painel.js", "/js/telas/pendencias.js", "/js/telas/alertas.js", "/js/telas/solicitacoes.js",
  "/js/telas/solicitacao-nova.js", "/js/telas/solicitacao-detalhe.js", "/js/telas/aprovacoes.js", "/js/telas/cotacoes.js",
  "/js/telas/pedidos.js", "/js/telas/pedido-detalhe.js", "/js/telas/recebimentos.js", "/js/telas/fornecedores.js",
  "/js/telas/materiais.js", "/js/telas/relatorios.js", "/js/telas/usuarios.js", "/js/telas/auditoria.js",
  "/js/telas/notificacoes.js", "/js/telas/perfil.js",
  "/assets/marca/logo-rg-hospital-branca.svg", "/assets/marca/logo-rg-hospital-primaria.svg",
  "/assets/marca/simbolo-rg-branca.svg", "/assets/icones/icone-192.png", "/assets/icones/icone-512.png",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(VERSAO).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys()
      .then((chaves) => Promise.all(chaves.filter((c) => c.startsWith("rg-") && c !== VERSAO).map((c) => caches.delete(c))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (evento) => {
  const req = evento.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/") || url.pathname === "/ws") return;

  if (req.mode === "navigate") {
    evento.respondWith(
      fetch(req).catch(async () => (await caches.match("/index.html")) || caches.match("/offline.html")),
    );
    return;
  }

  evento.respondWith(
    caches.open(VERSAO).then(async (cache) => {
      try {
        const resp = await fetch(req);
        if (resp.ok && resp.type === "basic") cache.put(req, resp.clone());
        return resp;
      } catch (erro) {
        const emCache = await cache.match(req);
        if (emCache) return emCache;
        throw erro;
      }
    }),
  );
});

self.addEventListener("message", (evento) => {
  if (evento.data === "pular-espera") self.skipWaiting();
});
