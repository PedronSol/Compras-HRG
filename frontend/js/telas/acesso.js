// Telas públicas: seleção de perfil (demonstração), login, solicitação de acesso e troca obrigatória de senha.
import { api } from "../api.js";
import { estado, emitir, rotulo } from "../estado.js";
import { navegar } from "../roteador.js";
import { html, renderizar, dadosFormulario, mostrarErrosCampos, on } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { aviso, comCarregamento, opcoes, opcoesSetores, toast, vazio, ICONE_PAPEL } from "../ui/componentes.js";

function moldura(conteudo, { largo = false } = {}) {
  const etapas = estado.meta?.etapas || [];
  return html`<div class="tela-auth">
    <section class="auth-lado" aria-hidden="true">
      <img class="simbolo-fundo" src="/assets/marca/simbolo-rg-branca.svg" alt="">
      <div>
        <img class="logo-auth" src="/assets/marca/logo-rg-hospital-branca.svg" alt="">
        <h1>Compras e Suprimentos do Hospital Rio Grande</h1>
        <p class="lead">Da necessidade do setor à entrega conferida: cada solicitação com responsáveis, prazos, aprovações por alçada e histórico completo.</p>
        <div class="auth-fluxo">${etapas.map((e, i) => html`${i ? icone("seta_dir") : ""}<span>${e}</span>`)}</div>
        <ul class="auth-destaques">
          <li>${icone("carimbo")}<span><strong>Aprovação por alçada</strong>Gestor do setor, Diretoria acima do limite e Financeiro no pedido de compra.</span></li>
          <li>${icone("balanca")}<span><strong>Cotações comparadas</strong>Propostas registradas pelo comprador, com mapa de preços por item.</span></li>
          <li>${icone("escudo")}<span><strong>Dados protegidos no hospital</strong>Sem integração com serviços de IA. Assinatura eletrônica e trilha de auditoria imutável.</span></li>
        </ul>
      </div>
      <p class="auth-rodape">© ${new Date().getFullYear()} Hospital Rio Grande · Uso restrito a colaboradores autorizados</p>
    </section>
    <main class="auth-form-area" id="conteudo">
      <div class="auth-cartao ${largo ? "largo" : ""}">
        <img class="logo-mobile" src="/assets/marca/logo-rg-hospital-primaria.svg" alt="Hospital Rio Grande">
        ${conteudo}
      </div>
    </main>
  </div>`;
}

function campoSenha(nome, rotulo, { autocomplete = "current-password", ajuda = "" } = {}) {
  return html`<div class="campo"><label for="${nome}">${rotulo}<span class="obrigatorio" aria-hidden="true">*</span></label>
    <div class="campo-senha"><input id="${nome}" name="${nome}" type="password" autocomplete="${autocomplete}" required maxlength="128" ${ajuda ? html`aria-describedby="${nome}-ajuda"` : ""}>
    <button type="button" data-ver-senha aria-label="Mostrar senha" aria-pressed="false">${icone("olho")}</button></div>
    ${ajuda ? html`<p class="ajuda" id="${nome}-ajuda">${ajuda}</p>` : ""}</div>`;
}

function ativarVerSenha(raiz) {
  return on(raiz, "click", "[data-ver-senha]", (e, botao) => {
    const input = botao.parentElement.querySelector("input");
    const mostrar = input.type === "password";
    input.type = mostrar ? "text" : "password";
    botao.setAttribute("aria-pressed", String(mostrar));
    botao.setAttribute("aria-label", mostrar ? "Ocultar senha" : "Mostrar senha");
    renderizar(botao, icone(mostrar ? "olho_off" : "olho"));
  });
}

export function nivelSenha(senha) {
  let pontos = 0;
  if (senha.length >= (estado.meta?.limites?.senha_min || 12)) pontos++;
  if (senha.length >= 16) pontos++;
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(senha)).length;
  if (classes >= 3) pontos++;
  if (classes === 4) pontos++;
  return senha ? Math.max(1, pontos) : 0;
}

function ativarMedidor(raiz, nomeCampo) {
  const input = raiz.querySelector(`[name="${nomeCampo}"]`);
  const medidor = raiz.querySelector("[data-forca]");
  const texto = raiz.querySelector("[data-forca-texto]");
  input?.addEventListener("input", () => {
    const n = nivelSenha(input.value);
    medidor.dataset.nivel = n;
    texto.textContent = ["", "Fraca", "Razoável", "Boa", "Forte"][n];
  });
}

const medidorSenha = html`<div class="forca-senha" data-forca data-nivel="0" aria-hidden="true"><span></span><span></span><span></span><span></span></div>
  <p class="ajuda" aria-live="polite">Força: <span data-forca-texto>—</span></p>`;

// ------------------------------------------------------------------ escolha de perfil (demonstração)
async function entrar(email, senha, consulta = {}) {
  const r = await api.post("/auth/login", { email, senha });
  estado.usuario = r.usuario;
  estado.csrf = r.csrf_token;
  const retorno = consulta.retorno && consulta.retorno.startsWith("/") && !consulta.retorno.startsWith("//") ? consulta.retorno : "/";
  navegar(r.usuario.troca_senha_obrigatoria ? "/trocar-senha" : retorno, { substituir: true });
}

async function perfis({ raiz, consulta }) {
  const contas = estado.meta?.contas_teste || [];
  if (!contas.length) { navegar("/login", { substituir: true }); return; }
  const descricoes = estado.meta.rotulos.papel_descricao;
  renderizar(raiz, moldura(html`
    <div>
      <span class="selo-demo">${icone("sparkle")}Ambiente de demonstração · dados 100% fictícios</span>
      <h2>Escolha um perfil para explorar</h2>
      <p class="sub">Cada perfil vê e executa apenas o que lhe compete no fluxo de compras. Troque de perfil a qualquer momento pelo menu do usuário.</p>
    </div>
    <div id="aviso-login" aria-live="assertive"></div>
    <div class="perfis-demo">
      ${contas.map((c) => html`<button type="button" class="perfil-demo" data-papel="${c.papel}" data-email="${c.email}" data-senha="${c.senha}">
        <span class="icone-perfil">${icone(ICONE_PAPEL[c.papel] || "perfil")}</span>
        <span><strong>${rotulo("papel", c.papel)}</strong><span class="nome-perfil">${c.nome} · ${c.cargo}</span><p>${descricoes[c.papel]}</p></span>
      </button>`)}
    </div>
    <p class="pequeno texto-3">Senha de todos os perfis de demonstração: <code>${contas[0].senha}</code> · <a href="/login">Entrar com e-mail e senha</a></p>`, { largo: true }));
  on(raiz, "click", "[data-email]", async (e, b) => {
    b.setAttribute("aria-busy", "true");
    raiz.querySelectorAll(".perfil-demo").forEach((x) => { x.disabled = true; });
    try {
      await entrar(b.dataset.email, b.dataset.senha, consulta);
      toast("info", `Você entrou como ${rotulo("papel", b.dataset.papel)}`, "Ambiente de demonstração com dados fictícios.");
    } catch (erro) {
      raiz.querySelectorAll(".perfil-demo").forEach((x) => { x.disabled = false; });
      renderizar(raiz.querySelector("#aviso-login"), aviso("perigo", erro.message));
    }
  });
}

// ------------------------------------------------------------------ login
async function login({ raiz, consulta }) {
  const demo = (estado.meta?.contas_teste || []).length > 0;
  renderizar(raiz, moldura(html`
    <div><h2>Acessar o sistema de Compras</h2>
    <p class="sub">Use seu e-mail institucional e senha.</p></div>
    <div class="auth-painel">
      <div id="aviso-login" aria-live="assertive"></div>
      <form id="form-login" class="pilha" novalidate>
        <div class="campo"><label for="email">E-mail institucional<span class="obrigatorio" aria-hidden="true">*</span></label>
          <input id="email" name="email" type="email" autocomplete="username" required inputmode="email" autofocus value="${consulta.email || ""}"></div>
        ${campoSenha("senha", "Senha")}
        <button class="botao bloco grande" type="submit">${icone("cadeado")}Entrar</button>
      </form>
      ${demo ? html`<a class="botao secundario bloco" href="/perfis">${icone("usuarios")}Escolher um perfil de demonstração</a>` : ""}
    </div>
    <p class="pequeno texto-3">Ainda não tem acesso? <a href="/cadastro">Solicite seu cadastro</a>. Esqueceu a senha? O Administrador do sistema redefine com segurança.</p>
    <p class="nota-privacidade">${icone("escudo")}<span>Conexão protegida, sessão com expiração automática e registro de acessos. Nenhum dado é enviado a serviços externos de inteligência artificial.</span></p>`));
  const form = raiz.querySelector("#form-login");
  ativarVerSenha(form);
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const dados = dadosFormulario(form);
    const erros = {};
    if (!dados.email) erros.email = "Informe seu e-mail";
    if (!form.senha.value) erros.senha = "Informe sua senha";
    mostrarErrosCampos(form, erros);
    if (Object.keys(erros).length) return;
    const botao = form.querySelector('button[type="submit"]');
    try {
      await comCarregamento(botao, entrar(dados.email, form.senha.value, consulta));
    } catch (erro) {
      form.senha.value = "";
      const tipo = erro.status === 423 || erro.codigo?.startsWith("conta_") ? "alerta" : "perigo";
      renderizar(raiz.querySelector("#aviso-login"), aviso(tipo, erro.message));
      if (Object.keys(erro.campos).length) mostrarErrosCampos(form, erro.campos);
      else form.senha.focus();
    }
  });
}

// ------------------------------------------------------------------ cadastro
async function cadastro({ raiz }) {
  const setores = estado.meta.setores;
  renderizar(raiz, moldura(html`
    <div><h2>Solicitar acesso</h2>
    <p class="sub">Seu cadastro será analisado pelo Administrador do sistema antes da liberação.</p></div>
    <div id="aviso-cadastro" aria-live="assertive"></div>
    <form id="form-cadastro" class="form-grade auth-painel" novalidate>
      <div class="campo"><label for="nome">Nome completo<span class="obrigatorio" aria-hidden="true">*</span></label>
        <input id="nome" name="nome" autocomplete="name" required minlength="3" maxlength="120"></div>
      <div class="campo"><label for="email">E-mail institucional<span class="obrigatorio" aria-hidden="true">*</span></label>
        <input id="email" name="email" type="email" autocomplete="email" required></div>
      <div class="campo col-6"><label for="papel">Perfil de acesso<span class="obrigatorio" aria-hidden="true">*</span></label>
        <select id="papel" name="papel" required>${opcoes({ solicitante: "Solicitante", gestor: "Gestor de setor", comprador: "Comprador", financeiro: "Financeiro", recebimento: "Recebimento" }, "solicitante")}</select></div>
      <div class="campo col-6"><label for="setor_codigo">Setor<span class="obrigatorio" aria-hidden="true">*</span></label>
        <select id="setor_codigo" name="setor_codigo" required>${opcoesSetores(setores, "", { vazio: "Selecione…", somenteOperacionais: true })}</select></div>
      <div class="campo col-6"><label for="cargo">Cargo</label><input id="cargo" name="cargo" maxlength="80" autocomplete="organization-title"></div>
      <div class="campo col-6"><label for="telefone">Telefone</label><input id="telefone" name="telefone" type="tel" inputmode="tel" autocomplete="tel" maxlength="20" placeholder="(51) 99999-9999"></div>
      ${campoSenha("senha", "Senha", { autocomplete: "new-password", ajuda: `Mínimo de ${estado.meta.limites.senha_min} caracteres, combinando maiúsculas, minúsculas, números e símbolos.` })}
      <div>${medidorSenha}</div>
      <div class="campo"><label for="confirmacao">Confirme a senha<span class="obrigatorio" aria-hidden="true">*</span></label>
        <input id="confirmacao" name="confirmacao" type="password" autocomplete="new-password" required maxlength="128"></div>
      <div class="campo" data-campo="consentimento"><label class="checkbox"><input type="checkbox" name="consentimento" required>
        <span>Declaro ciência de que meus dados pessoais (nome, e-mail, telefone, setor e registros de acesso) serão tratados pelo Hospital Rio Grande
        exclusivamente para controle de acesso, rastreabilidade e cumprimento de obrigações legais, conforme a LGPD (Lei 13.709/2018).
        Posso solicitar acesso, correção, portabilidade ou eliminação pelo meu perfil ou junto ao Encarregado de Dados.</span></label></div>
      <button class="botao bloco" type="submit">${icone("enviar")}Enviar solicitação de acesso</button>
    </form>
    <hr><p class="pequeno texto-3">Já possui acesso? <a href="/login">Entrar</a></p>`));
  const form = raiz.querySelector("#form-cadastro");
  ativarVerSenha(form);
  ativarMedidor(form, "senha");
  const papel = form.querySelector("#papel");
  const setor = form.querySelector("#setor_codigo");
  papel.addEventListener("change", () => {
    const operacionais = ["gestor", "solicitante"].includes(papel.value);
    const padrao = { comprador: "suprimentos", recebimento: "suprimentos", financeiro: "financeiro" }[papel.value] || "";
    renderizar(setor, opcoesSetores(setores, padrao, { vazio: "Selecione…", somenteOperacionais: operacionais }));
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const dados = dadosFormulario(form);
    dados.senha = form.senha.value;
    const erros = {};
    if ((dados.nome || "").length < 3) erros.nome = "Informe o nome completo";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(dados.email || "")) erros.email = "Informe um e-mail válido";
    if (!dados.setor_codigo) erros.setor_codigo = "Selecione o setor";
    if (dados.senha.length < estado.meta.limites.senha_min) erros.senha = `A senha deve ter no mínimo ${estado.meta.limites.senha_min} caracteres`;
    if (dados.senha !== form.confirmacao.value) erros.confirmacao = "As senhas não conferem";
    if (!dados.consentimento) erros.consentimento = "É necessário aceitar o termo para prosseguir";
    mostrarErrosCampos(form, erros);
    if (Object.keys(erros).length) return;
    delete dados.confirmacao;
    try {
      const r = await comCarregamento(form.querySelector('button[type="submit"]'), api.post("/auth/cadastro", dados));
      renderizar(raiz.querySelector(".auth-cartao"), html`
        <img class="logo-mobile" src="/assets/marca/logo-rg-hospital-primaria.svg" alt="Hospital Rio Grande">
        <div class="auth-painel">${vazio("Solicitação enviada", r.mensagem, html`<a class="botao" href="/login">Voltar para o login</a>`, "check_circulo")}</div>`);
    } catch (erro) {
      renderizar(raiz.querySelector("#aviso-cadastro"), aviso("perigo", erro.message));
      mostrarErrosCampos(form, erro.campos);
    }
  });
}

// ------------------------------------------------------------------ troca obrigatória
async function trocarSenha({ raiz }) {
  renderizar(raiz, moldura(html`
    <div><h2>Defina uma nova senha</h2>
    <p class="sub">Por segurança, substitua a senha temporária antes de continuar.</p></div>
    <div id="aviso-troca" aria-live="assertive"></div>
    <form id="form-troca" class="pilha auth-painel" novalidate>
      ${campoSenha("senha_atual", "Senha atual (temporária)")}
      ${campoSenha("nova_senha", "Nova senha", { autocomplete: "new-password", ajuda: "Não é permitido reutilizar nenhuma das últimas 5 senhas." })}
      ${medidorSenha}
      <div class="campo"><label for="confirmacao">Confirme a nova senha<span class="obrigatorio" aria-hidden="true">*</span></label>
        <input id="confirmacao" name="confirmacao" type="password" autocomplete="new-password" required></div>
      <button class="botao bloco" type="submit">${icone("chave")}Salvar nova senha</button>
      <button class="botao fantasma bloco" type="button" data-sair>Sair</button>
    </form>`));
  const form = raiz.querySelector("#form-troca");
  ativarVerSenha(form);
  ativarMedidor(form, "nova_senha");
  form.querySelector("[data-sair]").addEventListener("click", () => emitir("sair"));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (form.nova_senha.value !== form.confirmacao.value) { mostrarErrosCampos(form, { confirmacao: "As senhas não conferem" }); return; }
    try {
      await comCarregamento(form.querySelector('button[type="submit"]'),
        api.post("/auth/senha", { senha_atual: form.senha_atual.value, nova_senha: form.nova_senha.value }));
      estado.usuario.troca_senha_obrigatoria = false;
      toast("sucesso", "Senha atualizada", "Bem-vindo(a) ao sistema de Compras.");
      navegar("/", { substituir: true });
    } catch (erro) {
      renderizar(raiz.querySelector("#aviso-troca"), aviso("perigo", erro.message));
      mostrarErrosCampos(form, erro.campos);
    }
  });
}

export const telas = { perfis, login, cadastro, trocarSenha };
export { campoSenha, ativarVerSenha, ativarMedidor, medidorSenha };
