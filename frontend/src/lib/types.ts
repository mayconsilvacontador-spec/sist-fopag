export type Source = "real" | "demo" | "indisponivel";

export type ModuleInfo = {
  code: string;
  name: string;
  group: string;
  order: number;
  phase: number | null;
  implemented: boolean;
  actions: string[];
};

export type Me = {
  user: {
    id: string;
    username: string;
    full_name: string;
    short_name: string;
    email: string;
    cpf: string;
    must_change_password: boolean;
    last_login: string | null;
    is_master: boolean;
  };
  institution: {
    id: string; short_name: string; name: string; city: string; uf: string; kind: string; life_purchase_enabled: boolean;
  } | null;
  institutions: { id: string; short_name: string; name: string; city: string; uf: string }[];
  roles: { id: string; code: string; name: string }[];
  primary_role: string;
  permissions: string[];
  modules: ModuleInfo[];
  groups: { code: string; name: string }[];
  actions: { code: string; name: string }[];
  integracoes?: { receita: boolean };
};

/** Dados devolvidos pela consulta de CPF na Receita (Conecta gov.br), já convertidos. */
export type ReceitaPerson = {
  cpf: string; name: string; social_name: string; birth_date: string | null; sex: number | null; mother_name: string;
  birthplace_city: string; birthplace_uf: string; nationality: string; situacao_cadastral: string;
  ano_obito: number | null;
  endereco: { street: string; number: string; complement: string; district: string; city: string; uf: string; cep: string };
};

export type ImportBatchRow = {
  id: string; source_system: string; status: "VALIDADO" | "IMPORTADO" | "DESCARTADO"; status_display: string;
  files: { nome: string; sha256: string; linhas: number }[];
  report: ImportReport; result: ImportReport | Record<string, never>; imported_at: string | null;
  created_by_name: string; created_at: string;
};

export type ImportReport = {
  arquivos: { nome: string; tipo: string; linhas: number; validas: number; erros: number }[];
  erros: { arquivo: string; linha: number | string; cpf: string; mensagem: string }[];
  avisos: { arquivo: string; linha: number | string; cpf: string; mensagem: string }[];
  total_erros: number; total_avisos: number;
  resumo: Record<string, number>;
};

export type Severity = "CRITICO" | "ATENCAO" | "INFORMATIVO";

export type Alert = {
  id: string;
  severity: Severity;
  severity_display: string;
  code: string;
  module: string;
  title: string;
  message: string;
  link: string;
  is_demo: boolean;
  status: "ABERTO" | "RESOLVIDO" | "DESCARTADO";
  status_display: string;
  detected_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  resolved_by_name: string;
  resolution_note: string;
};

export type Role = {
  id: string;
  code: string;
  name: string;
  description: string;
  is_system: boolean;
  active: boolean;
  permission_count: number;
  user_count: number;
  scope: string;
};

export type UserRow = {
  id: string;
  username: string;
  full_name: string;
  cpf: string | null;
  cpf_formatado: string;
  email: string;
  phone: string;
  job_title: string;
  is_active: boolean;
  is_locked: boolean;
  locked_until: string | null;
  must_change_password: boolean;
  last_login: string | null;
  last_login_ip: string | null;
  date_joined: string;
  roles: { id: string; code: string; name: string; is_system: boolean }[];
  temporary_password?: string;
};

export type FiscalYear = {
  id: string;
  year: number;
  status: "ABERTO" | "FECHADO";
  status_display: string;
  closed_at: string | null;
  closed_by_name: string;
  notes: string;
  competences_count: number;
};

export type Competence = {
  id: string;
  year: number;
  month: number;
  code: string;
  label: string;
  status: "ABERTA" | "FECHADA";
  status_display: string;
  is_reference: boolean;
  closed_at: string | null;
  closed_by_name: string;
};

export type Plan = {
  id: string;
  code: string;
  name: string;
  kind: "FINANCEIRO" | "PREVIDENCIARIO";
  kind_display: string;
  description: string;
  legal_basis: string;
  start_date: string | null;
  active: boolean;
};

export type Segment = "FINANCEIRO" | "PREVIDENCIARIO" | "COMPRA_VIDAS";

export type PayrollGroup = {
  id: string;
  segment: Segment;
  segment_display: string;
  code: string;
  name: string;
  plan: string;
  plan_code: string;
  plan_kind: Plan["kind"];
  active: boolean;
};

export type LifePurchase = {
  id: string;
  number: number;
  cutoff_date: string;
  effective_date: string | null;
  legal_act: string;
  legal_act_date: string | null;
  actuarial_study: string;
  transferred_amount: string | null;
  lives_count: number | null;
  origin_plan: string;
  origin_plan_code: string;
  destination_plan: string;
  destination_plan_code: string;
  notes: string;
  active: boolean;
};

export type ActuarialBase = {
  id: string;
  reference_year: number;
  reference_month: number;
  data_base: string;
  layout_code: string;
  life_purchase_enabled: boolean;
  file_name: string;
  file_sha256: string;
  file_size: number;
  summary: Record<string, Record<string, number>>;
  pendencias: string[];
  notes: string;
  created_by_name: string;
  created_at: string;
};

export type PersonRow = {
  id: string; cpf: string; cpf_formatado: string; name: string; social_name: string; birth_date: string;
  idade: number; sex: number; sex_display: string; death_date: string | null; situacao: string | null;
};

export type Person = PersonRow & {
  marital_status: number | null; marital_status_display: string; mother_name: string; father_name: string;
  nationality: string; birthplace_city: string; birthplace_uf: string; rg_number: string; rg_issuer: string;
  rg_uf: string; rg_date: string | null; pis_pasep: string; voter_id: string; education: string; phone: string;
  mobile: string; email: string; race: number | null; has_disability: boolean; disability_type: string; is_invalid: boolean;
  invalidity_date: string | null; death_certificate: string; notes: string; created_at: string; updated_at: string;
};

export type Address = {
  id: string; person: string; cep: string; street: string; number: string; complement: string; district: string;
  city: string; city_ibge: string; uf: string; country: string; valid_from: string; valid_to: string | null; is_current: boolean;
};

export type BankAccount = {
  id: string; person: string; bank: string; bank_label: string; branch: string; branch_digit: string; account: string;
  account_digit: string; account_type: string; account_type_display: string; valid_from: string; valid_to: string | null;
  is_current: boolean;
};

export type DependencyRow = {
  id: string; holder: string; holder_name: string; dependent: string; dependent_data: PersonRow; kind: number;
  kind_display: string; start_date: string; end_date: string | null; end_reason: string; economic_dependency: boolean;
  pension_eligible: boolean; tax_dependent: boolean; notes: string; active: boolean;
};

export type DocumentRow = {
  id: string; person: string; doc_type: string; doc_type_display: string; description: string; file_name: string;
  file_size: number; content_type: string; sha256: string; version: number; superseded: boolean; uploaded_by: string;
  created_at: string; pasta: "PESSOAIS" | "FUNCIONAIS" | "OUTROS";
};

export type EmploymentLink = {
  id: string; person: string; person_name: string; person_cpf: string; organ: string; organ_name: string;
  position: string; position_name: string; career: string; initial_position: string | null; initial_position_name: string;
  workplace: string | null; workplace_name: string; registration: string; link_type: number; link_type_display: string;
  regime: string; regime_display: string; admission_form: number; admission_form_display: string;
  public_service_start: string; ente_start: string; career_start: string | null; position_start: string;
  statutory_since: string | null; class_level: string; base_salary: string | null; weekly_hours: number | null; eligibility: number;
  eligibility_display: string; situation: number; situation_display: string; segment: Segment; segment_display: string;
  life_purchase: string | null; life_purchase_number: number | null; permanence_bonus_since: string | null;
  complementary_pension: boolean; status: string; status_display: string; end_date: string | null; end_reason: string;
  notes: string;
};

export type FunctionalEventRow = {
  id: string; link: string; event_type: string; event_type_display: string; is_absence: boolean; start_date: string;
  end_date: string | null; days: number | null; with_pay: boolean; contributed: boolean; counts_as_service: boolean;
  act_type: string; act_number: string; act_date: string | null; publication: string; description: string;
  created_by_name: string; created_at: string;
};

export type Sector = {
  id: string; name: string; code: string; organ: string | null; organ_name: string; members: string[];
  member_names: string[]; active: boolean;
};

export type ProcessTypeRow = {
  id: string; name: string; deadline_days: number; business_days: boolean; sector_deadline_days: number | null;
  description: string; active: boolean;
};

export type ProcessRow = {
  id: string; code: string; number: number; year: number; process_type: string; process_type_name: string;
  subject: string; description: string; interested: string | null; interested_name: string; interested_cpf: string;
  priority: string; priority_display: string; external_number: string; status: string; status_display: string;
  current_sector: string; current_sector_code: string; current_sector_name: string; pending_receipt: boolean;
  opened_at: string; opened_date: string; business_days: boolean; deadline_days: number; due_date: string;
  sector_due_date: string | null; suspended_since: string | null; closed_at: string | null;
  prazo: { dias_restantes: number | null; atrasado: boolean; dias_restantes_setor: number | null } | null;
};

export type MovementRow = {
  id: string; kind: string; kind_display: string; from_sector: string | null; from_sector_code: string;
  to_sector: string | null; to_sector_code: string; text: string; occurred_at: string; due_date_after: string | null;
  user_name: string;
};

export type AttachmentRow = {
  id: string; process: string; description: string; file_name: string; file_size: number; content_type: string;
  sha256: string; uploaded_by: string; created_at: string;
};

// ---------------------------------------------------------------- Fase 3 — Gestão previdenciária
export type Averbacao = {
  id: string; person: string; nature: string; nature_display: string; issuer: string; issuer_cnpj: string;
  certificate_number: string; certificate_date: string | null; start_date: string; end_date: string; gross_days: number;
  certified_days: number; magisterio: boolean; special_activity: boolean; conversion_extra_days: number;
  act_number: string; act_date: string | null; comprev: boolean; notes: string; active: boolean; is_public_service: boolean;
};

export type TimePeriod = {
  inicio: string; fim: string | null; fim_apurado: string | null; natureza: string; natureza_display: string;
  descricao: string; servico_publico: boolean; magisterio: boolean; especial: boolean; dias_brutos: number;
  deducoes: number; concomitancia: number; acrescimo_conversao: number; dias_liquidos: number; ativo: boolean;
  avisos: string[];
};

export type TimeReport = {
  data_referencia: string; periodos: TimePeriod[]; avisos: string[];
  totais: Record<"contribuicao" | "servico_publico" | "magisterio" | "especial" | "carreira" | "cargo", { dias: number; texto: string }>;
};

export type RuleSimulation = {
  codigo: string; nome: string; fundamento: string; grupo: "PERMANENTE" | "TRANSICAO" | "DIREITO_ADQUIRIDO" | "COMPULSORIA";
  professor: boolean; situacao: "CUMPRIDA" | "CUMPRIRA" | "NAO_ALCANCAVEL" | "NAO_SE_APLICA";
  data_elegibilidade: string | null; data_referencia?: string | null;
  requisitos: { chave: string; descricao: string; exigido: string; atual: string; cumprido: boolean }[];
  observacoes: string[]; proventos: string; paridade: string;
  estimativa: { valor: string | null; forma: string; avisos: string[] } | null; abono: boolean;
};

export type ChecklistSectorCode = "BENEFICIOS" | "JURIDICO" | "CONTROLE" | "PRESIDENCIA" | "FOLHA";
export type ChecklistItemRow = {
  id: string; sector: ChecklistSectorCode; sector_display: string; name: string; help_text: string;
  source: "ANEXO" | "SISTEMA"; source_display: string; system_kind: string; required: boolean;
  status: "PENDENTE" | "CUMPRIDO" | "NAO_SE_APLICA"; status_display: string; sha256: string; note: string;
  file_name: string; file_id: string; done_by_name: string; done_at: string | null;
  attachment: string | null; document: string | null; person_doc_type: string; person_document: string | null;
};
export type ChecklistResponse = {
  setor_atual: ChecklistSectorCode | null; itens: ChecklistItemRow[]; pendentes_setor_atual: string[];
  cadastro?: {
    nome: string;
    endereco: { cep: string; street: string; number: string; complement: string; district: string; city: string; uf: string } | null;
    identidade: { rg_number: string; rg_issuer: string; rg_uf: string; rg_date: string };
  };
};

/** Regras cumpridas até a data de validade e o valor de cada uma (benefício mais favorável — ELOM 28, art. 5º, § 2º). */
export type RuleComparison = {
  data_validade: string; data_base: string; melhor: string | null; pendencias: string[]; avisos: string[]; observacao: string;
  regras: { codigo: string; nome: string; fundamento: string; grupo: string; data_cumprimento: string; valor: string | null; forma: string; paridade: string; avisos: string[] }[];
};

export type Simulation = {
  data_referencia: string; idade: number; professor: boolean; ingresso_servico_publico: string | null;
  ingresso_ente: string | null;
  tempo: Record<string, number | string>;
  medias: { media80: string | null; media100: string | null; meses: number; ultima_remuneracao_rpps: string | null };
  abono_permanencia: { data: string | null; ja_tem_direito: boolean };
  regras: RuleSimulation[]; avisos: string[];
};

export type ContributionSalaryRow = {
  id: string; person: string; competence: string; competencia: string; regime: "RPPS" | "RGPS"; source_label: string;
  amount: string; origin: string;
};

export type RetirementRuleRow = {
  id: string; code: string; name: string; legal_basis: string; engine: string; group: string; for_teacher: boolean;
  params: Record<string, unknown>; valid_from: string | null; valid_to: string | null; proventos: string; paridade: string;
  gives_permanence_bonus: boolean; notes: string; active: boolean; updated_at: string;
};

export type CtcRow = {
  id: string; code: string; number: number; year: number; person: string; person_name: string; destination: string;
  purpose: string; period_start: string; period_end: string; sha256: string; process: string | null; process_code: string;
  status: "EMITIDA" | "CANCELADA"; status_display: string; cancel_reason: string; issued_by: string; created_at: string;
  snapshot: {
    instituicao: { nome: string; sigla: string; cnpj: string; cidade: string; uf: string; ente: string };
    segurado: { nome: string; cpf: string; pis_pasep: string; rg: string; nascimento: string; sexo: string; mae: string; pai: string };
    vinculos: { matricula: string; orgao: string; cargo: string; admissao: string; exoneracao: string | null; motivo: string }[];
    periodo: { inicio: string; fim: string };
    frequencia_anual: { ano: number; dias_brutos: number; deducoes: number; dias_liquidos: number }[];
    totais: { dias_brutos: number; deducoes: number; dias_liquidos: number; liquido_texto: string; anos_decimais: string };
    remuneracoes: { competencia: string; valor: string }[];
    destino: string; finalidade: string; emitida_em: string; emitida_por: string; observacoes: string[];
  };
};

// ---------------------------------------------------------------- Fase 4 — Concessão e benefícios
export type ConcessionStage = "INSTRUCAO" | "ENQUADRADO" | "CALCULADO" | "ANALISE_JURIDICA" | "CONTROLE_INTERNO" | "PRESIDENCIA"
  | "ATO_EMITIDO" | "PUBLICADO" | "IMPLANTADO" | "INDEFERIDO" | "ANULADO" | "SOBRESTADO" | "DESISTENCIA";

export type ParcelRow = {
  id?: number; kind: "PROVENTO" | "REMUNERACAO"; name: string; legal_basis: string; correlation: string;
  percent: string | null; proportionality: string | null; amount: string; in_reference: boolean;
};

export type QuotaRow = {
  id: number; dependent: string; dependent_name: string; dependent_cpf: string; relation: number; relation_display: string;
  percent: string; amount: string; duration: string; duration_display: string; end_date: string | null; duration_basis: string;
};

export type ConcessionRow = {
  id: string; kind: "APOSENTADORIA" | "PENSAO" | "REVISAO"; kind_display: string; stage: ConcessionStage; stage_display: string;
  person: string; person_name: string; process: string; process_code: string; rule_name: string;
  validity_date: string | null; total: string | null; created_at: string;
};

export type Concession = ConcessionRow & {
  person_cpf: string; link: string | null; link_label: string; modality: number | null; modality_display: string | null;
  rule: string | null; rule_code: string; legal_basis: string; local_legal_basis: string; request_date: string | null;
  validity_class: number | null; validity_class_display: string | null; validity_legal_basis: string;
  death_date: string | null; judicial: boolean; judicial_process: string; invalidity_cause: number | null; cid: string;
  medical_report_date: string | null;
  analysis: {
    data_validade?: string; data_base_calculo?: string; data_base_motivo?: string;
    regra?: { codigo: string; nome: string; fundamento: string; data_cumprimento: string; data_referencia?: string | null; requisitos: { descricao: string; exigido: string; atual: string }[] };
    opcao?: { melhor_regra: string; melhor_valor: string; valor_escolhida: string | null; justificativa: string; termo_assinado: boolean };
  };
  calculation: Record<string, unknown> & { forma?: string; avisos?: string[] };
  suspended_from: string; suspended_from_display: string; suspended_since: string | null; suspended_until: string | null;
  suspension_reason: string; withdrawal_reason: string; withdrawn_at: string | null;
  integralidade: boolean; paridade: boolean; opinion: string; approved_by_name: string; approved_at: string | null;
  act_nature: string; act_nature_display: string; act_number: string; act_date: string | null;
  publication_date: string | null; publication_media: string; implanted_at: string | null; rejection_reason: string;
  parcels: ParcelRow[]; quotas: QuotaRow[];
  compliance_opinion: string; returned_count: number; signed_hash: string; revised_benefit: string | null;
  revised_benefit_label: string; revision_reason: string; tce_sent_date: string | null; tce_reference: string;
  tce_result: "" | "LEGAL" | "RESSALVA" | "ILEGAL"; tce_result_display: string; tce_result_date: string | null; tce_notes: string;
  annulled_at: string | null; annulment_act: string;
};

export type ConcessionStepRow = {
  id: string; action: string; action_display: string; role: string; stage_from: string; stage_to: string; user_name: string;
  text: string; data: Record<string, unknown>; signed: boolean; signature_hash: string; created_at: string;
};

export type ConcessionDocumentRow = {
  id: string; kind: string; kind_display: string; version: number; file_name: string; sha256: string; created_by_name: string; created_at: string;
};

export type BenefitRow = {
  id: string; kind: "APOSENTADORIA" | "PENSAO"; kind_display: string; modality: number | null; modality_display: string | null;
  beneficiary: string; beneficiary_name: string; beneficiary_cpf: string; instituidor: string | null; instituidor_name: string;
  concession: string | null; concession_process: string; imported: boolean; folha: string; folha_name: string;
  registration: string; legal_basis: string; start_date: string; end_date: string | null; amount: string;
  percent: string | null; integralidade: boolean; paridade: boolean; status: "ATIVO" | "SUSPENSO" | "CESSADO"; status_display: string;
  esocial_nr: string; esocial_tp_beneficio: string; esocial_mtv_termino: string;
};

export type BenefitEventRow = {
  id: number; kind: string; kind_display: string; date: string; justification: string; act: string;
  old_values: Record<string, string>; new_values: Record<string, string>; user_name: string; created_at: string;
};

export type Parameter = {
  id: string;
  key: string;
  value: unknown;
  description: string;
  version: number;
  valid_from: string;
  valid_to: string | null;
  change_reason: string;
  is_current: boolean;
  created_by_name: string;
  created_at: string;
};

export type AuditLogRow = {
  id: number;
  timestamp: string;
  username: string;
  user_full_name: string;
  ip: string | null;
  user_agent: string;
  request_id: string;
  source: string;
  action: string;
  action_display: string;
  module: string;
  object_type: string;
  object_id: string;
  object_repr: string;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  justification: string;
  extra: Record<string, unknown> | null;
  record_hash: string;
};

// ---------------------------------------------------------------- Folha (Fase 5)
export type RunStatus = "ABERTA" | "CALCULADA" | "CONFERIDA" | "FECHADA" | "PAGA";
export type RunTotals = {
  beneficiarios?: number; aposentados?: number; pensionistas?: number; proventos?: string; descontos?: string;
  liquido?: string; sem_conta?: number; liquido_negativo?: number;
};
export type PayrollRun = {
  id: string; kind: "MENSAL" | "DECIMO"; kind_display: string; status: RunStatus; status_display: string;
  competence: string; competence_label: string; year: number; month: number; payroll_group: string; folha: string;
  folha_name: string; segment: string; sequence: number; totals: RunTotals; warnings: string[];
  calculated_at: string | null; checked_at: string | null; checked_by_name: string; closed_at: string | null;
  closed_by_name: string; payment_date: string | null;
};
export type PayrollEntryRow = {
  id: string; benefit: string; beneficiary: string; beneficiary_name: string; beneficiary_cpf: string;
  kind: "APOSENTADORIA" | "PENSAO"; registration: string; competencia: string; run_kind: string; folha: string;
  gross: string; discounts: string; net: string; warnings: string[];
};
export type PayrollItemRow = { id: string; code: string; name: string; kind: "PROVENTO" | "DESCONTO" | "INFORMATIVA"; reference: string; amount: string };
export type Payslip = PayrollEntryRow & {
  items: PayrollItemRow[]; run: PayrollRun; kind_display: string; instituidor_name: string; start_date: string;
  ir_base: string; rpps_base: string; bank: Record<string, string>; memory: Record<string, unknown>;
};
export type Rubric = {
  id: string; code: string; version: number; name: string; kind: "PROVENTO" | "DESCONTO" | "INFORMATIVA"; kind_display: string;
  calc: string; calc_display: string; inc_ir: boolean; inc_rpps: boolean; inc_13: boolean; inc_margem: boolean;
  ir_deduction: boolean; esocial_nature: string; esocial_inc_cp: string; esocial_inc_irrf: string; esocial_inc_cprp: string; valid_from: string; valid_to: string | null; change_reason: string; active: boolean;
};
export type PayrollEntryFixed = {
  id: string; benefit: string; beneficiary_name: string; beneficiary_cpf: string; folha: string; rubric_code: string;
  rubric_name: string; description: string; amount: string | null; percent: string | null; base: string; start: string;
  end: string | null; installments: number | null; paid_installments: number; consignee: string | null; consignee_name: string;
  contract: string; alimony_beneficiary: string | null; alimony_beneficiary_name: string; on_13: boolean; active: boolean; notes: string;
};
