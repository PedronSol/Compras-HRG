// Perfil do usuário: dados pessoais, troca de senha, sessões ativas e direitos do titular (LGPD).
import { api } from "../api.js";
import { estado, rotulo } from "../estado.js";
import { html, renderizar, on, dadosFormulario, mostrarErrosCampos } from "../ui/dom.js";
import { icone } from "../ui/icones.js";
import { aviso, comCarregamento, confirmar, formato, toast, toastErro } from "../ui/componentes.js";
import { ativarMedidor, ativarVerSenha, campoSenha, medidorSenha } from "./acesso.js";

function descreverDispositivo(ua = "") {
  const nav = /Edg\//.test(ua) ? "Edge" : /Chrome\//.test(ua) ? "Chrome" : /Firefox\//.test(ua) ? "Firefox" : /Safari\//.test(ua) ? "Safari" : "Navegador";
  const so = /Windows/.test(ua) ? "Windows" : /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Mac OS/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "";
  return `${nav}${so ? ` · ${so}` : ""}`;
}

export async function montar({ raiz }) {
  const [p, sessoes] = await Promise.all([api.get("/auth/perfil"), api.get("/auth/sessoes")]);
  renderizar(raiz, html`
    <div class="cabecalho-pagina"><div class="titulos"><h1>Meu perfil e segurança</h1><p>${rotulo("papel", p.papel)} · ${p.setor_nome}</p></div></div>
    <div class="grade-2">
      <section class="cartao" aria-labelledby="t-dados"><div class="cartao-cabecalho"><h2 id="t-dados">Dados pessoais</h2></div>
        <form id="f-perfil" class="cartao-corpo form-grade" novalidate>
          <div class="campo"><label for="p-nome">Nome completo</label><input id="p-nome" name="nome" value="${p.nome}" required minlength="3" maxlength="120" autocomplete="name"></div>
          <div class="campo"><label for="p-email">E-mail</label><input id="p-email" value="${p.email}" disabled aria-describedby="p-email-ajuda"><p class="ajuda" id="p-email-ajuda">Alterações de e-mail, perfil ou setor são feitas pela Administração.</p></div>
          <div class="campo col-6"><label for="p-cargo">Cargo</label><input id="p-cargo" name="cargo" value="${p.cargo ?? ""}" maxlength="80"></div>
          <div class="campo col-6"><label for="p-tel">Telefone</label><input id="p-tel" name="telefone" type="tel" value="${p.telefone ?? ""}" maxlength="20" autocomplete="tel"></div>
          <div><button class="botao" type="submit">${icone("check")}Salvar dados</button></div>
        </form></section>
      <section class="cartao" aria-labelledby="t-senha"><div class="cartao-cabecalho"><h2 id="t-senha">Alterar senha</h2><span class="subtitulo">Última alteração: ${formato.dataHora(p.senha_alterada_em)}</span></div>
        <form id="f-senha" class="cartao-corpo pilha" novalidate>
          ${campoSenha("senha_atual", "Senha atual")}
          ${campoSenha("nova_senha", "Nova senha", { autocomplete: "new-password", ajuda: `Mínimo de ${estado.meta.limites.senha_min} caracteres; as últimas 5 senhas não podem ser reutilizadas; senhas vazadas são recusadas.` })}
          ${medidorSenha}
          <div class="campo"><label for="confirmacao">Confirme a nova senha</label><input id="confirmacao" name="confirmacao" type="password" autocomplete="new-password"></div>
          <button class="botao" type="submit">${icone("chave")}Alterar senha</button>
        </form></section>
    </div>
    <section class="cartao" aria-labelledby="t-sessoes"><div class="cartao-cabecalho"><h2 id="t-sessoes">Sessões ativas</h2><span class="subtitulo">Encerre sessões em dispositivos que você não reconhece.</span></div>
      <ul class="lista-simples" id="lista-sessoes">${sessoes.itens.map((s) => html`<li>${icone("monitor")}<span class="quebra"><strong>${descreverDispositivo(s.user_agent)}</strong>${s.atual ? html` <span class="badge sucesso">Esta sessão</span>` : ""}<br>
        <span class="minusculo texto-3">IP ${s.ip} · iniciada ${formato.dataHora(s.criado_em)} · último acesso ${formato.relativo(s.ultimo_acesso_em)}</span></span>
        <span class="espacador"></span>${s.atual ? "" : html`<button class="botao secundario pequeno" data-encerrar="${s.id}">Encerrar</button>`}</li>`)}</ul></section>
    <section class="cartao" aria-labelledby="t-lgpd"><div class="cartao-cabecalho"><h2 id="t-lgpd">Privacidade e LGPD</h2></div>
      <div class="cartao-corpo pilha">
        <p class="texto-2">Consentimento registrado em ${formato.dataHora(p.consentimento_lgpd_em)} (termo versão ${p.consentimento_versao || "—"}). Telefone armazenado com criptografia AES.</p>
        ${aviso("info", "Seus direitos", "Você pode obter uma cópia dos seus dados pessoais a qualquer momento. Para correção de dados administrativos ou eliminação, contate a Administração / Encarregado de Dados.")}
        <div><button class="botao secundario" data-exportar>${icone("download")}Baixar meus dados (JSON)</button></div>
      </div></section>`);

  const formPerfil = raiz.querySelector("#f-perfil");
  formPerfil.addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = dadosFormulario(formPerfil);
    try {
      const novo = await comCarregamento(formPerfil.querySelector("button"), api.patch("/auth/perfil", d));
      estado.usuario.nome = novo.nome;
      toast("sucesso", "Dados atualizados");
    } catch (err) { mostrarErrosCampos(formPerfil, err.campos); toastErro(err); }
  });

  const formSenha = raiz.querySelector("#f-senha");
  ativarVerSenha(formSenha);
  ativarMedidor(formSenha, "nova_senha");
  formSenha.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (formSenha.nova_senha.value !== formSenha.confirmacao.value) { mostrarErrosCampos(formSenha, { confirmacao: "As senhas não conferem" }); return; }
    try {
      const r = await comCarregamento(formSenha.querySelector('button[type="submit"]'),
        api.post("/auth/senha", { senha_atual: formSenha.senha_atual.value, nova_senha: formSenha.nova_senha.value }));
      formSenha.reset();
      toast("sucesso", "Senha alterada", r.mensagem);
    } catch (err) { mostrarErrosCampos(formSenha, err.campos); toastErro(err); }
  });

  on(raiz, "click", "[data-encerrar]", async (e, b) => {
    const r = await confirmar({ titulo: "Encerrar sessão", mensagem: "O dispositivo será desconectado imediatamente.", rotuloConfirmar: "Encerrar", tom: "perigo" });
    if (!r.confirmado) return;
    try { await api.delete(`/auth/sessoes/${b.dataset.encerrar}`); b.closest("li").remove(); toast("sucesso", "Sessão encerrada"); } catch (err) { toastErro(err); }
  });
  raiz.querySelector("[data-exportar]").addEventListener("click", (e) => {
    comCarregamento(e.currentTarget, api.baixar("/auth/meus-dados", null, { nomePadrao: "meus-dados-rg-hospital.json" })).catch(toastErro);
  });
}
