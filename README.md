# RG Hospital — Plataforma Corporativa

Plataforma do **Hospital Rio Grande** para solicitações de compras, orçamentos e contratação de serviços, com aprovação em três níveis, assinatura eletrônica, serviços programados, OCR de documentos, auditoria completa, painel executivo e relatórios em PDF.

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12+ · Flask 3 (API REST modular em `/api/v1`) · WebSocket (flask-sock) |
| Banco | PostgreSQL ≥ 15 com **Row Level Security**, triggers de workflow, SLA e auditoria |
| Frontend | HTML5 + CSS3 + JavaScript puro (ES modules), PWA instalável, tema claro/escuro |
| Segurança | Sessões server-side (cookie HttpOnly/SameSite=Strict), CSRF, RBAC, Argon2id, Fernet (AES), HMAC-SHA-256, CSP estrita |
| Relatórios | ReportLab (PDF institucional com logotipo vetorial e código de verificação) |
| OCR | Camada de texto de PDF (pypdfium2) → Tesseract `por` (se instalado) → RapidOCR (ONNX, embutido) |

---

## Início rápido (desenvolvimento, Windows/Linux/macOS)

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python dev.py --criar-admin       # sobe um PostgreSQL embutido, migra e cria o 1º administrador
python dev.py                     # http://127.0.0.1:8000
```

`dev.py` cria `backend/.env` com chaves aleatórias na primeira execução e mantém os dados do PostgreSQL de desenvolvimento em `backend/.pgdata/`. Novos usuários se cadastram em **/cadastro** e ficam **pendentes** até a aprovação do administrador em **Usuários e acessos**.

### Rodando no VS Code

1. Instale a extensão **Python** (a recomendação aparece sozinha ao abrir a pasta).
2. `Ctrl+Shift+P` → **Tasks: Run Task** → **1. Instalar dependências (venv)** (só na primeira vez; cria a `.venv` e instala tudo).
3. `Ctrl+Shift+P` → **Tasks: Run Task** → **3. Criar administrador** (só na primeira vez).
4. **F5** → *RG Hospital — iniciar*: sobe banco e API com depurador e abre http://127.0.0.1:8000.

Sem depurador, use a tarefa **2. Iniciar plataforma (dev)**. Os testes aparecem no painel **Testing** (frasco) ou pela tarefa **Rodar testes** (`Ctrl+Shift+P` → *Tasks: Run Test Task*).

Se o interpretador não for detectado: `Ctrl+Shift+P` → **Python: Select Interpreter** → `.venv\Scripts\python.exe`.

### Testes

```bash
cd backend
python -m pytest            # 24 testes: unidade + integração contra PostgreSQL 17 real
```

A suíte cobre o workflow completo, RLS por setor/papel (inclusive via SQL direto no papel `rg_app`), máquina de estados, assinaturas e sua verificação criptográfica, OCR (NF-e com chave de acesso, orçamento e laudo), limites de anexos, SLA e alertas, bloqueio por tentativas, histórico de senhas, CSRF, LGPD (exportação e anonimização), relatórios PDF/CSV e cabeçalhos de segurança.

---

## Arquitetura

```
frontend/  (SPA estática: index.html, css/, js/, sw.js, manifest)
   │  fetch /api/v1/* (cookie de sessão + X-CSRF-Token)      WebSocket /ws
   ▼
backend/rg/  Flask
   ├─ api/           rotas REST por módulo (auth, usuarios, solicitacoes, anexos, fornecedores,
   │                 servicos, notificacoes, painel, auditoria, busca, ws)
   ├─ seguranca/     sessões/CSRF/RBAC, senhas (Argon2id, histórico, HIBP), criptografia, cabeçalhos
   ├─ servicos/      workflow, assinaturas, arquivos cifrados, OCR, PDF, painel, tempo real
   └─ db.py          pool psycopg 3; cada transação faz SET LOCAL ROLE rg_app + contexto do usuário
   ▼
PostgreSQL  schemas rg (negócio) e audit (trilha imutável)
   ├─ RLS em todas as tabelas       gestor → próprio setor · compras → liberadas pelo ADM · admin → global
   ├─ triggers                      máquina de estados, SLA, histórico, notificações, auditoria, pg_notify
   └─ LISTEN rg_eventos             → cada instância da API repassa eventos aos seus WebSockets
```

**Defesa em profundidade:** as regras de negócio são verificadas na API (mensagens claras) **e** no banco. Mesmo um SQL direto no papel da aplicação não consegue aprovar uma solicitação sem ser administrador, alterar uma solicitação após a liberação sem ser Compras, homologar sem cotação vencedora, mudar status sem assinatura digital na mesma transação, nem ler dados de outro setor.

### Workflow

| Etapa | Quem | Ações | Assinatura |
|---|---|---|---|
| 1 | Gestor do setor | Cria (justificativa ≥ 20 caracteres, até 3 anexos), reenvia após nova cotação, cancela | Submissão / reenvio |
| 2 | Administração | Aprova, rejeita, solicita nova cotação, altera urgência (com justificativa; SLA recalculado) | Todas as decisões |
| 3 | Compras | Inicia cotação, cadastra fornecedores e propostas (preenchimento por OCR), homologa ou rejeita | Homologação / rejeição |

SLA: **Imediato 3 dias · Urgente 7 dias · Normal 14 dias** (corridos, desde a abertura). Situações: dentro do prazo, alerta (< 24 h) e estourado, com notificações automáticas de alerta e estouro.

### Assinatura eletrônica

`hash_autenticidade = HMAC-SHA-256(RG_SIGNATURE_SECRET, solicitação | usuário | data/hora UTC | IP | hash do conteúdo | ação | status)`. O *hash do conteúdo* é o SHA-256 do estado canônico da solicitação (dados, anexos com seus SHA-256 e cotações). Assinaturas, histórico e auditoria são **imutáveis** (triggers bloqueiam UPDATE/DELETE). A verificação está disponível em cada assinatura e no dossiê PDF.

### LGPD

- Consentimento registrado no cadastro (data e versão do termo).
- Telefone cifrado (Fernet/AES-128-CBC + HMAC); anexos cifrados em repouso; senhas com Argon2id.
- Portabilidade: **Meu perfil › Baixar meus dados**. Eliminação: **Usuários › Anonimizar** (preserva trilhas de auditoria).
- API e WebSocket nunca são armazenados em cache pelo service worker.
- Toda leitura sensível (downloads, exportações, relatórios) gera evento de auditoria.

---

## Produção

Referência completa em [`deploy/`](deploy/): `Dockerfile` (Python + Tesseract `por`), `docker-compose.yml` (PostgreSQL 17, migrações, API com gunicorn `gthread`, Nginx com TLS e WebSocket) e `postgres/init-papeis.sh`.

```bash
cp deploy/.env.producao.example deploy/.env.producao        # preencha senhas e segredos
docker compose -f deploy/docker-compose.yml --env-file deploy/.env.producao up -d --build
docker compose -f deploy/docker-compose.yml exec api python -m rg.cli criar-admin
```

**Papéis do banco (privilégio mínimo):** `rg_owner` é dono do schema e roda as migrações; `rg_api` é o login da API, membro de `rg_app` e **não** dono das tabelas, então o RLS sempre se aplica.

Checklist:
- HTTPS obrigatório (`RG_SESSION_COOKIE_SECURE=true`; em `RG_AMBIENTE=producao` a aplicação recusa iniciar sem isso).
- `RG_TRUSTED_PROXIES=1` atrás do Nginx, para registrar o IP real nas assinaturas.
- Backup do PostgreSQL **e** do volume de anexos (`/data/storage`), guardando `RG_ENCRYPTION_KEYS` em cofre separado. Sem a chave, os anexos não podem ser decifrados.
- Rotação de chave: adicione a nova chave no **início** de `RG_ENCRYPTION_KEYS` e execute `python -m rg.cli rotacionar-chaves`.
- Várias instâncias: use Redis em `RG_RATELIMIT_STORAGE_URI`. O tempo real já funciona entre instâncias via LISTEN/NOTIFY.
- A cada nova versão do frontend, incremente `VERSAO` em `frontend/sw.js`.

### Variáveis de ambiente

Veja [`backend/.env.example`](backend/.env.example). Obrigatórias: `RG_SECRET_KEY`, `RG_SIGNATURE_SECRET`, `RG_ENCRYPTION_KEYS`, `RG_DATABASE_URL`. Para gerá-las: `python -m rg.cli gerar-chaves`.

---

## Identidade visual

Cores: `#2E5C88` (principal), `#8EB7E5` (destaque), `#2FA84F` (sucesso), `#F7F9FC` (fundo), com tokens próprios para o modo escuro e contraste AA.

O logotipo e o símbolo foram redesenhados como **vetores sem fundo** a partir das imagens fornecidas. A geometria única está em `backend/rg/marca.py` e é usada tanto no PDF quanto na geração dos arquivos do frontend:

```bash
python scripts/gerar_marca.py   # gera frontend/assets/marca/*.svg e os ícones PWA em frontend/assets/icones/
```

Variantes disponíveis: `logo-rg-hospital.svg` (azul destaque, como no original), `-primaria.svg` e `-branca.svg`, além do símbolo isolado nas mesmas cores.

## Observações

- No servidor de desenvolvimento (Werkzeug), quando o servidor encerra um WebSocket (ex.: sessão revogada), o navegador pode registrar *"Invalid frame header"* no console. É uma limitação do servidor de desenvolvimento: o cliente reconecta sozinho, e isso não ocorre com o gunicorn.
- O OCR usa primeiro a camada de texto do PDF, que é exata. Para digitalizações, a qualidade é maior com o Tesseract `por` instalado (já incluído na imagem Docker; no Windows, informe `RG_TESSERACT_CMD`). Sem ele, a plataforma usa o RapidOCR embutido.
