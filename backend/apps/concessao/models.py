"""
Concessão de benefícios (Fase 4) e benefícios implantados.

Fluxo da concessão (cada etapa registrada e auditada):
  INSTRUCAO -> ENQUADRADO -> CALCULADO (Benefícios) -> ANALISE_JURIDICA -> CONTROLE_INTERNO -> PRESIDENCIA
  -> ATO_EMITIDO (portaria assinada) -> PUBLICADO -> IMPLANTADO (Folha) [-> TCE-RJ; ANULADO se julgado ilegal]
  Regras de decisão, segregação de funções e assinatura eletrônica em workflow.py.
  (ou INDEFERIDO). Todo processo de concessão nasce de um processo do Protocolo.

Benefício: um registro por beneficiário (na pensão, um por cota), sempre ligado a
uma FOLHA (massa) — o motor de folha da Fase 5 lê daqui. Nada é excluído: revisões,
suspensões e cessações viram eventos.

Os campos espelham o FATIMA (Deliberação TCE-RJ 260) e o leiaute SPREV.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel


class BenefitKind(models.TextChoices):
    APOSENTADORIA = "APOSENTADORIA", "Aposentadoria"
    PENSAO = "PENSAO", "Pensão por morte"


class Modality(models.IntegerChoices):  # CO_TIPO_APOSENTADORIA (SPREV)
    IDADE = 1, "Por idade"
    TEMPO_CONTRIBUICAO = 2, "Por tempo de contribuição"
    COMPULSORIA = 3, "Compulsória"
    INCAPACIDADE = 4, "Por incapacidade permanente (invalidez)"
    PROFESSOR = 5, "De professor"
    ESPECIAL_RISCO = 6, "Especial — atividade de risco"
    ESPECIAL_INSALUBRE = 7, "Especial — agentes nocivos"


class ValidityClass(models.IntegerChoices):  # FATIMA — classificação da data de validade
    PUBLICACAO = 1, "Data da publicação"
    LAUDO = 2, "Data do laudo médico"
    REQUERIMENTO = 3, "Data do requerimento"
    AFASTAMENTO = 4, "Data do afastamento"
    LIMITE_PERMANENCIA = 5, "Data limite de permanência (compulsória)"
    OUTRA = 6, "Outra"


class ActNature(models.TextChoices):
    PORTARIA = "PORTARIA", "Portaria"
    DECRETO = "DECRETO", "Decreto"
    RESOLUCAO = "RESOLUCAO", "Resolução"
    OUTROS = "OUTROS", "Outros"


class ConcessionKind(models.TextChoices):
    APOSENTADORIA = "APOSENTADORIA", "Aposentadoria"
    PENSAO = "PENSAO", "Pensão por morte"
    REVISAO = "REVISAO", "Revisão de benefício"


class Stage(models.TextChoices):
    """Etapas do mapeamento da PREVIBAM (Benefícios → Jurídico → Controle Interno → Presidência → Folha → TCE-RJ)."""
    INSTRUCAO = "INSTRUCAO", "Em instrução (Benefícios)"
    ENQUADRADO = "ENQUADRADO", "Enquadrado (Benefícios)"
    CALCULADO = "CALCULADO", "Calculado (Benefícios)"
    ANALISE_JURIDICA = "ANALISE_JURIDICA", "Parecer jurídico"
    CONTROLE_INTERNO = "CONTROLE_INTERNO", "Controle Interno"
    PRESIDENCIA = "PRESIDENCIA", "Presidência"
    ATO_EMITIDO = "ATO_EMITIDO", "Portaria assinada"
    PUBLICADO = "PUBLICADO", "Publicado"
    IMPLANTADO = "IMPLANTADO", "Implantado na folha"
    INDEFERIDO = "INDEFERIDO", "Indeferido"
    ANULADO = "ANULADO", "Anulado (julgamento TCE-RJ)"
    SOBRESTADO = "SOBRESTADO", "Sobrestado (pausado)"
    DESISTENCIA = "DESISTENCIA", "Arquivado por desistência"


# Etapas em que o processo pode ser sobrestado ou arquivado por desistência: antes da assinatura da portaria.
# Depois dela, só a Presidência pode tornar o ato sem efeito (fora deste fluxo).
PAUSABLE_STAGES = ["INSTRUCAO", "ENQUADRADO", "CALCULADO", "ANALISE_JURIDICA", "CONTROLE_INTERNO", "PRESIDENCIA"]


STAGE_ORDER = [Stage.INSTRUCAO, Stage.ENQUADRADO, Stage.CALCULADO, Stage.ANALISE_JURIDICA, Stage.CONTROLE_INTERNO,
               Stage.PRESIDENCIA, Stage.ATO_EMITIDO, Stage.PUBLICADO, Stage.IMPLANTADO]


class TceResult(models.TextChoices):
    LEGAL = "LEGAL", "Legal (registrado)"
    RESSALVA = "RESSALVA", "Legal com ressalva"
    ILEGAL = "ILEGAL", "Ilegal (negado registro)"


class Concession(InstitutionScopedModel):
    process = models.ForeignKey("protocolo.Process", on_delete=models.PROTECT, related_name="concessions",
                                verbose_name="processo (Protocolo)")
    kind = models.CharField("tipo", max_length=15, choices=ConcessionKind.choices)
    stage = models.CharField("etapa", max_length=20, choices=Stage.choices, default=Stage.INSTRUCAO)
    # Revisão: benefício revisto e novo valor proposto
    revised_benefit = models.ForeignKey("concessao.Benefit", on_delete=models.PROTECT, null=True, blank=True,
                                        related_name="revisions", verbose_name="benefício revisto")
    revision_reason = models.TextField("motivo da revisão", blank=True)
    # Aposentadoria: servidor. Pensão: instituidor (falecido).
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="concessions",
                               verbose_name="servidor / instituidor")
    link = models.ForeignKey("employment.EmploymentLink", on_delete=models.PROTECT, null=True, blank=True,
                             related_name="concessions", verbose_name="vínculo")
    instituidor_benefit = models.ForeignKey("concessao.Benefit", on_delete=models.PROTECT, null=True, blank=True,
                                            related_name="+", verbose_name="aposentadoria do instituidor (pensão)")
    modality = models.PositiveSmallIntegerField("modalidade", choices=Modality.choices, null=True, blank=True)
    rule = models.ForeignKey("previdencia.RetirementRule", on_delete=models.PROTECT, null=True, blank=True,
                             related_name="+", verbose_name="regra")
    legal_basis = models.CharField("fundamentação legal", max_length=255, blank=True)
    local_legal_basis = models.CharField("legislação local", max_length=255, blank=True)
    request_date = models.DateField("data do requerimento", null=True, blank=True)
    validity_date = models.DateField("data de validade (início do benefício)", null=True, blank=True)
    validity_class = models.PositiveSmallIntegerField("classificação da data de validade",
                                                      choices=ValidityClass.choices, null=True, blank=True)
    validity_legal_basis = models.CharField("fundamento da data de validade", max_length=255, blank=True)
    death_date = models.DateField("data do óbito (pensão)", null=True, blank=True)
    judicial = models.BooleanField("decorre de decisão judicial", default=False)
    judicial_process = models.CharField("processo judicial", max_length=40, blank=True)
    # Incapacidade
    invalidity_cause = models.PositiveSmallIntegerField(
        "causa da incapacidade", null=True, blank=True,
        choices=[(1, "Acidente em serviço"), (2, "Moléstia profissional"), (3, "Doença grave, contagiosa ou incurável"),
                 (4, "Outras")])
    cid = models.CharField("CID", max_length=10, blank=True)
    medical_report_date = models.DateField("data do laudo médico", null=True, blank=True)
    # Análise e cálculo
    analysis = models.JSONField("enquadramento (fotografia da simulação)", default=dict, blank=True)
    calculation = models.JSONField("memória de cálculo", default=dict, blank=True)
    integralidade = models.BooleanField("integralidade", default=False)
    paridade = models.BooleanField("paridade", default=False)
    total = models.DecimalField("valor total dos proventos / pensão", max_digits=15, decimal_places=2,
                                null=True, blank=True)
    opinion = models.TextField("parecer jurídico", blank=True)
    compliance_opinion = models.TextField("análise do Controle Interno", blank=True)
    returned_count = models.PositiveSmallIntegerField("devoluções para correção", default=0)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+", verbose_name="portaria assinada por (Presidência)")
    approved_at = models.DateTimeField("assinada em", null=True, blank=True)
    signed_snapshot = models.JSONField("dados fixados na assinatura", default=dict, blank=True)
    signed_hash = models.CharField("hash SHA-256 da assinatura", max_length=64, blank=True)
    # TCE-RJ (homologação) e anulação
    tce_sent_date = models.DateField("enviado ao TCE-RJ em", null=True, blank=True)
    tce_reference = models.CharField("nº do processo no TCE-RJ", max_length=60, blank=True)
    tce_result = models.CharField("julgamento do TCE-RJ", max_length=10, choices=TceResult.choices, blank=True)
    tce_result_date = models.DateField("data do julgamento", null=True, blank=True)
    tce_notes = models.TextField("observações do julgamento", blank=True)
    annulled_at = models.DateTimeField("anulada em", null=True, blank=True)
    annulment_act = models.CharField("portaria de anulação", max_length=120, blank=True)
    # Ato
    act_nature = models.CharField("natureza do ato", max_length=10, choices=ActNature.choices, blank=True)
    act_number = models.CharField("nº do ato", max_length=30, blank=True)
    act_date = models.DateField("data de emissão do ato", null=True, blank=True)
    publication_date = models.DateField("data de publicação", null=True, blank=True)
    publication_media = models.CharField("meio de publicação", max_length=150, blank=True)
    implanted_at = models.DateTimeField("implantado em", null=True, blank=True)
    rejection_reason = models.TextField("motivo do indeferimento", blank=True)
    # Sobrestamento (pausa) e desistência
    suspended_from = models.CharField("etapa antes do sobrestamento", max_length=20, blank=True)
    suspended_since = models.DateField("sobrestado desde", null=True, blank=True)
    suspended_until = models.DateField("sobrestado até (previsão de retomada)", null=True, blank=True)
    suspension_reason = models.TextField("motivo do sobrestamento", blank=True)
    withdrawal_reason = models.TextField("motivo da desistência", blank=True)
    withdrawn_at = models.DateTimeField("arquivado por desistência em", null=True, blank=True)

    class Meta:
        db_table = "concessions"
        verbose_name = "processo de concessão"
        verbose_name_plural = "processos de concessão"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.person} ({self.process})"


class Parcel(InstitutionScopedModel):
    """Parcela do ato de fixação de proventos (Passo 5 do FATIMA) ou da última remuneração (Passo 3)."""

    concession = models.ForeignKey(Concession, on_delete=models.CASCADE, related_name="parcels",
                                   verbose_name="concessão")
    kind = models.CharField("quadro", max_length=12, choices=[("PROVENTO", "Proventos"),
                                                               ("REMUNERACAO", "Última remuneração")])
    name = models.CharField("parcela", max_length=60)
    legal_basis = models.CharField("fundamentação legal", max_length=100, blank=True)
    correlation = models.CharField("verba de correlação", max_length=40, blank=True)
    percent = models.DecimalField("percentual", max_digits=7, decimal_places=3, null=True, blank=True)
    proportionality = models.DecimalField("fator de proporcionalidade", max_digits=7, decimal_places=4, null=True,
                                          blank=True)
    amount = models.DecimalField("valor", max_digits=15, decimal_places=2)
    in_reference = models.BooleanField("integra a remuneração de referência", default=True)

    class Meta:
        db_table = "concession_parcels"
        verbose_name = "parcela"
        ordering = ["kind", "id"]


class QuotaDuration(models.TextChoices):
    VITALICIA = "VITALICIA", "Vitalícia"
    TEMPORARIA = "TEMPORARIA", "Temporária"


class PensionQuota(InstitutionScopedModel):
    """Cota de pensão por dependente habilitado (proposta na concessão)."""

    concession = models.ForeignKey(Concession, on_delete=models.CASCADE, related_name="quotas",
                                   verbose_name="concessão")
    dependent = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="+",
                                  verbose_name="dependente")
    relation = models.PositiveSmallIntegerField(  # CO_TIPO_RELACAO (SPREV)
        "relação com o instituidor",
        choices=[(1, "Cônjuge / companheiro(a)"), (2, "Filho(a) menor"), (3, "Filho(a) inválido(a) ou com deficiência"),
                 (4, "Pais"), (5, "Irmão(ã)"), (6, "Outros")])
    percent = models.DecimalField("percentual da cota", max_digits=7, decimal_places=3)
    amount = models.DecimalField("valor da cota", max_digits=15, decimal_places=2)
    duration = models.CharField("duração", max_length=10, choices=QuotaDuration.choices)
    end_date = models.DateField("fim previsto", null=True, blank=True)
    duration_basis = models.CharField("fundamento da duração", max_length=255, blank=True)
    request_date = models.DateField("data do requerimento", null=True, blank=True)

    class Meta:
        db_table = "pension_quotas"
        verbose_name = "cota de pensão"
        constraints = [models.UniqueConstraint(fields=["concession", "dependent"], name="uq_quota_dependent")]


class BenefitStatus(models.TextChoices):
    ATIVO = "ATIVO", "Ativo"
    SUSPENSO = "SUSPENSO", "Suspenso"
    CESSADO = "CESSADO", "Cessado"


class Benefit(InstitutionScopedModel):
    """Benefício implantado (base da folha da Fase 5)."""

    kind = models.CharField("tipo", max_length=15, choices=BenefitKind.choices)
    modality = models.PositiveSmallIntegerField("modalidade", choices=Modality.choices, null=True, blank=True)
    beneficiary = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="benefits",
                                    verbose_name="beneficiário")
    instituidor = models.ForeignKey("people.Person", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                    verbose_name="instituidor (pensão)")
    concession = models.ForeignKey(Concession, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="benefits", verbose_name="concessão")
    legacy = models.OneToOneField("people.LegacyBenefit", on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="benefit", verbose_name="benefício importado")
    payroll_group = models.ForeignKey("institutions.PayrollGroup", on_delete=models.PROTECT, related_name="benefits",
                                      verbose_name="folha")
    life_purchase = models.ForeignKey("institutions.LifePurchase", on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="+", verbose_name="lote de compra de vidas")
    registration = models.CharField("matrícula do benefício", max_length=30, blank=True)
    legal_basis = models.CharField("fundamentação", max_length=255, blank=True)
    start_date = models.DateField("início do benefício")
    end_date = models.DateField("fim previsto / cessação", null=True, blank=True)
    amount = models.DecimalField("valor mensal", max_digits=15, decimal_places=2)
    percent = models.DecimalField("percentual da cota (pensão)", max_digits=7, decimal_places=3, null=True, blank=True)
    integralidade = models.BooleanField("integralidade", default=False)
    paridade = models.BooleanField("paridade", default=False)
    status = models.CharField("situação", max_length=10, choices=BenefitStatus.choices, default=BenefitStatus.ATIVO)
    # eSocial (S-2410 / S-2420)
    esocial_nr = models.CharField("nº do benefício no eSocial", max_length=20, blank=True)
    esocial_tp_beneficio = models.CharField("tipo de benefício (eSocial, Tabela 25)", max_length=4, blank=True)
    esocial_mtv_termino = models.CharField("motivo do término (eSocial, Tabela 26)", max_length=2, blank=True)

    class Meta:
        db_table = "benefits"
        verbose_name = "benefício"
        ordering = ["beneficiary__name"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="ck_benefit_amount"),
            models.CheckConstraint(condition=~Q(kind="PENSAO") | Q(instituidor__isnull=False),
                                   name="ck_benefit_pension_instituidor"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.beneficiary}"


class BenefitEventKind(models.TextChoices):
    IMPLANTACAO = "IMPLANTACAO", "Implantação"
    REVISAO = "REVISAO", "Revisão"
    SUSPENSAO = "SUSPENSAO", "Suspensão"
    RESTABELECIMENTO = "RESTABELECIMENTO", "Restabelecimento"
    CESSACAO = "CESSACAO", "Cessação"
    REVERSAO = "REVERSAO", "Reversão"


class BenefitEvent(InstitutionScopedModel):
    """Histórico do benefício (imutável)."""

    benefit = models.ForeignKey(Benefit, on_delete=models.PROTECT, related_name="events", verbose_name="benefício")
    kind = models.CharField("tipo", max_length=16, choices=BenefitEventKind.choices)
    date = models.DateField("data de efeito")
    justification = models.TextField("justificativa / fundamento")
    act = models.CharField("ato", max_length=100, blank=True)
    old_values = models.JSONField("valores anteriores", default=dict, blank=True)
    new_values = models.JSONField("valores novos", default=dict, blank=True)
    process = models.ForeignKey("protocolo.Process", on_delete=models.PROTECT, null=True, blank=True,
                                related_name="+", verbose_name="processo")

    class Meta:
        db_table = "benefit_events"
        verbose_name = "evento do benefício"
        ordering = ["date", "created_at"]


class StepAction(models.TextChoices):
    INSTRUCAO = "INSTRUCAO", "Instrução (enquadramento/cálculo)"
    ENVIO_JURIDICO = "ENVIO_JURIDICO", "Enviado ao Jurídico"
    PARECER_FAVORAVEL = "PARECER_FAVORAVEL", "Parecer jurídico favorável"
    DEVOLUCAO_JURIDICO = "DEVOLUCAO_JURIDICO", "Devolvido pelo Jurídico para correção"
    CONFORMIDADE = "CONFORMIDADE", "Conformidade do Controle Interno"
    DEVOLUCAO_CONTROLE = "DEVOLUCAO_CONTROLE", "Devolvido pelo Controle Interno"
    ASSINATURA = "ASSINATURA", "Portaria assinada pela Presidência"
    INDEFERIMENTO = "INDEFERIMENTO", "Indeferido"
    PUBLICACAO = "PUBLICACAO", "Publicação registrada"
    IMPLANTACAO = "IMPLANTACAO", "Implantado na folha"
    ENVIO_TCE = "ENVIO_TCE", "Enviado ao TCE-RJ"
    JULGAMENTO_TCE = "JULGAMENTO_TCE", "Julgamento do TCE-RJ"
    ANULACAO = "ANULACAO", "Concessão anulada"
    DOCUMENTO = "DOCUMENTO", "Documento gerado"
    SOBRESTAMENTO = "SOBRESTAMENTO", "Processo sobrestado (pausado)"
    RETOMADA = "RETOMADA", "Processo retomado"
    DESISTENCIA = "DESISTENCIA", "Arquivado por desistência do requerente"


# Papel de quem praticou o ato — base da segregação de funções
STEP_ROLE = {
    StepAction.INSTRUCAO: "INSTRUCAO", StepAction.ENVIO_JURIDICO: "INSTRUCAO",
    StepAction.PARECER_FAVORAVEL: "JURIDICO", StepAction.DEVOLUCAO_JURIDICO: "JURIDICO",
    StepAction.CONFORMIDADE: "CONTROLE", StepAction.DEVOLUCAO_CONTROLE: "CONTROLE",
    StepAction.ASSINATURA: "PRESIDENCIA", StepAction.INDEFERIMENTO: "PRESIDENCIA", StepAction.ANULACAO: "PRESIDENCIA",
    StepAction.IMPLANTACAO: "IMPLANTACAO", StepAction.PUBLICACAO: "IMPLANTACAO",
}


class ConcessionStep(InstitutionScopedModel):
    """Trilha da concessão: quem fez o quê, quando e com que fundamento. Somente inclusão (nunca alterada)."""

    concession = models.ForeignKey(Concession, on_delete=models.PROTECT, related_name="steps", verbose_name="concessão")
    action = models.CharField("ato", max_length=20, choices=StepAction.choices)
    role = models.CharField("papel", max_length=12, blank=True)
    stage_from = models.CharField("etapa anterior", max_length=20, blank=True)
    stage_to = models.CharField("etapa seguinte", max_length=20, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+", verbose_name="usuário")
    text = models.TextField("parecer / fundamento", blank=True)
    data = models.JSONField("dados", default=dict, blank=True)
    signed = models.BooleanField("confirmado com senha (assinatura eletrônica)", default=False)
    signature_hash = models.CharField("hash SHA-256", max_length=64, blank=True)

    class Meta:
        db_table = "concession_steps"
        verbose_name = "ato da concessão"
        ordering = ["created_at"]


class DocumentKind(models.TextChoices):
    MINUTA_PORTARIA = "MINUTA_PORTARIA", "Minuta de portaria"
    PORTARIA = "PORTARIA", "Portaria"
    CIENCIA_INDEFERIMENTO = "CIENCIA_INDEFERIMENTO", "Ofício de ciência de indeferimento"
    MINUTA_ANULACAO = "MINUTA_ANULACAO", "Minuta de portaria de anulação"
    PORTARIA_ANULACAO = "PORTARIA_ANULACAO", "Portaria de anulação"
    TERMO_DESISTENCIA = "TERMO_DESISTENCIA", "Termo de desistência e arquivamento"
    RELATORIO_INSTRUCAO = "RELATORIO_INSTRUCAO", "Relatório de instrução (tempo, enquadramento e cálculo)"
    PARECER_JURIDICO = "PARECER_JURIDICO", "Parecer jurídico"
    PARECER_CONTROLE = "PARECER_CONTROLE", "Análise de conformidade (Controle Interno)"


class ConcessionDocument(InstitutionScopedModel):
    """Documento gerado pelo sistema (Word), anexado também ao processo do Protocolo."""

    concession = models.ForeignKey(Concession, on_delete=models.PROTECT, related_name="documents",
                                   verbose_name="concessão")
    kind = models.CharField("tipo", max_length=24, choices=DocumentKind.choices)
    version = models.PositiveSmallIntegerField("versão", default=1)
    file = models.FileField("arquivo", upload_to="concessao/%Y/%m/")
    file_name = models.CharField("nome do arquivo", max_length=200)
    sha256 = models.CharField("SHA-256", max_length=64)
    attachment = models.ForeignKey("protocolo.Attachment", on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+", verbose_name="anexo no Protocolo")

    class Meta:
        db_table = "concession_documents"
        verbose_name = "documento da concessão"
        ordering = ["-created_at"]


class DocumentTemplate(InstitutionScopedModel):
    """Modelo de texto das portarias e ofícios (editável pela instituição; marcadores entre chaves)."""

    kind = models.CharField("documento", max_length=24, choices=DocumentKind.choices)
    concession_kind = models.CharField("tipo de concessão", max_length=15, choices=ConcessionKind.choices, blank=True,
                                       help_text="Vazio = vale para todos os tipos.")
    title = models.CharField("título", max_length=150)
    body = models.TextField("texto (um parágrafo por linha)")
    signer = models.CharField("assinatura (nome e cargo)", max_length=200, blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "document_templates"
        verbose_name = "modelo de documento"
        ordering = ["kind", "concession_kind"]


# ---------------------------------------------------------------------------- processo digital: checklist
class ChecklistSector(models.TextChoices):
    """Setor responsável pelo item; cada setor só libera o processo com o seu checklist completo e assinado."""
    BENEFICIOS = "BENEFICIOS", "Benefícios"
    JURIDICO = "JURIDICO", "Procuradoria Jurídica"
    CONTROLE = "CONTROLE", "Controle Interno"
    PRESIDENCIA = "PRESIDENCIA", "Presidência"
    FOLHA = "FOLHA", "Folha de Pagamento"


# Etapa da concessão -> setor que está com o processo (e que pode anexar no seu checklist)
SECTOR_BY_STAGE = {
    "INSTRUCAO": "BENEFICIOS", "ENQUADRADO": "BENEFICIOS", "CALCULADO": "BENEFICIOS",
    "ANALISE_JURIDICA": "JURIDICO", "CONTROLE_INTERNO": "CONTROLE", "PRESIDENCIA": "PRESIDENCIA",
    "ATO_EMITIDO": "FOLHA", "PUBLICADO": "FOLHA",
}


class ChecklistSource(models.TextChoices):
    ANEXO = "ANEXO", "Anexar documento"
    SISTEMA = "SISTEMA", "Gerado pelo sistema"


class ChecklistTemplate(InstitutionScopedModel):
    """Documento exigido no processo digital (configurável pela instituição em Concessão › Checklist)."""

    concession_kind = models.CharField("tipo de processo", max_length=15, choices=ConcessionKind.choices)
    modality = models.PositiveSmallIntegerField("só para a modalidade", choices=Modality.choices, null=True, blank=True,
                                                help_text="Vazio = todas as modalidades.")
    sector = models.CharField("setor", max_length=12, choices=ChecklistSector.choices)
    name = models.CharField("documento", max_length=200)
    help_text = models.CharField("orientação", max_length=300, blank=True)
    source = models.CharField("origem", max_length=8, choices=ChecklistSource.choices, default=ChecklistSource.ANEXO)
    system_kind = models.CharField("documento do sistema", max_length=24, choices=DocumentKind.choices, blank=True)
    person_doc_type = models.CharField("guardar também no Cadastro Único como", max_length=20, blank=True,
                                       help_text="Tipo de documento da pessoa (identidade, comprovante de residência...).")
    required = models.BooleanField("obrigatório", default=True)
    order = models.PositiveSmallIntegerField("ordem", default=0)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "concession_checklist_templates"
        verbose_name = "item de checklist (modelo)"
        ordering = ["concession_kind", "sector", "order", "name"]


class ChecklistStatus(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    CUMPRIDO = "CUMPRIDO", "Anexado / gerado"
    NAO_SE_APLICA = "NAO_SE_APLICA", "Não se aplica (justificado)"


class ChecklistItem(InstitutionScopedModel):
    """Item do checklist de um processo. O arquivo fica no Protocolo (com SHA-256); substituir mantém o anterior."""

    concession = models.ForeignKey(Concession, on_delete=models.PROTECT, related_name="checklist",
                                   verbose_name="concessão")
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    sector = models.CharField("setor", max_length=12, choices=ChecklistSector.choices)
    name = models.CharField("documento", max_length=200)
    help_text = models.CharField("orientação", max_length=300, blank=True)
    source = models.CharField("origem", max_length=8, choices=ChecklistSource.choices)
    system_kind = models.CharField("documento do sistema", max_length=24, blank=True)
    person_doc_type = models.CharField("tipo no Cadastro Único", max_length=20, blank=True)
    person_document = models.ForeignKey("people.Document", on_delete=models.PROTECT, null=True, blank=True,
                                        related_name="+", verbose_name="documento no Cadastro Único")
    required = models.BooleanField("obrigatório", default=True)
    order = models.PositiveSmallIntegerField("ordem", default=0)
    status = models.CharField("situação", max_length=14, choices=ChecklistStatus.choices,
                              default=ChecklistStatus.PENDENTE)
    attachment = models.ForeignKey("protocolo.Attachment", on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+", verbose_name="anexo")
    document = models.ForeignKey(ConcessionDocument, on_delete=models.PROTECT, null=True, blank=True,
                                 related_name="+", verbose_name="documento gerado")
    sha256 = models.CharField("SHA-256 do arquivo", max_length=64, blank=True)
    note = models.TextField("justificativa (não se aplica)", blank=True)
    done_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                related_name="+", verbose_name="registrado por")
    done_at = models.DateTimeField("registrado em", null=True, blank=True)

    class Meta:
        db_table = "concession_checklist_items"
        verbose_name = "item de checklist"
        ordering = ["sector", "order", "name"]
