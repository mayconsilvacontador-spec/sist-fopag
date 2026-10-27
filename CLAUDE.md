# SIST — Sistema Integrado de Gestão de RPPS

Sistema de gestão de Regime Próprio de Previdência Social. Instituição inicial: PREVIBAM (Barra Mansa), mas a
arquitetura é multi-instituição. Responder ao usuário em **português do Brasil**, em linguagem simples
(o usuário é contador, não programador).

Documentação de referência: `README.md` (instalação), `docs/ARQUITETURA.md` (decisões, roadmap por fases),
`docs/MODELO_DADOS.md` (modelo relacional). Ler antes de criar módulos novos.

## Estrutura

- `backend/` — Django 5.2 + DRF, apps por domínio em `backend/apps/` (core, accounts, institutions, audit, alerts,
  dashboard, search, actuarial, cadastros, people, employment, protocolo, previdencia, concessao, folha, esocial,
  financeiro, portal). Settings em `backend/config/settings.py`,
  lidos de `backend/.env`.
  - `cadastros`: entes, órgãos (código SIGFIS), cargos, lotações, bancos, agências.
  - `people`: Cadastro Único (pessoa por CPF), endereços/contas com vigência, dependências, documentos versionados.
    Importação (`importers/sprev.py`, tela Cadastros › Importação): leiaute SPREV + arquivos COMPLEMENTARES do SIST
    no mesmo lote (`importers/complementar.py`, reconhecidos pelo cabeçalho: PESSOAS_COMPLEMENTO, ENDERECOS,
    CONTAS_BANCARIAS, AVERBACOES_CTC, HISTORICO_FUNCIONAL; nada sobrescrito, vigência, sem duplicar).
    Base fictícia completa (fora do repositório): `Downloads\base_ficticia_v3` (Serra Azul do Sul, 7 órgãos,
    300 ativos/90 aposentados/38 pensões, CTCs, histórico; ver LEIA-ME.txt; validada com 0 erros).
    Base fictícia só de APOSENTADOS: `Downloads\base_ficticia_aposentados` (130 aposentados, matrículas 70001+, 11
    cenários, dependentes, complementares e arquivo com erros; gerador `gera_base_aposentados.py` no scratchpad;
    validada: 0 erros, 130 implantados — 86 PREV / 44 FIN).
  - `employment`: vínculos e histórico funcional; `actuarial_sources.py` alimenta a base atuarial.
  - **Vida do servidor** (`people/lifecycle.py`): ADMISSÃO (`people/admissao/`, tela Cadastros › Admissão — pessoa
    pelo CPF (reaproveita o Cadastro Único), vínculo com vencimento base, eventos NOMEACAO + POSSE, endereço e conta,
    tudo atômico) e FICHA (`people/<id>/ficha/` = situação/vínculo/vencimento; `people/<id>/cronologia/` = linha do
    tempo do nascimento ao óbito/pensões). Foto em `people/<id>/foto/` (PNG/JPG/WEBP conferidos pelo conteúdo, 5 MB).
    Documentos em pastas PESSOAIS/FUNCIONAIS/OUTROS (`people.models.doc_folder`, espelhado em `DOC_FOLDERS` no
    frontend). Ficha com abas Cronologia, Dados pessoais (+endereços/contas/dependentes), Vida funcional, Pasta de
    documentos, Previdência, Processos. Menu sem Dependentes/Vínculos/Instituidores/Tabelas/Histórico funcional/
    Elegibilidade/Certidões/Processos previdenciários (ficam na ficha ou não implementados).
    Tela **Servidores** (`/cadastros/servidores`: lista de vínculos + card de importação + "Nova admissão") →
    **Pasta do Servidor** (`/cadastros/pessoas/[id]`: cabeçalho com foto; abas Ficha de Admissão (imprimível),
    Vida Funcional, Remuneração, Férias e Afastamentos, Benefícios, Dependentes, Processos, Documentos; coluna direita
    Linha do Tempo Funcional + Óbito/Pensão; dados extras em `people/<id>/pasta/` = `lifecycle.folder_extras`).
    `EmploymentLink.weekly_hours` (carga horária). **Tabela padrão de servidores** (`complementar.SERVIDORES_COLUMNS`,
    modelo Excel em `imports/modelo-servidores/`; tipo `admissoes` = uma admissão completa por linha via
    `lifecycle.admit`, matrícula repetida é ignorada). Layout de referência: imagem enviada pelo usuário (o site
    sifab.sistsolucoes.com.br estava com certificado inválido).
    Importação SPREV grava `base_salary` = VL_BASE_CALCULO (senão VL_REMUNERACAO), a conferir com a tabela de
    vencimentos (que tem prioridade na folha); `manage.py fill_base_salary --institution <sigla>` preenche vínculos
    antigos a partir dos arquivos guardados nos lotes.
  - `protocolo`: setores, tipos, feriados, processos, tramitação; prazos em `deadlines.py` (dias úteis/corridos).
    Todos os perfis (exceto Consulta/Auditor) abrem processos para qualquer setor ativo (`sectors/destinos`); quem
    não é do setor de destino abre com "aguardando recebimento". `ALWAYS_SYNC` (catalog) inclui as permissões do
    Protocolo também nos perfis de sistema já existentes a cada `sync_permissions`.
  - `previdencia` (Fase 3): averbações, salários de contribuição, fatores de correção, regras de aposentadoria
    versionadas (`rules.py`: motor + `default_rules`), apuração de tempo (`tempo.py`), estimativa de proventos
    (`calculo.py`), CTC (snapshot imutável), `SalContr.txt` da Deliberação 260 (`services.salcontr_txt`). Salários:
    importação individual (`import_salaries`) e em lote por CPF (`import_salaries_batch`, endpoint
    `previdencia/salarios/import-lote/`, gravação em blocos). Bases fictícias de teste (fora do repositório):
    `Downloads\base_ficticia_sprev` (1ª) e `Downloads\base_ficticia_v2` (segurados por cenário, salários em lote,
    fatores fictícios; ver LEIA-ME.txt).
    Regras carregadas por `manage.py seed_rules --institution PREVIBAM --reforma 2025-06-15` (também cria o
    parâmetro `rgps.teto` 2023–2025 e as séries históricas `rgps.teto` 1994–2022 e `salario_minimo` 1994–2026 —
    a conferir com a norma oficial; anos seguintes devem ser cadastrados em Parâmetros).
    Média (`calculo.Averages`, Lei 3.965/2011 art. 62): piso do salário mínimo e teto do RGPS por competência,
    fatores obrigatórios, lacunas no vínculo RPPS; `pendencias` BLOQUEIAM a concessão (na simulação viram avisos).
    Proventos (`estimate`): limite à remuneração antes da fração (art. 63 § 1º), piso do salário mínimo, compulsória
    antes/depois da reforma, redutor EC 41 3,5%/5%. Auditoria de out/2026: `tests/test_auditoria_concessao.py`.
  - `concessao` (Fase 4): `Concession` (APOSENTADORIA, PENSAO, REVISAO; fluxo do mapeamento PREVIBAM em `workflow.py`:
    instrução (Benefícios) → ANALISE_JURIDICA → CONTROLE_INTERNO (revisão pula) → PRESIDENCIA (assina; valores fixados
    com hash) → ATO_EMITIDO → PUBLICADO → IMPLANTADO (Folha; confere o hash) → TCE-RJ (julgamento; ILEGAL → ANULADO).
    Cada decisão tem módulo próprio (concessao.juridico/controle_interno/presidencia/implantacao/tce), exige senha
    (assinatura eletrônica) e respeita a segregação de funções (`concessao.segregacao_funcoes`, padrão ativo).
    Trilha imutável em `ConcessionStep`; minuta/portaria/ofício/anulação em Word por `documents.py` (modelos editáveis
    `DocumentTemplate`), anexados ao Protocolo e avisados na Central de Alertas (check CONCESSAO_PENDENTE).
    Revisão de valor só por processo (evento REVISAO direto é recusado); eventos de benefício pedem senha.
    Data-base da média e do tempo = ABERTURA DO PROCESSO (critério da PREVIBAM; outra data só com justificativa).
    Enquadramento compara todas as regras (`compare_rules`, endpoint `comparativo`): regra menos vantajosa exige
    justificativa + termo de opção do servidor (ELOM 28, art. 5º § 2º). Envio ao Jurídico exige ciência dos avisos.
    Antes da assinatura da portaria (`PAUSABLE_STAGES`): SOBRESTADO (pausa com motivo, previsão de retomada e senha;
    processo do Protocolo fica sobrestado e o prazo é estendido na retomada) e DESISTENCIA (pedido do requerente
    juntado + senha; arquiva o processo sem conceder e gera o Termo de desistência) — `workflow.suspend/resume/withdraw`.
    Processo digital (`checklist.py`): `ChecklistTemplate` (por tipo × setor × modalidade, editável em
    /concessao/checklist; sugestão inicial dos manuais MM-*, criada na 1ª consulta) e `ChecklistItem` por processo
    (ANEXO = arquivo no Protocolo com SHA-256; SISTEMA = relatório de instrução/parecer/conformidade/portaria gerados
    no ato). Cada ato de setor (envio ao Jurídico e publicação também pedem senha) exige o checklist do setor completo
    (`require_complete`) e o assina (`seal`: SHA-256 na trilha e no andamento do Protocolo). Só o setor que está com o
    processo altera o seu checklist (`SECTOR_BY_STAGE`).
    Sempre ligado a um processo do Protocolo), `Parcel`, `PensionQuota`, `Benefit` (um por
    beneficiário/cota, ligado a uma `PayrollGroup` — é o que a folha lê), `BenefitEvent`
    (revisão/suspensão/restabelecimento/cessação/reversão). Pensão em `services._calc_pension` (EC 103 art. 23
    após a reforma local; art. 40 §7º antes). Ficha FATIMA em `fatima.py`. Benefícios importados da base SPREV
    (`people.LegacyBenefit`) são implantados por `services.implant_legacy`.
  - `folha` (Fase 5): `Rubric` versionada (cada `PayrollItem` guarda a versão usada; `calc` automáticos são
    únicos), `Entry` (lançamentos por benefício: MANUAL/diferenças, CONSIGNACAO, PENSAO_ALIMENTICIA, com parcelas),
    `Consignee`, `IrExemption` (moléstia grave), `PayrollRun` (competência × folha × MENSAL/DECIMO; ABERTA→
    CALCULADA→CONFERIDA→FECHADA→PAGA; reabertura só de FECHADA, com justificativa; mensal não pula competência;
    exclusão `services.delete_run` (permissão `folha.folha_mensal:excluir`, senha + justificativa, só a última da
    massa/tipo, sem lote de pagamento/contribuição/eSocial, PAGA só sem beneficiário; desfaz parcelas; auditada)),
    `PayrollEntry` (contracheque, com `memory` = memória de cálculo usada pelo informe de rendimentos).
    Motor em `engine.py` (dias comerciais, retroativo só de benefício com `concession`, RRA de anos anteriores,
    contribuição sobre o excedente ao teto — na pensão, teto sobre o total das cotas e rateio —, IRRF por
    beneficiário, pensão alimentícia iterativa, margem consignável, 13º por avos); IR/contribuição em `tax.py`.
    Carga: `manage.py seed_payroll --institution PREVIBAM` (18 rubricas, `irrf.tabela` 2024/2025/2026,
    `folha.aliquota_segurado` 14% desde 09/2025, `folha.margem_consignavel` 35%). O painel usa
    sempre `RealPayrollProvider` (beneficiários = benefícios ativos; valores = última folha calculada; sem DEMO). Arquivo CNAB fica para a Fase 7 (hoje: relação de crédito).
  - `pessoal` (**Folha de ATIVOS**, menu "Folha de Ativos", módulos `ativos.*`, para todos os tipos de órgão —
    separada da folha de benefícios): `SalaryScale` (tabela de vencimentos cargo × nível com vigência; reajuste =
    `new_scale` encerra a anterior), `ActiveRubric` (sugestão `DEFAULT_RUBRICS` no 1º acesso; cálculos VENCIMENTO,
    ADICIONAL_TEMPO % a cada N anos com limite, LANCAMENTO, FALTAS, CONTRIB_RPPS, IRRF), `ActiveEntry` (lançamentos
    por vínculo, valor ou % do vencimento, parcelas), `ActiveRun` (uma por ÓRGÃO × competência; ABERTA→CALCULADA→
    CONFERIDA→FECHADA; reabrir/excluir com justificativa), `ActivePayslip`/`Item` (snapshot). Motor
    `services.calculate_link`: dias comerciais (licença sem vencimento reduz), vencimento pela tabela ou
    `link.base_salary`, faltas do histórico funcional, RPPS = `folha.aliquota_segurado` (teto do RGPS se previdência
    complementar), patronal informativa (`arrecadacao.aliquota_patronal`), IRRF via `folha.tax.compute_ir`.
    FICHA FINANCEIRA (`pessoal/ficha.py`, módulo `ativos.ficha_financeira`, endpoints `ativos/ficha-financeira/…`):
    importação do sistema anterior (`FinancialImport`/`FinancialLine`, leiaute `COLUMNS`, modelo Excel; conferir →
    gravar; repetir atualiza; `CLASSIFICACAO` CONTRIB_RPPS/BASE_RPPS/PATRONAL/IRRF, sugerida pelo nome e corrigível em
    `classificar/`), ficha anual rubrica × mês juntando contracheques da Folha de Ativos (prevalecem) e linhas importadas
    (Excel), CONTROLE DA CONTRIBUIÇÃO por competência (base, descontado, devido = base × `folha.aliquota_segurado`,
    diferença, patronal, repasse do órgão = `financeiro.Contribution` SERVIDOR + receitas) e `to_history` (bases →
    salários de contribuição, sem alterar os existentes). Telas: Pasta › Remuneração e Folha de Ativos › Ficha financeira.
    `add_manual` (endpoint `<pessoa>/lancar/`): lança competência sem arquivo (base, alíquota, descontado; opcional no
    histórico). O controle também mostra os meses do histórico contributivo sem ficha (fonte HISTORICO, "desconto não
    informado"). ALÍQUOTAS: `financeiro/aliquotas.py`, tela Arrecadação › Alíquotas (`arrecadacao/aliquotas/`, módulo
    `arrecadacao.aliquotas`): servidor e patronal com vigência sobre os parâmetros; aceita vigência nova ou HISTÓRICA
    (antes da primeira) — `set_parameter` sozinho só aceita posteriores.
    Próximas etapas: 13º, férias + 1/3, rescisão, eSocial S-1200/S-1210 de ativos, crédito bancário, integração
    com a Arrecadação (contribuições servidor/patronal da folha).
  - `esocial` (Fase 6): `EsocialEvent` (XML não assinado + pendências; PENDENTE→VALIDADO→EXPORTADO→ACEITO|
    REJEITADO; correção/retificação gera NOVO evento com `replaces`, nada é excluído) e `EsocialLog`. XMLs em
    `builders.py` (S-2400, S-2410, S-2420, S-1010, S-1207, S-1210, S-1299; leiaute no parâmetro `esocial.versao`,
    padrão S_01_03_00). **Nunca simula retorno.** Dois caminhos: (a) exporta ZIP para transmissor externo e
    importa o XML de retorno (`import_returns` → `apply_returns`: cdResposta 201/202 = aceito) ou recibo manual;
    (b) **transmissão direta** (`transmission.py`, tela /esocial/transmissao, módulo `esocial.transmissao`):
    certificado A1 `.pfx` em `EsocialCertificate` CRIPTOGRAFADO com Fernet (chave `ESOCIAL_CERT_KEY` no
    `backend/.env`, nunca no banco; trocar a chave obriga reenviar o certificado), assinatura XMLDSig própria
    (`sign_event`: sem prefixo ds:, URI="", C14N, RSA-SHA256 — o modo sem prefixo do signxml gera assinatura
    inválida, por isso não é usado), `EsocialBatch` (até 50 eventos do mesmo grupo; 201 = recebido com protocolo →
    eventos EXPORTADO; consulta 101 = processando, 201 = aplica retornos, outro = lote com erro e eventos voltam a
    VALIDADO), TLS mútuo via `requests` com PEM temporário 0600. Instalar certificado e transmitir pedem a senha do
    usuário. URLs/namespaces em `transmission.URLS`/`NS_*` (conferir com o Manual do Desenvolvedor a cada versão);
    ambiente = parâmetro `esocial.ambiente` (2 = produção restrita). Testes simulam o webservice só no pytest. XSD oficial é opcional: copiar .xsd para `backend/apps/esocial/xsd/`
    (validação com lxml). Códigos de tabelas (25, 26, natureza Tabela 03, codIncIRRF/codIncCPRP) vêm do cadastro
    — `seed_esocial --institution PREVIBAM` só SUGERE incidências (a conferir). Campos novos: `Person.race`,
    `Address.city_ibge`, `Benefit.esocial_nr/esocial_tp_beneficio/esocial_mtv_termino`, `Rubric.esocial_inc_*`.
  - `financeiro` (Fase 7, cobre Financeiro e Arrecadação): `TreasuryAccount` (conta da instituição por plano, com
    convênio CNAB), `PaymentBatch`/`PaymentItem` (lote da folha FECHADA → aprovação → remessa → retorno; conta
    pagadora tem de ser do MESMO plano da folha; quando todos os líquidos são pagos, a folha vira PAGA),
    `BankFile` (remessa/retorno/extrato com SHA-256), `cnab.py` (CNAB 240 FEBRABAN genérico, segmentos A/B, lote
    crédito mesmo banco + lote TED; **precisa ser homologado com o banco**), `Contribution` (servidor/patronal
    estimadas pelo vencimento base dos vínculos, base editável; APOSENTADOS = retenção da folha), `Aporte`,
    `InstallmentAgreement`/`Installment` (cronograma nominal), `Revenue` (receita realizada; baixa só em conta do
    mesmo plano; estorno = inativar com justificativa), `StatementLine` (extrato OFX, conciliação automática por
    valor/data ±3 dias), `AccountingMapping`/`AccountingExport` (de-para rubrica/receita → contas, CSV).
    Parâmetros: `seed_financeiro --institution PREVIBAM` (`arrecadacao.aliquota_patronal` 24% desde 09/2025,
    `arrecadacao.vencimento_dia` 20 — conferir lei municipal).
  - `portal` (Fase 8): Portal do Segurado. `PortalAccess` (usuário `User.is_portal` ligado a uma pessoa; senha
    provisória gerada pela equipe em `/portal`, troca obrigatória) e `PortalRequest` (solicitações respondidas pela
    equipe). Segurança: `ModulePermission` recusa usuário `is_portal` em qualquer view sem `portal_allowed = True`;
    o login interno (`auth/token/`) recusa usuário do portal e o do portal (`portal/auth/token/`, por CPF) só
    aceita usuário do portal; consultas filtradas pela pessoa do acesso; contracheques só de folha FECHADA/PAGA.
    Frontend do segurado em `/segurado` (fora do AppShell); a tela interna de gestão é `/portal`.
- `comprev` (só CONTROLE — o requerimento/pagamento acontece no sistema COMPREV do governo): `ComprevProcess` nos dois
  sentidos (RECEBER = somos regime instituidor, ligado a `Benefit`/`Averbacao`, plano = o da folha do benefício;
  PAGAR = somos regime de origem, ligado à `Ctc`), situação com trilha `ProcessEvent` (CADASTRADO→ENVIADO→EXIGENCIA→
  DEFERIDO→CESSADO; INDEFERIDO/CANCELADO; transições em `models.TRANSITIONS`), valor mensal com vigência
  (`MonthlyValue`, reajuste = nova vigência), `Movement` (fluxo mensal/atrasados/ajuste/glosa; estorno = inativar;
  um MENSAL por competência), lote do mês (`register_batch`), recebimentos → UMA `financeiro.Revenue` tipo COMPREV
  (`to_revenue`, mesmo plano), fluxo previsto × realizado, indicadores, `potential` (benefício com averbação
  `comprev=True` sem requerimento). Pro rata só como sugestão (RMI × tempo origem ÷ total). Alerta COMPREV.
  Relatórios com `also=("relatorios.comprev",)`: o registro aceita outros módulos (`Report.also`, `?modulo=`).
- `leitura` — DOIS MOTORES (`AiSettings.engine`, guardado em `ReadingJob.engine`): **LOCAL (padrão, gratuito, sem
  internet)** = `ocr.py`: Tesseract 5 + `por` instalados no `backend/Dockerfile`, PyMuPDF; página digital lida direto,
  digitalizada vira imagem 300 dpi P&B e é lida em PARALELO (limiar 170 psm 6, Otsu psm 6, 170 psm 11 "esparso" —
  o psm 6 falha com faixa cinza na página; fica a leitura com mais palavras confiáveis);
  linhas/blocos com caixa (coordenadas do PDF); classificação pelo nome do arquivo (palavra inteira, peso 40) e
  palavras-chave; campos por rótulo (mesma linha ou linha logo abaixo na mesma coluna; `LABEL_WORDS` descarta rótulo
  como valor); CPF/PIS validados pelo dígito com correção O→0, l→1, /→7; tabela da CTC por coluna do cabeçalho
  (dedução inferida bruto−líquido ≤ 60, "tempo líquido apurado" como total; ano com bruto > 366, líquido com dígito
  trocado ou não lido é ajustado e marcado `suspeito` → aviso + linha amarela com "confirmar"); rubricas entre
  cabeçalho e "Total". "Ler de novo" vale para qualquer arquivo em conferência.
  `read_next` faz 2 páginas por chamada (`pages_done`); `review_row` corrige célula da CTC; endpoint
  `arquivo/<id>/pagina/<n>/?caixa=` devolve PNG com retângulo vermelho. Calibrado com processo real (Mangaratiba):
  OCR erra números pequenos — as contas (CTC, contracheque, líquido) apontam a linha a corrigir. **ANTHROPIC** (pago):
- `leitura` (Leitura inteligente de processos, tela /concessao/leitura, módulo `concessao.leitura`): PDFs do processo
  (quase sempre digitalizados, sem texto) lidos pela API da Anthropic (`reader.py`: SDK `anthropic` 1.x,
  `beta.messages.stream`, PDF inteiro como bloco `document`, saída estruturada `SCHEMA` com tipos `DOC_TYPES` e
  chaves `FIELDS`, `fallbacks: "default"`, effort `medium`; modelo Opus 5.5 ou Sonnet 5.5 por instituição).
  `AiSettings` (chave de API criptografada com `core/secrets.py` — `SIST_SECRETS_KEY` no .env; ativar exige ciência
  LGPD; configurar exige `admin.configuracoes:editar`). `ReadingJob`/`ReadingFile` (fila: a tela chama `ler/` um
  arquivo por vez). Conferência: cada campo com página/trecho/confiança, confirmar/corrigir/ignorar; `run_checks`
  (CPF/nascimento/nome/admissão entre documentos, contas da CTC ano a ano e total, rubricas × totais, documentos
  esperados, comparação com o Cadastro Único). `apply` só com tudo conferido e sem erro: pessoa (só completa campos
  vazios; diferenças listadas), vínculo (órgão escolhido), CTC → averbação ou faltas do vínculo, PDFs nos documentos
  da pessoa. Testes trocam `reader.read_pdf` por leitura fictícia. `X-Frame-Options: SAMEORIGIN` (PDF ao lado).
- `reports` (relatórios): catálogo em `apps/reports/registry.py` (`@report(codigo, modulo, titulo, descricao, filtros)`
  → colunas/linhas/totais); definições em `definitions.py` (previdenciários, benefícios, folha, financeiros, gerenciais,
  estatísticos, eSocial) e nos apps (ex.: `provadevida/reports.py`). Tela genérica `components/reports/reports-page.tsx`
  (rota `/relatorios/[modulo]`), exportação Excel/CSV exige `exportar` e vai para a auditoria. O sistema é
  multi-órgão: nada de regra fixa da PREVIBAM no código.
- `provadevida`: campanhas por ato do órgão (`LifeProofCampaign`: anual/semestral/extraordinária, prazo = fim da
  campanha ou mês de aniversário, tolerância, público, folha) e `LifeProof` por beneficiário. Suspensão dos atrasados
  só por comando com senha (`suspend_overdue` → `BenefitEvent` SUSPENSAO); prova tardia restabelece (senha). Aviso no
  Portal do Segurado (`portal/me` → `prova_de_vida`). Alerta PROVA_DE_VIDA.
  Prova pelo Portal (`allow_portal`): selfie com documento + foto do documento (imagens conferidas pelo conteúdo)
  → EM_ANALISE → equipe aprova (`register`, canal PORTAL; restabelece se estava suspenso) ou recusa (`portal_reject`).
  Selfie SÓ pela câmera ao vivo (`components/portal/live-selfie.tsx`, getUserMedia; exige HTTPS em produção): 2
  gestos sorteados + medição de movimento; o servidor exige as fotos dos gestos e movimento ≥ 4
  (`check_liveness`) — sem isso recusa. Não é biometria facial (depende de serviço contratado). Sem câmera/permissão
  → "Pedir atendimento" (presencial, visita domiciliar ou procurador) vira solicitação no Portal.
- `recadastramento`: campanhas por ato (`RegistrationCampaign`: público servidores/beneficiários/todos, órgão,
  Portal, comprovante obrigatório) e `Reregistration` por pessoa (PENDENTE→ENVIADO→APROVADO|DEVOLVIDO). Pelo Portal
  ou presencial (equipe preenche e aprova). Nada vai ao Cadastro Único sem conferência: `approve` aplica só o que
  mudou (pessoa auditada, endereço com nova vigência, comprovante/identidade nos documentos). Dependentes e conta
  bancária NÃO mudam por aqui → `staff_followup` (relatório "Pendências para a equipe"). Lembretes 15/7/1 dia.
- Avisos ao segurado (`portal/notifications.py`): `PortalNotification` (sininho, chave única) e `OutboundMessage`
  (celular). Lembretes de prova de vida 30/15/7/1 dia e prazo vencido (`provadevida.services.portal_reminders`,
  chamado pela rotina de alertas). **Sem provedor de SMS/WhatsApp contratado nada é enviado sozinho**: a equipe
  abre o link wa.me com o texto pronto (Portal › Mensagens ao celular) e confirma. Parâmetro `portal.mensagens_celular`.
- Checklist → Cadastro Único: item com `person_doc_type` vira nova versão do documento da pessoa; comprovante de
  residência/identidade permitem conferir e atualizar endereço (nova vigência) e RG (`checklist.update_cadastro`).
- Tipo de órgão (`Institution.kind`: RPPS, PREFEITURA, AUTARQUIA, FUNDACAO, CAMARA, FUNDO): módulos de RPPS (`RPPS_GROUPS` em
  `accounts/catalog.py`) são retirados das permissões efetivas dos demais tipos.
- Identidade visual (`institutions/branding.py`): brasão e imagem de fundo da instituição (PNG/JPG/WEBP conferidos
  pelo conteúdo; SVG recusado), enviados em Administração › Instituição; leitura pública (`branding/`, usada no login)
  pela rota Next `/api/branding` (sem sessão). Fundo aplicado no AppShell com véu (`background_intensity` 5–60%).
  Layout padrão **SIST-SIFAB** (pedido do usuário): menu lateral CLARO com grupos em caixa alta sem ícones (ícones só
  recolhido), grupo "Principal" (Painel, Alertas, Calendário), cor principal vermelho-vinho (tokens em globals.css),
  barra superior com voltar/avançar, busca central arredondada, ano, avisos e usuário; botão de recolher o menu na barra
  das abas; ponto laranja por pendência (`alerts/summary` → `por_grupo`).
  Menu (out/2026) enxuto: `MenuLeaf.section` (título de seção no grupo: Rotina do mês, Tabelas...) e
  `MenuLeaf.hidden` (telas repetidas fora do menu, mas na pesquisa global e nos títulos das abas). Uma tela por
  tarefa: Folha mensal faz o ciclo inteiro (Cálculo/Conferência/Fechamento/Reabertura/Painel/Arquivo bancário/
  Relatórios ocultos); eSocial › Eventos gera, filtra (tipo/situação), exporta e importa retorno (S-xxxx/Retornos/
  Rejeições/Pendências ocultos); Concessão › "Suspender, cessar ou reverter" (`/concessao/beneficios`,
  `BenefitsScreen area="concessao"`) substitui Suspensão/Cessação/Reversão; Auditoria = um item (filtros na tela).
  Guia "Como fazer (passo a passo)" em `/guia` (rotinas com links por permissão).
- Frontend: abas de telas abertas (estilo navegador) em `components/layout/page-tabs.tsx` (guardadas no
  localStorage por usuário; o título vem do `PageHeader`; trocar de aba remonta a tela). Cadastros simples usam `components/shared/registry-page.tsx` (lista + `FormDialog`); códigos das tabelas
  em `frontend/src/lib/options.ts` (espelham o backend).
- `frontend/` — Next.js 15 (App Router) + TypeScript + Tailwind 3 + shadcn/ui. Telas autenticadas em
  `frontend/src/app/(app)/`. O navegador nunca fala com o Django direto: passa pelo BFF em
  `frontend/src/app/api/backend/[...path]` (JWT em cookie httpOnly). Escritas (POST etc.) só com Origin/Referer em
  `ALLOWED_ORIGINS` (`frontend/.env.local`) ou igual ao Host do próprio servidor (`isAllowedOrigin` em `lib/server/bff.ts`).
- `docker-compose.yml` — PostgreSQL 16 (banco/usuário/senha `sist`) e Redis 7, apenas para desenvolvimento.

## Ambiente desta máquina (Windows 11 Home)

- Abrir o sistema: abrir o **Docker Desktop** (instalado em
  `%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe`), rodar `docker compose up -d` na raiz (containers `sist-postgres`,
  `sist-redis`, `sist-backend`) e depois `preview_start` com `frontend` (porta 3000, `.claude/launch.json`).
- **O backend roda dentro do Docker** (`backend/Dockerfile`, código montado em `/app`, recarrega sozinho).
  Comandos Django: `docker exec sist-backend python manage.py <comando>` (interativo: `docker exec -it ...`).
  Após mudar `requirements*.txt`: `docker compose up -d --build backend`.
- Não há venv local: `backend/.venv` foi apagado (não conectava ao banco no Windows — Smart App Control). Use o Docker.
- O DNS interno do Docker Desktop falha nesta máquina: postgres e redis têm IPs fixos (172.28.0.10 / .11) no
  `docker-compose.yml`; não trocar por nomes de serviço.
- Se o Docker Desktop não abrir com erro em `docker-secrets-engine\engine.sock` (ou "Docker Desktop is unable to
  start"), o usuário deve fechar o Docker (Quit) e apagar esse arquivo em `%LOCALAPPDATA%\docker-secrets-engine`
  (nunca "Reset to factory defaults": apaga o banco). O classificador de permissões bloqueia o Claude de apagá-lo.
  Problema recorrente — se persistir, sugerir atualizar o Docker Desktop.
- O frontend roda em **modo de produção** (`preview_start` `frontend` = `next start`): o modo dev recompilava cada
  tela (3–8 s) e deixava o BFF lento (~2,5 s por chamada). **Após alterar o frontend, rodar o build**
  (`node node_modules\next\dist\bin\next build` na pasta `frontend`, ~5 min, com o servidor parado) e reiniciar o
  `frontend`. Para desenvolver com recarga automática, usar `frontend-dev` (`next dev`). Os dois são iniciados com
  `node node_modules\next\dist\bin\next ...` porque `npm run dev` via preview não sobe.
- Teste no celular (mesma rede Wi-Fi): `preview_start` `celular-https` (script `frontend/scripts/https-local.mjs`,
  certificado autoassinado em `frontend/certs/*.pem`, gerado para o IP 192.168.15.103) → https://192.168.15.103:3443.
  O celular só libera câmera em https. Se o IP do computador mudar, gerar outro certificado e ajustar
  `ALLOWED_ORIGINS` em `frontend/.env.local`. `Permissions-Policy` em `next.config.ts` permite `camera=(self)`.
- Celery (worker/beat) ainda não está rodando; tarefas assíncronas ficam na fila do Redis.

### Armadilhas já resolvidas — não desfazer

- **Smart App Control do Windows está ativo** e bloqueia DLLs sem assinatura: tanto `psycopg[binary]` quanto
  `psycopg2-binary` foram bloqueados no Windows. Por isso o backend roda em Linux no Docker. Nunca sugerir desligar
  o Smart App Control (não pode ser religado sem reinstalar o Windows). O `@next/swc-win32-x64-msvc` também passou a
  ser bloqueado (aviso no `next lint`); se o frontend parar de compilar, considerar rodá-lo também no Docker.
- `frontend/postcss.config.mjs` e `frontend/tailwind.config.ts` (`content.relative: true`) usam caminhos
  relativos ao próprio arquivo, para o Tailwind funcionar quando o Next é iniciado fora de `frontend/`.
- Arquivos `.env` devem ser gravados em UTF-8 **sem BOM** (o django-environ rejeita BOM). No PowerShell 5.1,
  não usar `Set-Content -Encoding utf8` para eles.

## Comandos

Backend (`docker exec sist-backend python manage.py ...`):

- `manage.py migrate` / `manage.py seed_initial` — tabelas e carga inicial (PREVIBAM, planos FIN e PREV).
- `manage.py createmaster --username <u> --full-name "<nome>" --email <e>` — cria usuário MASTER. Pede a senha
  de forma interativa (mínimo 10 caracteres); o usuário deve rodar no próprio terminal.
- `manage.py sync_permissions` — sincroniza o catálogo RBAC (`apps/accounts/catalog.py`) com o banco.
- `manage.py seed_demo [--remove]`, `manage.py run_alert_checks`.
- `docker exec sist-backend pytest` — testes (precisa do Postgres rodando; cria banco temporário).

Frontend (na pasta `frontend`): `npm run typecheck`, `npm run lint`, `npm run build`.

## Regras do projeto

- Dinheiro sempre `Decimal`/`DECIMAL`; a API serializa decimais como texto. Nunca `float`.
- Toda entidade de negócio tem `institution_id`; entidades financeiras têm FK obrigatória para `benefit_plans`
  (FINANCEIRO/PREVIDENCIÁRIO) — não misturar massas.
- Histórico nunca é sobrescrito: usar vigência (`ValidityModel`) ou versionamento (`parameters`).
- Auditoria é imutável (trigger no PostgreSQL + hash SHA-256). Não criar UPDATE/DELETE em `audit_logs`.
- Permissão = módulo + ação, validada no backend em todo endpoint; o frontend só oculta.
- Dados de demonstração sempre marcados como DEMO (`source`/`is_demo`); nunca simular sucesso de integrações
  externas (eSocial, bancos).
- Telas ainda não implementadas mostram "Em desenvolvimento — Fase N" (rota `[...slug]`).
- Segregação em **três folhas**: Financeiro, Previdenciário (massa própria) e Compra de Vidas — esta pertence ao Plano
  Previdenciário (fundo em capitalização). Ver `docs/MODELO_DADOS.md` › "Segregação em três folhas".
- Base atuarial no leiaute oficial SPREV (`backend/apps/actuarial/layouts/sprev_2021.json`, extraído do dicionário
  oficial). Nunca alterar nomes/ordem das variáveis oficiais; dados extras vão em arquivos complementares.
- **Legislação de Barra Mansa (PREVIBAM):** Emenda à Lei Orgânica nº 28/2025 (adota as regras da EC 103 da União;
  transições arts. 4º, 20, 21; permanente art. 10 e 22; direito adquirido art. 5º; abono art. 6º; alíquotas 14% e
  patronal 24% a partir de 01/09/2025) com vigência dada pela **LC 106/2025, publicada em 15/06/2025**. Requisitos
  das regras antigas (CF art. 40, EC 41 arts. 2º e 6º, EC 47 art. 3º) valem só se cumpridos até 14/06/2025.
  Pendências de interpretação: data de referência do pedágio do art. 20 (adotada 15/06/2025) e idade da Guarda
  Municipal (depende de LC futura).
- Fase 6 (eSocial RPPS) concluída: geração, conferência, exportação e retorno dos eventos; pendências: S-2405/
  S-2416 (alterações), S-1000/S-1005 (já enviados pelo ente), informações complementares de IR no S-1210, XSDs.
- Fase 7 (Financeiro e Arrecadação) concluída; pendências: homologar o CNAB 240 com o banco da PREVIBAM,
  confirmar dia de vencimento e alíquota patronal anterior a 09/2025, atualização monetária automática das parcelas.
- Datas "de hoje" no backend: usar sempre `timezone.localdate()` (o container roda em UTC; `date.today()` vira o
  dia seguinte após 21h de Brasília).
- Fase 8 (Portal do Segurado) concluída; tutorial de operação da folha em `docs/TUTORIAL_FOLHA.md`.
- Situação atual: **Fases 1 a 8 concluídas** (roteiro original completo) (Fase 2 = Cadastro Único, vínculos, histórico funcional, cadastros
  básicos, Protocolo com prazos, tipo de órgão; Fase 3 = tempo de contribuição, averbações, histórico contributivo,
  regras versionadas, simulação, abono, CTC, SalContr.txt; Fase 4 = concessão integrada de aposentadoria e pensão,
  implantação na folha, operações sobre benefícios, Ficha FATIMA da Deliberação 260 — só `SalContr.txt` é
  importável no FATIMA; Fase 5 = motor de folha, rubricas versionadas, 13º, consignações, pensão alimentícia,
  retroativos/RRA, conferência, fechamento/reabertura, contracheque, informe de rendimentos, relação de crédito).
  Pendências da Fase 5: conferir a tabela do IRRF 2026 (Lei 15.270/2025) e a alíquota anterior a 09/2025;
  confirmar a margem consignável municipal; CNAB por banco (Fase 7).
- Perfis de sistema só recebem permissões novas na criação; após incluir módulos, avaliar
  `sync_permissions --reset-roles` (sobrescreve personalizações dos perfis de sistema).
