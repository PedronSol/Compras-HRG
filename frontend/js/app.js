// Ponto de entrada da aplicação RG Hospital.
import { api } from "./api.js";
import { estado, ouvir } from "./estado.js";
import { definirRota, iniciarRoteador, navegar, processar, aoMudarRota, podeAcessar } from "./roteador.js";
import { iniciarTempoReal, pararTempoReal } from "./tempo-real.js";
import { $, html, renderizar } from "./ui/dom.js";
import { icone } from "./ui/icones.js";
import { carregando, erroTela, toast, vazio } from "./ui/componentes.js";
import { montarShell, desmontarShell, marcarMenuAtivo } from "./ui/shell.js";
import { aplicarTema, temaAtual } from "./tema.js";

// ------------------------------------------------------------------ rotas
definirRota("/perfis", () => import("./telas/acesso.js"), { publica: true, titulo: "Escolher perfil", tela: "perfis" });
definirRota("/login", () => import("./telas/acesso.js"), { publica: true, titulo: "Entrar", tela: "login" });
definirRota("/cadastro", () => import("./telas/acesso.js"), { publica: true, titulo: "Solicitar acesso", tela: "cadastro" });
definirRota("/trocar-senha", () => import("./telas/acesso.js"), { titulo: "Definir nova senha", tela: "trocarSenha", semShell: true });
definirRota("/", () => import("./telas/painel.js"), { titulo: "Painel" });
definirRota("/pendencias", () => import("./telas/pendencias.js"), { titulo: "Minhas pendências" });
definirRota("/alertas", () => import("./telas/alertas.js"), { titulo: "Alertas" });
definirRota("/solicitacoes", () => import("./telas/solicitacoes.js"), { titulo: "Solicitações" });
definirRota("/solicitacoes/nova", () => import("./telas/solicitacao-nova.js"), { titulo: "Nova solicitação", capacidade: "solicitacao.criar" });
definirRota("/solicitacoes/:id/ajustar", () => import("./telas/solicitacao-nova.js"), { titulo: "Ajustar solicitação", capacidade: "solicitacao.criar" });
definirRota("/solicitacoes/:id", () => import("./telas/solicitacao-detalhe.js"), { titulo: "Solicitação" });
definirRota("/aprovacoes", () => import("./telas/aprovacoes.js"), { titulo: "Aprovações" });
definirRota("/cotacoes", () => import("./telas/cotacoes.js"), { titulo: "Cotações" });
definirRota("/pedidos", () => import("./telas/pedidos.js"), { titulo: "Pedidos de compra", capacidade: "pedido.ver" });
definirRota("/pedidos/:id", () => import("./telas/pedido-detalhe.js"), { titulo: "Pedido de compra", capacidade: "pedido.ver" });
definirRota("/recebimentos", () => import("./telas/recebimentos.js"), { titulo: "Recebimento", capacidade: "recebimento.ver" });
definirRota("/fornecedores", () => import("./telas/fornecedores.js"), { titulo: "Fornecedores", capacidade: "fornecedor.ver" });
definirRota("/materiais", () => import("./telas/materiais.js"), { titulo: "Materiais e categorias", capacidade: "material.ver" });
definirRota("/relatorios", () => import("./telas/relatorios.js"), { titulo: "Relatórios e indicadores", capacidade: "relatorio.ver" });
definirRota("/usuarios", () => import("./telas/usuarios.js"), { titulo: "Usuários e perfis", papeis: ["admin", "auditoria"] });
definirRota("/auditoria", () => import("./telas/auditoria.js"), { titulo: "Auditoria", capacidade: "auditoria.ver" });
definirRota("/notificacoes", () => import("./telas/notificacoes.js"), { titulo: "Notificações" });
definirRota("/perfil", () => import("./telas/perfil.js"), { titulo: "Meu perfil" });

const raiz = $("#app");
let shellMontado = false;

function garantirShell() {
  if (shellMontado) return;
  montarShell(raiz);
  shellMontado = true;
  iniciarTempoReal();
}

function removerShell() {
  if (!shellMontado) return;
  desmontarShell();
  pararTempoReal();
  shellMontado = false;
}

aoMudarRota(async (encontrado, consulta) => {
  const instituicao = "Compras · " + (estado.meta?.instituicao || "Hospital Rio Grande");
  if (!encontrado) {
    if (!estado.usuario) { navegar("/perfis", { substituir: true }); return null; }
    garantirShell();
    document.title = `Página não encontrada · ${instituicao}`;
    renderizar($("#tela"), html`<div class="cartao">${vazio("Página não encontrada", "O endereço acessado não existe ou foi movido.", html`<a class="botao" href="/">${icone("painel")}Ir para o painel</a>`, "busca")}</div>`);
    return null;
  }
  const { rota, params } = encontrado;

  if (!rota.publica && !estado.usuario) {
    const retorno = location.pathname + location.search;
    navegar(retorno !== "/" ? `/login?retorno=${encodeURIComponent(retorno)}` : "/perfis", { substituir: true });
    return null;
  }
  if (rota.publica && estado.usuario) { navegar("/", { substituir: true }); return null; }
  if (estado.usuario?.troca_senha_obrigatoria && rota.tela !== "trocarSenha") {
    navegar("/trocar-senha", { substituir: true });
    return null;
  }

  document.title = `${rota.titulo} · ${instituicao}`;
  let alvo;
  if (rota.publica || rota.semShell) {
    removerShell();
    alvo = raiz;
  } else {
    garantirShell();
    marcarMenuAtivo(location.pathname);
    alvo = $("#tela");
    if (!podeAcessar(rota)) {
      renderizar(alvo, html`<div class="cartao">${vazio("Acesso restrito", "Seu perfil não tem permissão para acessar esta área. As permissões são definidas pelo Administrador.", html`<a class="botao secundario" href="/">Voltar ao painel</a>`, "cadeado")}</div>`);
      return null;
    }
    renderizar(alvo, carregando());
  }

  try {
    const modulo = await rota.carregar();
    const montar = modulo.telas?.[rota.tela] || modulo.montar;
    const tela = await montar({ raiz: alvo, params, consulta, rota });
    if (!rota.publica && !rota.semShell) {
      $("#conteudo")?.focus({ preventScroll: true });
      window.scrollTo(0, 0);
    }
    return tela || null;
  } catch (erro) {
    if (erro.name === "AbortError") return null;
    console.error(erro);
    if (erro.status === 401 || erro.codigo === "troca_senha_obrigatoria") return null;
    alvo.replaceChildren(erroTela(erro, () => processar()));
    return null;
  }
});

// ------------------------------------------------------------------ sessão
export async function carregarSessao() {
  try {
    const r = await api.get("/auth/me");
    estado.usuario = r.usuario;
    estado.csrf = r.csrf_token;
  } catch (e) {
    if (e.status !== 401 && e.status !== 403) throw e;
    estado.usuario = null;
    estado.csrf = null;
  }
}

ouvir("sessao-expirada", () => {
  if (!estado.usuario) return;
  estado.usuario = null;
  estado.csrf = null;
  removerShell();
  toast("alerta", "Sessão encerrada", "Faça login novamente para continuar.");
  navegar(`/login?retorno=${encodeURIComponent(location.pathname + location.search)}`, { substituir: true });
});

ouvir("troca-senha-obrigatoria", () => {
  if (estado.usuario) estado.usuario.troca_senha_obrigatoria = true;
  navegar("/trocar-senha", { substituir: true });
});

ouvir("sair", async () => {
  try { await api.post("/auth/logout"); } catch { /* sessão já encerrada */ }
  estado.usuario = null;
  estado.csrf = null;
  removerShell();
  navegar("/perfis", { substituir: true });
  toast("info", "Sessão encerrada com segurança");
});

document.addEventListener("click", (e) => {
  const botao = e.target.closest("[data-alternar-filtros]");
  if (!botao) return;
  const barra = botao.closest(".barra-filtros");
  const aberto = barra.toggleAttribute("data-expandido");
  botao.setAttribute("aria-expanded", String(aberto));
});

function monitorarConexao() {
  const atualizar = () => {
    let selo = $("#selo-offline");
    if (navigator.onLine) { selo?.remove(); return; }
    if (!selo) {
      selo = document.createElement("div");
      selo.id = "selo-offline";
      selo.className = "selo-offline";
      selo.setAttribute("role", "status");
      renderizar(selo, html`${icone("wifi_off")}Sem conexão — as alterações exigem internet`);
      document.body.appendChild(selo);
    }
  };
  window.addEventListener("online", () => { atualizar(); toast("sucesso", "Conexão restabelecida"); });
  window.addEventListener("offline", atualizar);
  atualizar();
}

async function iniciar() {
  aplicarTema(temaAtual());
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => aplicarTema(temaAtual()));
  try {
    estado.meta = await api.get("/meta");
    await carregarSessao();
  } catch (erro) {
    raiz.replaceChildren(erroTela(erro, () => location.reload()));
    return;
  }
  iniciarRoteador();
  monitorarConexao();
  await processar();
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch((e) => console.warn("Service worker não registrado", e));
  }
}

iniciar();
