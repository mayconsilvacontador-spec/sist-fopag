# SIST — Arquitetura

## 1. Visão geral

```
Navegador ──► Next.js (mesma origem)
               ├─ páginas (App Router, TypeScript, Tailwind, shadcn/ui, Recharts)
               └─ BFF  /api/auth/*  e  /api/backend/*  ──Bearer JWT──►  Django REST Framework
                    tokens em cookie httpOnly                             ├─ PostgreSQL (base única)
                                                                          ├─ Redis ◄─► Celery (worker + beat)
                                                                          └─ armazenamento de arquivos (Fase 2)
```

Princípio central: **uma única base de dados**. Cada informação é digitada uma vez e referenciada pelos módulos
seguintes (segurado → vínculo → históricos → processo → concessão → folha → eSocial → pagamento → contabilidade → relatórios).

## 2. Decisões de arquitetura

| Tema | Decisão | Motivo |
|---|---|---|
| Separação | `frontend/` e `backend/` independentes | Deploy e evolução separados; a API serve também ao futuro Portal do Segurado |
| Comunicação | BFF no Next.js guarda JWT em cookie httpOnly | Elimina exposição de tokens a XSS; mantém a API stateless |
| Multi-RPPS | `institution_id` em toda entidade de negócio; acesso via `memberships` | Comercialização nacional sem reescrita |
| Segregação de massas | Tabela `benefit_plans` (FINANCEIRO/PREVIDENCIARIO) com FK obrigatória nas entidades financeiras | Filtros TODOS/FINANCEIRO/PREVIDENCIÁRIO sem misturar dados |
| Histórico | Vigência inicial/final (`ValidityModel`) e versionamento (`parameters`) | Reproduzir cálculos antigos e nunca sobrescrever |
| Auditoria | Sinais Django + serviço `log_event` + trigger de imutabilidade + hash | Rastreabilidade exigida por órgãos de controle |
| RBAC | Catálogo em código (`catalog.py`) sincronizado com o banco; permissão = módulo + ação | Controle além da página (calcular, fechar, reabrir, exportar, aprovar) |
| Valores | `DECIMAL` sempre; API serializa decimais como texto | Nunca `float` em dinheiro |
| Assíncrono | Celery + Redis | Cálculo de folha, arquivos bancários e eSocial sem travar a interface |
| Integrações externas | Camadas desacopladas (adapters) | eSocial/bancos implementados só com certificado/API reais — sem sucesso simulado |

## 3. Backend — organização por domínio

| App | Responsabilidade | Fase |
|---|---|---|
| `core` | Modelos-base, contexto de requisição, validadores, erros, logs | 1 |
| `accounts` | Usuários, perfis, permissões, login, bloqueio | 1 |
| `institutions` | Instituição, planos, exercícios, competências, parâmetros | 1 |
| `audit` | Trilha de auditoria imutável e exportação | 1 |
| `alerts` | Central de alertas e verificações automáticas | 1 |
| `dashboard` | Indicadores com origem explícita (real/DEMO/indisponível) | 1 |
| `search` | Pesquisa global extensível | 1 |
| `people` | Cadastro único, dependentes, documentos (SHA-256) | 2 |
| `employment` | Entes, órgãos, cargos, vínculos, histórico funcional | 2 |
| `pension_mgmt` | Histórico contributivo, CTC, averbações, regras versionadas, simulação | 3 |
| `benefits` | Processos e workflow de concessão, pensão com cotas | 4 |
| `payroll` | Rubricas versionadas, motor de cálculo, competências, retroativos, consignações | 5 |
| `esocial` | Eventos S-2400/S-2410/S-1207, estados, protocolos (adapter desacoplado) | 6 |
| `finance` | Pagamentos, layouts bancários (CNAB), conciliação, DE/PARA contábil | 7 |
| `portal` | Portal do segurado | 8 |

## 4. Fluxo de uma requisição

1. Navegador chama `/api/backend/users?search=ana`.
2. BFF valida a origem (escrita), lê `sist_access` (renova com `sist_refresh` se expirado) e chama
   `GET {BACKEND_URL}/api/v1/users/?search=ana` com `Authorization: Bearer` e `X-Institution-Id`.
3. `RequestContextMiddleware` registra IP, navegador, ID da requisição e justificativa (`X-Justification`).
4. DRF autentica o JWT; `ModulePermission` resolve a instituição permitida, carrega as permissões e verifica `admin.usuarios:visualizar`.
5. Toda gravação de modelo registrado gera `audit_logs` (valor anterior × novo) na mesma transação (`ATOMIC_REQUESTS`).

## 5. Perfis iniciais

MASTER · ADMINISTRADOR · PREVIDENCIÁRIO · FOLHA · FINANCEIRO · CONTABILIDADE · AUDITOR · CONSULTA

* MASTER: todas as permissões, não editável; só MASTER concede/retira MASTER.
* Perfis de sistema só são alterados por MASTER; perfis da instituição são livres.
* Ações: visualizar, incluir, editar, excluir, calcular, fechar, reabrir, exportar, aprovar.

## 6. Dados de demonstração

* O painel usa sempre dados reais: beneficiários dos benefícios ativos e valores da última folha mensal calculada (`RealPayrollProvider`).
* Todo card/gráfico informa `source` = `real` | `demo` | `indisponivel`; o frontend exibe o selo DEMO.
* Alertas DEMO têm `is_demo=True` e nunca se misturam às verificações reais.

## 7. Roadmap

| Fase | Entrega |
|---|---|
| 1 ✔ | Arquitetura, banco, login, usuários, perfis, permissões, layout, painel, auditoria, alertas |
| 2 ✔ | Cadastro Único, dependentes, vínculos, histórico funcional, documentos, cadastros básicos, Protocolo (tramitação e prazos), tipo de órgão |
| 3 ✔ | Gestão previdenciária, histórico contributivo, CTC, regras parametrizadas, simulações |
| 4 ✔ | Concessão de benefícios (workflow → implantação automática na folha) |
| 5 ✔ | Motor de folha (rubricas versionadas, cálculo, conferência, fechamento, retroativos, consignações, 13º) |
| 6 ✔ | eSocial RPPS (geração e conferência dos XMLs; transmissão externa com certificado) |
| 7 ✔ | Financeiro, arquivos bancários, conciliação, integração contábil; arrecadação (contribuições, aportes, parcelamentos) |
| 8 ✔ | Portal do Segurado (contracheques, informe, dados, processos, solicitações) |
