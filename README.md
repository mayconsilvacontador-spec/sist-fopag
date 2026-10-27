# SIST — Sistema Integrado de Gestão de RPPS

Plataforma para gestão completa de Regimes Próprios de Previdência Social.
Instituição inicial: **PREVIBAM** — Instituto de Previdência Social dos Servidores Públicos do Município de Barra Mansa.
A arquitetura é multi-instituição desde a primeira versão.

> **Situação atual: Fase 1** — arquitetura, banco de dados, login, usuários, perfis, permissões (RBAC por módulo e ação),
> auditoria imutável, central de alertas, layout institucional e painel geral.
> Todas as demais telas do menu já existem e informam claramente **"Em desenvolvimento — Fase N"**.
> Indicadores de folha/beneficiários do painel usam dados **DEMO** (identificados em cada card) até as Fases 4 e 5.

---

## 1. Requisitos

| Componente | Versão | Observação |
|---|---|---|
| Python | 3.12 ou 3.13 | marque "Add python.exe to PATH" no instalador do Windows |
| Node.js | 20.9+ (recomendado 22 LTS) | inclui o `npm` |
| PostgreSQL | 15 ou 16 | **obrigatório** — SQLite não é suportado |
| Redis | 6+ | para Celery (tarefas assíncronas). No Windows: Docker, WSL ou Memurai |
| Git | qualquer | opcional |

Alternativa prática para PostgreSQL + Redis no Windows: **Docker Desktop** e o arquivo `docker-compose.yml` da raiz:

```powershell
docker compose up -d
```

## 2. Instalação

Estrutura esperada (pasta de trabalho, por exemplo `C:\Projetos\sist`):

```
sist\
├─ backend\    (Django + DRF)
└─ frontend\   (Next.js)
```

### 2.1 Backend (PowerShell)

```powershell
cd C:\Projetos\sist\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # se bloquear: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
copy .env.example .env
```

Edite `backend\.env`:

* `DJANGO_SECRET_KEY` — gere uma chave: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
* `DATABASE_URL` — `postgres://USUARIO:SENHA@localhost:5432/sist`
* `REDIS_URL` — `redis://localhost:6379/0`

### 2.2 Frontend (PowerShell)

```powershell
cd C:\Projetos\sist\frontend
npm install
copy .env.example .env.local
```

`frontend\.env.local` — `BACKEND_URL=http://127.0.0.1:8000` (endereço interno do Django).

## 3. Criação do banco de dados

Com Docker (`docker compose up -d`) o banco `sist` (usuário `sist`, senha `sist`) já é criado.

Sem Docker, no **SQL Shell (psql)** ou pgAdmin, como superusuário `postgres`:

```sql
CREATE USER sist WITH PASSWORD 'troque-esta-senha' CREATEDB;
CREATE DATABASE sist OWNER sist ENCODING 'UTF8';
```

> `CREATEDB` é necessário apenas para rodar os testes automatizados (o pytest cria um banco temporário).

## 4. Migrations

```powershell
cd C:\Projetos\sist\backend
.\.venv\Scripts\Activate.ps1
python manage.py migrate
python manage.py seed_initial
```

* `migrate` cria todas as tabelas, o trigger que torna a auditoria imutável e sincroniza automaticamente o catálogo de módulos/permissões e os 8 perfis de sistema.
* `seed_initial` cria a instituição PREVIBAM, os planos **Financeiro (FIN)** e **Previdenciário (PREV)**, o exercício corrente,
  a competência de referência (mês anterior; ou informe `--reference 09/2026`) e a competência seguinte.
  Dados desconhecidos (CNPJ, endereço) ficam em branco para preenchimento em *Administração › Instituição* — nada é inventado.

Opcional — alertas de demonstração (sempre marcados como DEMO):

```powershell
python manage.py seed_demo            # cria
python manage.py seed_demo --remove   # remove
```

## 5. Criação do usuário administrador

```powershell
python manage.py createmaster --username maycon --full-name "Maycon Anderson da Silva" --email seu@email.com
```

A senha é pedida no terminal (mínimo de 10 caracteres). O usuário recebe o perfil **MASTER** na PREVIBAM.
Use `--superuser` se também quiser acesso técnico ao `/django-admin/`.

## 6. Execução do backend

```powershell
cd C:\Projetos\sist\backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver 127.0.0.1:8000
```

* Saúde: http://127.0.0.1:8000/api/health/
* Documentação da API (somente com DEBUG=True): http://127.0.0.1:8000/api/docs/
* Testes automatizados: `pytest`

## 7. Execução do frontend

```powershell
cd C:\Projetos\sist\frontend
npm run dev
```

Acesse **http://localhost:3000** e entre com o usuário MASTER criado.
Build de produção: `npm run build` e `npm start`.

## 8. Configuração do Redis e do Celery

O Celery executa tarefas assíncronas (na Fase 1: verificação periódica da Central de Alertas a cada 30 minutos;
nas próximas fases: cálculo de folha, geração de arquivos, envio ao eSocial).

Em dois terminais adicionais (com o venv ativado, na pasta `backend`):

```powershell
# Worker — no Windows é obrigatório usar --pool=solo
celery -A config worker -l info --pool=solo

# Agendador (tarefas periódicas)
celery -A config beat -l info
```

Sem Redis disponível em desenvolvimento, defina `CELERY_TASK_ALWAYS_EAGER=True` no `.env`: as tarefas rodam de forma síncrona.
As verificações de alertas também podem ser executadas manualmente: `python manage.py run_alert_checks`
ou pelo botão **Executar verificações** na Central de Alertas.

Opções de Redis no Windows: `docker compose up -d` (recomendado), Redis no WSL (`sudo apt install redis-server`) ou Memurai.

## 9. Estrutura do projeto

```
sist/
├─ README.md · docker-compose.yml · .gitignore
├─ docs/
│  ├─ ARQUITETURA.md       visão geral, decisões, segurança, roadmap
│  └─ MODELO_DADOS.md      modelo relacional (Fase 1 + entidades planejadas)
├─ backend/
│  ├─ manage.py · requirements.txt · requirements-dev.txt · .env.example · pytest.ini
│  ├─ config/              settings, urls, celery, wsgi, asgi
│  ├─ apps/
│  │  ├─ core/             modelos-base (UUID, timestamps, vigência), contexto de requisição,
│  │  │                    validadores CPF/CNPJ, filtro de logs, erros padronizados, seeds
│  │  ├─ accounts/         User, Module, AccessPermission, Role, Membership; catálogo RBAC;
│  │  │                    login JWT com bloqueio por tentativas; createmaster; sync_permissions
│  │  ├─ institutions/     Institution, BenefitPlan (segregação), FiscalYear, Competence, Parameter (versionado)
│  │  ├─ audit/            AuditLog imutável (trigger PostgreSQL + hash SHA-256), sinais, exportação CSV/XLSX
│  │  ├─ alerts/           Central de Alertas, verificações automáticas, tarefas Celery
│  │  ├─ dashboard/        provedores de indicadores (real / DEMO / indisponível)
│  │  └─ search/           pesquisa global extensível por módulo
│  └─ tests/               testes de autenticação, RBAC, auditoria, parâmetros e painel
└─ frontend/
   ├─ package.json · next.config.ts · tailwind.config.ts · components.json · .env.example
   └─ src/
      ├─ middleware.ts                    redireciona quem não tem sessão
      ├─ app/(auth)/login                 tela de acesso
      ├─ app/(app)/                       telas autenticadas (layout com menu lateral e barra superior)
      │  ├─ page.tsx                      Painel Geral
      │  ├─ alertas · auditoria · perfil
      │  ├─ administracao/ usuarios · perfis · permissoes · instituicao · exercicios · competencias · parametros
      │  └─ [...slug]                     "Em desenvolvimento — Fase N" para as demais telas do menu
      ├─ app/api/auth/*                   BFF: login, logout, troca de instituição (cookies httpOnly)
      ├─ app/api/backend/[...path]        BFF: proxy autenticado para a API Django
      ├─ components/ layout · ui (shadcn) · shared · dashboard · providers
      └─ lib/ api · format (padrão brasileiro) · menu · types
```

## Comandos úteis

| Comando | Função |
|---|---|
| `python manage.py sync_permissions` | Sincroniza módulos/permissões do catálogo (`apps/accounts/catalog.py`) |
| `python manage.py sync_permissions --reset-roles` | Restaura as permissões padrão dos perfis de sistema |
| `python manage.py run_alert_checks` | Executa as verificações da Central de Alertas |
| `python manage.py seed_demo [--remove]` | Cria/remove alertas DEMO |
| `pytest` | Testes do backend |
| `npm run typecheck` / `npm run lint` | Verificações do frontend |

## Segurança — resumo

* Senhas com **Argon2**; política mínima de 10 caracteres; troca obrigatória no primeiro acesso.
* **JWT** (access 15 min / refresh 10 h com rotação e blacklist) guardado em **cookie httpOnly** pelo BFF — o JavaScript do navegador nunca acessa o token.
* **CSRF**: cookies SameSite=Lax + validação de `Origin` em toda requisição de escrita no BFF.
* **CORS** restrito às origens do `.env`. **Rate limiting** em login, refresh e pesquisa.
* Bloqueio temporário após 5 tentativas de login falhas (configurável).
* **RBAC** validado no backend em todos os endpoints; o frontend apenas oculta o que não é permitido.
* **Auditoria imutável**: UPDATE/DELETE/TRUNCATE bloqueados por trigger no PostgreSQL; hash SHA-256 por registro.
* Logs da aplicação mascaram CPF, senhas e tokens.
* Em produção: `DJANGO_DEBUG=False`, `COOKIE_SECURE=true`, HTTPS e proxy reverso (nginx/IIS) com `TRUST_PROXY_HEADERS=true`.
