# Atualização do SIFAB para a versão atual do SIST FOPAG — guia para o TI

Repositório: https://github.com/mayconsilvacontador-spec/sist-fopag (ramo `main`).
Stack: backend Django 5.2 + DRF (PostgreSQL 16, Redis 7) e frontend Next.js 15 (BFF em `/api/backend`).
Instalação completa do zero: ver `README.md`. Este guia trata da **atualização** de um ambiente que já roda.

> Observação: o SIFAB publicado parece usar comandos com nomes próprios (ex.: a tela de rubricas sugere
> `sifab_seed_payroll`). Os comandos abaixo são os deste repositório; se o SIFAB for um port/fork, use o
> equivalente de lá.

## 0. Já instalou a versão anterior do GitHub (commit `7edda52`)? Faça só isto

A atualização seguinte (commit `0e12d7c`) mexe **apenas no frontend** (8 arquivos: menu reorganizado, tela
"Como fazer", tela única "Suspender, cessar ou reverter", eSocial › Eventos completo, `next.config.ts` sem cache
em disco). **Não há migração, dependência nova nem variável nova.**

```bash
git pull origin main
cd frontend && npm ci && npm run build   # depois reiniciar o serviço do frontend
```

Atenção — no SIFAB publicado (conferido em 27/10/2026) **não aparecia o menu "Folha de Ativos"** (a rota
`/ativos/folhas` dava 404) e estavam **vazios** rubricas, parâmetros, regras de aposentadoria, exercícios e
competências. Tudo isso já existia no commit `7edda52`. Conferir:

- se `python manage.py migrate` foi rodado (app `pessoal` = Folha de Ativos);
- se `python manage.py sync_permissions` foi rodado (sem ele o menu dos módulos novos fica escondido);
- se o frontend publicado é o deste repositório (a rota `frontend/src/app/(app)/ativos/` existe aqui);
- as cargas iniciais da seção 3 (rubricas, IR, alíquotas, regras, teto, salário mínimo).

## 1. Antes de começar

1. **Backup do banco** (`pg_dump -Fc`) e da pasta de arquivos enviados (`MEDIA_ROOT`).
2. Avise os usuários: a atualização roda migrações e reinicia o sistema.

## 2. Backend

```bash
git pull origin main
pip install -r backend/requirements.txt
```

Dependências novas desde a versão publicada: `cryptography`, `requests`, `anthropic`, `pymupdf`, `openpyxl`,
`python-docx`, `lxml`.

**Pacotes do sistema operacional** (leitura de PDFs digitalizados por OCR, sem custo):
`tesseract-ocr` e `tesseract-ocr-por`, com `TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata`
(já estão no `backend/Dockerfile`; se usar Docker, basta reconstruir a imagem).

**Variáveis novas no `.env` do backend** (ver `backend/.env.example`):

| Variável | Para quê | Como gerar |
|---|---|---|
| `ESOCIAL_CERT_KEY` | criptografa o certificado A1 do eSocial guardado no banco | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SIST_SECRETS_KEY` | criptografa a chave da API de leitura inteligente (opcional) | mesmo comando, chave diferente |

Guarde as chaves fora do banco e do repositório. Trocar a chave depois obriga a reenviar o certificado/chave.
O `.env` deve ser UTF-8 **sem BOM**.

Depois:

```bash
python manage.py migrate
python manage.py sync_permissions          # inclui os módulos novos no catálogo de permissões
```

`sync_permissions` só dá os módulos novos ao perfil MASTER. Para os perfis de sistema (Folha, Benefícios...)
receberem os novos módulos, ou se dá a permissão pela tela Administração › Perfis, ou se roda
`python manage.py sync_permissions --reset-roles` (atenção: sobrescreve personalizações dos perfis de sistema).

## 3. Cargas iniciais (rodar uma vez; trocar PREVIBAM pela sigla da instituição)

No SIFAB estavam vazios: rubricas, parâmetros, regras de aposentadoria, exercícios e competências.

```bash
python manage.py seed_payroll    --institution PREVIBAM                     # rubricas, tabela do IRRF, alíquota 14%, margem
python manage.py seed_rules      --institution PREVIBAM --reforma 2025-06-15 # regras de aposentadoria + teto RGPS e salário mínimo
python manage.py seed_financeiro --institution PREVIBAM                     # alíquota patronal e dia de vencimento
python manage.py seed_esocial    --institution PREVIBAM                     # sugestão de incidências das rubricas
python manage.py fill_base_salary --institution PREVIBAM --dry-run          # vencimento dos servidores importados (confira e rode sem --dry-run)
```

Valores carregados são SUGESTÕES a conferir com a legislação (IRRF 2026, salário mínimo/teto, alíquotas antigas).

## 4. Frontend

```bash
cd frontend
npm ci
npm run build
# reiniciar o serviço (next start)
```

Variáveis do frontend (`frontend/.env.example`): `BACKEND_URL`, `ALLOWED_ORIGINS` (endereços pelos quais os
usuários acessam — escritas de outra origem são recusadas), `TRUST_PROXY_HEADERS`, `COOKIE_SECURE=true` em HTTPS.
O `next.config.ts` agora desliga o cache do webpack em disco (build um pouco mais lento, sem a pasta de ~900 MB).

## 5. O que muda para os usuários (resumo)

- **Folha de Ativos** (menu novo): tabela de vencimentos, rubricas, lançamentos, folha por órgão, contracheque,
  ficha financeira (importação do sistema anterior) e controle da contribuição descontada × devida × repassada.
- **Servidores › Pasta do Servidor**: admissão completa, ficha imprimível, foto, linha do tempo, documentos em pastas;
  tabela padrão de importação de servidores (Excel).
- **Arrecadação › Alíquotas**: alíquotas do servidor e patronal com vigência (inclusive históricas).
- **Menu reorganizado**: seções por rotina; telas repetidas retiradas do menu (continuam pela pesquisa);
  Folha mensal faz o ciclo inteiro; eSocial › Eventos com tudo; tela "Como fazer (passo a passo)".
- **Leitura inteligente** de processos em PDF (OCR local gratuito ou API paga, opcional).
- **eSocial**: transmissão direta com certificado A1 (opcional).

## 6. Conferência depois da atualização

- [ ] Login funciona; menu "Folha de Ativos" aparece para o MASTER.
- [ ] Administração › Parâmetros mostra `irrf.tabela`, `folha.aliquota_segurado`, `rgps.teto`, `salario_minimo`.
- [ ] Gestão Previdenciária › Regras de aposentadoria lista as regras.
- [ ] Administração › Exercícios: abrir o exercício do ano; Folha de Benefícios › Rubricas lista as rubricas.
- [ ] Cadastros › Órgãos: preencher o código SIGFIS (necessário para o SalContr.txt do TCE-RJ).
- [ ] Gestão Financeira › Contas da instituição: cadastrar a conta pagadora de cada plano.
- [ ] Testes automáticos (opcional, com banco de teste): `pytest` na pasta `backend`.

O arquivo CNAB 240 gerado é o padrão FEBRABAN genérico: **homologar com o banco** antes de pagar de verdade.
