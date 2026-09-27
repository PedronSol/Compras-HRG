# Compras · Hospital Rio Grande

Sistema corporativo de **compras e suprimentos** do Hospital Rio Grande. Cobre o ciclo completo com responsáveis, datas, histórico e assinatura eletrônica em cada etapa:

**Solicitação → Aprovação → Cotação → Fornecedor → Pedido de compra → Recebimento → Conclusão**

Módulos: Painel · Minhas pendências · Alertas · Solicitações · Aprovações · Cotações e mapa comparativo · Fornecedores · Pedidos de compra · Recebimento e conferência · Materiais e categorias · Relatórios e indicadores · Usuários, perfis e permissões · Histórico e auditoria.

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12+ · Flask 3 (API REST modular em `/api/v1`) · WebSocket (flask-sock) |
| Banco | PostgreSQL ≥ 15 com **Row Level Security**, máquinas de estado em triggers, auditoria imutável |
| Frontend | HTML5 + CSS3 + JavaScript puro (ES modules), PWA instalável, tema claro/escuro, fonte Inter embarcada |
| Segurança | Sessões server-side (cookie HttpOnly/SameSite=Strict), CSRF, RBAC por capacidade, Argon2id, Fernet (AES), HMAC-SHA-256, CSP estrita |
| Relatórios | ReportLab (dossiê da solicitação, pedido de compra oficial, relatório executivo) · CSV |

## Privacidade: sem IA e sem serviços externos

- O sistema **não se integra com APIs de IA** nem com serviços externos de inteligência artificial. Nenhum dado do hospital é enviado a terceiros para análise, processamento ou treinamento.
- **Orçamentos não são lidos automaticamente.** Não há OCR, visão computacional nem extração por IA. O comprador (ou o solicitante) só **anexa ou fotografa** o orçamento; fornecedor, itens, quantidades, valores, frete, desconto, prazo, validade e condições de pagamento são **digitados manualmente** e ficam vinculados ao documento para conferência.
- Os anexos são cifrados em repouso no armazenamento do próprio servidor. A consulta de senhas vazadas (HIBP) é **desativada por padrão** (`RG_HIBP_ENABLED=false`) para que nenhuma requisição saia da infraestrutura.
- O frontend não carrega nada de CDNs: fontes, ícones e scripts são servidos pelo próprio sistema.

---

## Início rápido (desenvolvimento, Windows/Linux/macOS)

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python dev.py                     # http://127.0.0.1:8000 — já com dados de demonstração
```

`dev.py` cria `backend/.env` com chaves aleatórias na primeira execução, sobe um PostgreSQL embutido (dados em `backend/.pgdata/`), aplica as migrações e carrega a **base de demonstração fictícia** na primeira vez.

| Comando | Efeito |
|---|---|
| `python dev.py` | Inicia banco + API (carrega a demonstração se o banco estiver vazio) |
| `python dev.py --recriar` | Apaga o banco de desenvolvimento e recria com dados de demonstração novos |
| `python dev.py --sem-demo` | Inicia sem dados fictícios (banco vazio) |
| `python dev.py --criar-admin` | Cria um administrador real |
| `RG_DEV_DATABASE_URL=postgresql://…` | Usa um PostgreSQL já existente em vez do embutido |

Bancos criados pela versão 1.x são detectados e recriados automaticamente com a nova estrutura.

### Versão de demonstração

Em ambientes que não são de produção (`RG_MODO_DEMO`, padrão quando `RG_AMBIENTE` ≠ `producao`), a tela inicial mostra os **8 perfis de teste** com login em um clique. Todos usam a senha `Teste@Hospital2026`:

| Perfil | Conta | Pessoa (fictícia) | O que demonstrar |
|---|---|---|---|
| Administrador | `admin@hrg.demo` | Renata Moura | Usuários, perfis e permissões, alçadas e parâmetros, setores, auditoria |
| Comprador | `comprador@hrg.demo` | Carlos Menezes | Cotação, propostas digitadas, mapa comparativo, escolha do fornecedor, emissão e envio do pedido |
| Solicitante | `solicitante@hrg.demo` | Juliana Prado (UTI Adulto) | Nova solicitação com itens do catálogo, anexar/fotografar orçamento, acompanhamento |
| Gestor | `gestor@hrg.demo` | Fernando Alves (UTI Adulto) | Aprovação, devolução e reprovação das solicitações do setor |
| Financeiro | `financeiro@hrg.demo` | Patrícia Lemos | Aprovação financeira dos pedidos, indicadores de gasto |
| Recebimento | `recebimento@hrg.demo` | Marcos Vieira | Conferência de entregas, nota fiscal, divergências e recebimento parcial |
| Diretoria | `diretoria@hrg.demo` | Helena Castro | Aprovações acima da alçada, painel executivo e relatórios |
| Auditoria | `auditoria@hrg.demo` | Roberto Nunes | Consulta somente leitura de tudo, trilha de auditoria e verificação de assinaturas |

A base fictícia tem 20 setores, 11 categorias, ~50 materiais, 16 fornecedores (CNPJs válidos gerados), 52 solicitações em todos os status, propostas, pedidos, recebimentos parciais e totais, aprovações, assinaturas válidas, alertas, notificações e eventos de auditoria. Para recarregar em um banco vazio: `python -m rg.cli semear-demo`. **Em produção o modo demonstração é recusado** e os perfis de teste não são criados.

### Rodando no VS Code

1. Instale a extensão **Python** (a recomendação aparece sozinha ao abrir a pasta).
2. `Ctrl+Shift+P` → **Tasks: Run Task** → **1. Instalar dependências (venv)** (só na primeira vez).
3. **F5** → *RG Hospital — iniciar*: sobe banco e API com depurador e abre http://127.0.0.1:8000.

Outras tarefas: **2. Iniciar plataforma (dev)**, **Recriar banco de demonstração**, **3. Criar administrador**, **Rodar testes**.

### Testes

```bash
cd backend
python -m pytest            # 29 testes: unidade + integração contra PostgreSQL real
```

A suíte cobre o fluxo completo (solicitação → aprovação → cotação → pedido → recebimento parcial e total → conclusão), alçada da Diretoria, segregação de funções, RLS por setor e perfil (inclusive via SQL direto no papel `rg_app`), valores sempre calculados no servidor, assinaturas e sua verificação criptográfica, perfil Auditoria somente leitura, limites de anexos, alertas, bloqueio por tentativas, CSRF, LGPD, relatórios PDF/CSV e cabeçalhos de segurança.

---

## Fluxo e regras

| Etapa | Responsável | Regras |
|---|---|---|
| Solicitação | Solicitante ou gestor do setor | Itens do catálogo ou descritos, quantidades e valor unitário estimado; justificativa ≥ 20 caracteres; até 5 documentos |
| Aprovação | Gestor do setor → Diretoria | O gestor não aprova a própria solicitação; solicitações abertas pelo gestor vão direto à Diretoria. Valor ≥ **alçada da Diretoria** (padrão R$ 25.000) exige a Diretoria. Devolver e reprovar exigem parecer |
| Cotação | Comprador | Propostas digitadas manualmente a partir do orçamento anexado/fotografado; mínimo de 3 propostas (configurável) |
| Fornecedor | Comprador | Mapa comparativo com menor preço por item e total. Escolher com menos propostas que o mínimo, ou fora do menor preço, exige justificativa |
| Pedido | Comprador → Financeiro → Diretoria | Itens e valores copiados da proposta vencedora (imutáveis). O Financeiro aprova; acima da alçada, também a Diretoria. Depois de aprovado, o comprador envia ao fornecedor |
| Recebimento | Recebimento | Conferência item a item com nota fiscal; quantidade recebida e aceita, motivo da divergência, fotos. Recebimento parcial mantém o saldo |
| Conclusão | Automática | Quando todos os itens são recebidos, ou quando o comprador encerra o pedido com pendência (justificado) |

Prazos de atendimento: **Imediata 3 dias · Urgente 7 dias · Normal 14 dias** (da abertura até o pedido). Alertas automáticos para prazos a vencer ou estourados e para entregas atrasadas (antecedência configurável). O administrador **não** aprova compras (segregação de funções).

### Perfis e permissões

As permissões são definidas por **capacidade** (`backend/rg/permissoes.py`) e aplicadas em três camadas: menu e rotas do frontend, API (`exigir(capacidade)`) e banco (RLS + triggers). A matriz completa aparece em **Usuários › Perfis e permissões**.

### Assinatura eletrônica

`hash = HMAC-SHA-256(RG_SIGNATURE_SECRET, solicitação | usuário | data/hora UTC | IP | hash do conteúdo | ação | status da solicitação | status do pedido | pedido | recebimento)`. O *hash do conteúdo* é o SHA-256 do estado canônico (dados, itens, anexos com seus SHA-256, propostas). Toda mudança de status exige uma assinatura na mesma transação (constraint trigger). Assinaturas, histórico, aprovações e auditoria são **imutáveis**. A verificação está disponível em cada assinatura e no dossiê PDF.

---

## Arquitetura

```
frontend/  (SPA estática: index.html, css/, js/, assets/, sw.js, manifest)
   │  fetch /api/v1/* (cookie de sessão + X-CSRF-Token)      WebSocket /ws
   ▼
backend/rg/  Flask
   ├─ api/           rotas REST por módulo (auth, usuarios, solicitacoes, aprovacoes, pedidos, fornecedores,
   │                 materiais, anexos, alertas, notificacoes, painel, auditoria, busca, meta, ws)
   ├─ permissoes.py  capacidades por perfil (fonte única para API e frontend)
   ├─ seguranca/     sessões/CSRF, senhas (Argon2id, histórico), criptografia, cabeçalhos
   ├─ servicos/      workflow, assinaturas, arquivos cifrados, PDF, painel, tempo real
   ├─ demo.py        base de demonstração fictícia
   └─ db.py          pool psycopg 3; cada transação faz SET LOCAL ROLE rg_app + contexto do usuário
   ▼
PostgreSQL  schemas rg (negócio) e audit (trilha imutável)
   ├─ RLS em todas as tabelas       solicitante/gestor → próprio setor · comprador → aprovadas ·
   │                                recebimento → com pedido · financeiro/diretoria/auditoria/admin → global
   ├─ triggers                      máquinas de estado, valores derivados, histórico, notificações, auditoria, pg_notify
   └─ LISTEN rg_eventos             → cada instância da API repassa eventos aos seus WebSockets
```

**Defesa em profundidade:** as regras são verificadas na API (mensagens claras) **e** no banco. Mesmo um SQL direto no papel da aplicação não consegue aprovar fora da alçada, aprovar a própria solicitação, alterar valores de uma proposta ou de um pedido emitido, mudar status sem assinatura na mesma transação nem ler dados de outro setor.

### LGPD

- Consentimento registrado no cadastro (data e versão do termo).
- Telefone cifrado (Fernet/AES-128-CBC + HMAC); anexos cifrados em repouso; senhas com Argon2id.
- Portabilidade: **Meu perfil › Baixar meus dados**. Eliminação: **Usuários › Anonimizar** (preserva trilhas de auditoria).
- API e WebSocket nunca são armazenados em cache pelo service worker.
- Toda leitura sensível (downloads, exportações, relatórios) gera evento de auditoria.

---

## Produção

Referência completa em [`deploy/`](deploy/): `Dockerfile`, `docker-compose.yml` (PostgreSQL 17, migrações, API com gunicorn `gthread`, Nginx com TLS e WebSocket) e `postgres/init-papeis.sh`.

```bash
cp deploy/.env.producao.example deploy/.env.producao        # preencha senhas e segredos
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.producao up -d --build
docker compose -f deploy/docker-compose.yml exec api python -m rg.cli criar-admin
```

**Papéis do banco (privilégio mínimo):** `rg_owner` é dono do schema e roda as migrações; `rg_api` é o login da API, membro de `rg_app` e **não** dono das tabelas, então o RLS sempre se aplica.

Checklist:
- HTTPS obrigatório (`RG_SESSION_COOKIE_SECURE=true`; em `RG_AMBIENTE=producao` a aplicação recusa iniciar sem isso ou com `RG_MODO_DEMO=true`).
- `RG_TRUSTED_PROXIES=1` atrás do Nginx, para registrar o IP real nas assinaturas.
- Backup do PostgreSQL **e** do volume de anexos (`/data/storage`), guardando `RG_ENCRYPTION_KEYS` em cofre separado. Sem a chave, os anexos não podem ser decifrados.
- Rotação de chave: adicione a nova chave no **início** de `RG_ENCRYPTION_KEYS` e execute `python -m rg.cli rotacionar-chaves`.
- Várias instâncias: use Redis em `RG_RATELIMIT_STORAGE_URI`. O tempo real já funciona entre instâncias via LISTEN/NOTIFY.
- Alçada da Diretoria, mínimo de propostas e antecedência dos alertas são ajustados em **Usuários › Alçadas e parâmetros** (registrado na auditoria).
- A cada nova versão do frontend, incremente `VERSAO` em `frontend/sw.js`.

### Variáveis de ambiente

Veja [`backend/.env.example`](backend/.env.example). Obrigatórias: `RG_SECRET_KEY`, `RG_SIGNATURE_SECRET`, `RG_ENCRYPTION_KEYS`, `RG_DATABASE_URL`. Para gerá-las: `python -m rg.cli gerar-chaves`.

---

## Identidade visual

Interface corporativa sóbria: navegação lateral azul-marinho, superfícies claras, tipografia **Inter** (OFL, embarcada em `frontend/assets/fontes/`), cor principal `#2E5C88`, status com cor **e** texto/ícone, contraste AA e modo escuro com tokens próprios.

O logotipo e o símbolo são **vetores sem fundo**. A geometria única está em `backend/rg/marca.py` e é usada tanto no PDF quanto na geração dos arquivos do frontend:

```bash
python scripts/gerar_marca.py   # gera frontend/assets/marca/*.svg e os ícones PWA em frontend/assets/icones/
```

## Observações

- No servidor de desenvolvimento (Werkzeug), quando o servidor encerra um WebSocket (ex.: sessão revogada), o navegador pode registrar *"Invalid frame header"* no console. É uma limitação do servidor de desenvolvimento: o cliente reconecta sozinho, e isso não ocorre com o gunicorn.
- A versão 2.0 removeu o módulo "Serviços programados" (fora do escopo de compras) e toda a leitura automática de documentos (OCR).
