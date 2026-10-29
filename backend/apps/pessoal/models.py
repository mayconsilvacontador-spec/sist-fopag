"""
Folha de ATIVOS (servidores em atividade) — separada da folha de benefícios (aposentados e pensionistas, app `folha`).

Serve a Prefeituras, Câmaras, Autarquias, Fundações e ao próprio RPPS (servidores do instituto). Uma folha por
ÓRGÃO (empregador) e competência. O vencimento vem da TABELA DE VENCIMENTOS (cargo × nível, com vigência); vantagens e
descontos vêm das RUBRICAS e dos LANÇAMENTOS de cada vínculo; a contribuição ao RPPS e o IRRF são calculados. O
contracheque guarda o que foi pago (código, nome e valor de cada rubrica) — mudar a rubrica depois não altera o passado.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel, ValidityModel


class SalaryScale(InstitutionScopedModel, ValidityModel):
    """Tabela de vencimentos: valor do cargo (e nível/referência) a partir de uma data. Reajuste = nova vigência."""

    position = models.ForeignKey("cadastros.Position", on_delete=models.PROTECT, related_name="+", verbose_name="cargo")
    level = models.CharField("nível / referência", max_length=50, blank=True,
                             help_text="Igual ao 'classe / nível' do vínculo. Vazio = vale para todos os níveis.")
    amount = models.DecimalField("vencimento", max_digits=15, decimal_places=2)
    legal_basis = models.CharField("lei / ato", max_length=200, blank=True)

    class Meta:
        db_table = "salary_scales"
        ordering = ["position__name", "level", "-valid_from"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "position", "level", "valid_from"], name="uq_salary_scale"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="ck_salary_scale_amount"),
        ]


class RubricKind(models.TextChoices):
    PROVENTO = "PROVENTO", "Provento (vantagem)"
    DESCONTO = "DESCONTO", "Desconto"


class RubricCalc(models.TextChoices):
    VENCIMENTO = "VENCIMENTO", "Vencimento (tabela de vencimentos)"
    ADICIONAL_TEMPO = "ADICIONAL_TEMPO", "Adicional por tempo de serviço (% do vencimento)"
    LANCAMENTO = "LANCAMENTO", "Lançamento (valor fixo ou % do vencimento)"
    FALTAS = "FALTAS", "Faltas (desconto pelos dias do histórico funcional)"
    CONTRIB_RPPS = "CONTRIB_RPPS", "Contribuição ao RPPS (calculada)"
    IRRF = "IRRF", "IRRF (calculado)"


AUTOMATIC = {RubricCalc.VENCIMENTO, RubricCalc.ADICIONAL_TEMPO, RubricCalc.FALTAS, RubricCalc.CONTRIB_RPPS,
             RubricCalc.IRRF}


class ActiveRubric(InstitutionScopedModel):
    code = models.CharField("código", max_length=10)
    name = models.CharField("nome", max_length=120)
    kind = models.CharField("tipo", max_length=10, choices=RubricKind.choices)
    calc = models.CharField("forma de cálculo", max_length=20, choices=RubricCalc.choices, default=RubricCalc.LANCAMENTO)
    inc_rpps = models.BooleanField("incide contribuição ao RPPS", default=True)
    inc_ir = models.BooleanField("incide IRRF", default=True)
    # adicional por tempo: percentual a cada N anos, com limite
    percent = models.DecimalField("percentual por período", max_digits=6, decimal_places=2, null=True, blank=True)
    period_years = models.PositiveSmallIntegerField("a cada (anos)", null=True, blank=True)
    max_percent = models.DecimalField("limite (%)", max_digits=6, decimal_places=2, null=True, blank=True)
    legal_basis = models.CharField("fundamentação", max_length=200, blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "active_rubrics"
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="uq_active_rubric_code")]

    def __str__(self):
        return f"{self.code} — {self.name}"


class ActiveEntry(InstitutionScopedModel):
    """Lançamento de um vínculo: gratificação, função, hora extra, consignação, desconto diverso..."""

    link = models.ForeignKey("employment.EmploymentLink", on_delete=models.PROTECT, related_name="active_entries",
                             verbose_name="vínculo")
    rubric = models.ForeignKey(ActiveRubric, on_delete=models.PROTECT, related_name="entries", verbose_name="rubrica")
    amount = models.DecimalField("valor", max_digits=15, decimal_places=2, null=True, blank=True)
    percent = models.DecimalField("% do vencimento", max_digits=7, decimal_places=3, null=True, blank=True)
    start = models.DateField("a partir da competência")
    end = models.DateField("até a competência", null=True, blank=True)
    installments = models.PositiveSmallIntegerField("parcelas", null=True, blank=True)
    paid_installments = models.PositiveSmallIntegerField("parcelas pagas", default=0)
    reference = models.CharField("referência / contrato", max_length=60, blank=True)
    notes = models.TextField("observações", blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "active_entries"
        ordering = ["link__person__name", "rubric__code"]


class RunStatus(models.TextChoices):
    ABERTA = "ABERTA", "Aberta"
    CALCULADA = "CALCULADA", "Calculada"
    CONFERIDA = "CONFERIDA", "Conferida"
    FECHADA = "FECHADA", "Fechada"


EDITABLE = {RunStatus.ABERTA, RunStatus.CALCULADA, RunStatus.CONFERIDA}


class ActiveRun(InstitutionScopedModel):
    """Folha mensal de um órgão (empregador)."""

    organ = models.ForeignKey("cadastros.Organ", on_delete=models.PROTECT, related_name="+", verbose_name="órgão")
    year = models.PositiveSmallIntegerField("ano")
    month = models.PositiveSmallIntegerField("mês")
    status = models.CharField("situação", max_length=10, choices=RunStatus.choices, default=RunStatus.ABERTA)
    totals = models.JSONField("totais", default=dict, blank=True)
    warnings = models.JSONField("avisos", default=list, blank=True)
    calculated_at = models.DateTimeField("calculada em", null=True, blank=True)
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+")
    checked_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    close_effects = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "active_runs"
        ordering = ["-year", "-month", "organ__name"]
        constraints = [models.UniqueConstraint(fields=["institution", "organ", "year", "month"],
                                               name="uq_active_run")]

    def __str__(self):
        return f"Folha de ativos {self.month:02d}/{self.year} — {self.organ}"


class ActivePayslip(InstitutionScopedModel):
    run = models.ForeignKey(ActiveRun, on_delete=models.CASCADE, related_name="payslips")
    link = models.ForeignKey("employment.EmploymentLink", on_delete=models.PROTECT, related_name="+")
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="+")
    registration = models.CharField("matrícula", max_length=20)
    position_name = models.CharField("cargo", max_length=150)
    segment = models.CharField("massa (fundo)", max_length=20)
    days = models.PositiveSmallIntegerField("dias trabalhados", default=30)
    gross = models.DecimalField("proventos", max_digits=15, decimal_places=2, default=0)
    discounts = models.DecimalField("descontos", max_digits=15, decimal_places=2, default=0)
    net = models.DecimalField("líquido", max_digits=15, decimal_places=2, default=0)
    rpps_base = models.DecimalField("base de contribuição", max_digits=15, decimal_places=2, default=0)
    employer_contribution = models.DecimalField("contribuição patronal", max_digits=15, decimal_places=2, default=0)
    ir_base = models.DecimalField("base do IRRF", max_digits=15, decimal_places=2, default=0)
    bank = models.JSONField("conta de crédito", default=dict, blank=True)
    memory = models.JSONField("memória de cálculo", default=dict, blank=True)
    warnings = models.JSONField("avisos", default=list, blank=True)

    class Meta:
        db_table = "active_payslips"
        ordering = ["person__name"]


class ActivePayslipItem(InstitutionScopedModel):
    payslip = models.ForeignKey(ActivePayslip, on_delete=models.CASCADE, related_name="items")
    rubric = models.ForeignKey(ActiveRubric, on_delete=models.PROTECT, null=True, related_name="+")
    source_entry = models.ForeignKey(ActiveEntry, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    code = models.CharField("código", max_length=10)
    name = models.CharField("descrição", max_length=120)
    kind = models.CharField("tipo", max_length=10, choices=RubricKind.choices)
    reference = models.CharField("referência", max_length=30, blank=True)
    amount = models.DecimalField("valor", max_digits=15, decimal_places=2)

    class Meta:
        db_table = "active_payslip_items"
        ordering = ["kind", "code"]


# ============================================================ ficha financeira (histórico importado)
class FinancialCategory(models.TextChoices):
    """Papel da rubrica no controle da contribuição (o código/nome variam de sistema para sistema)."""

    NENHUMA = "", "Outras"
    CONTRIB_RPPS = "CONTRIB_RPPS", "Contribuição do servidor ao RPPS (desconto)"
    BASE_RPPS = "BASE_RPPS", "Base de contribuição ao RPPS (informativa)"
    INCIDE_RPPS = "INCIDE_RPPS", "Provento que entra na base do RPPS"
    PATRONAL = "PATRONAL", "Contribuição patronal (informativa)"
    IRRF = "IRRF", "Imposto de renda (desconto)"


class FinancialImport(InstitutionScopedModel):
    """Arquivo de ficha financeira importado (sistema anterior da Prefeitura/órgão)."""

    file_name = models.CharField("arquivo", max_length=255)
    sha256 = models.CharField("hash do arquivo", max_length=64)
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                               verbose_name="servidor (importação individual)")
    summary = models.JSONField("resumo", default=dict, blank=True)

    class Meta:
        db_table = "financial_imports"
        ordering = ["-created_at"]


class FinancialLine(InstitutionScopedModel):
    """
    Linha da ficha financeira IMPORTADA: uma rubrica de um vínculo numa competência. A ficha gerada pelo SIST junta
    estas linhas com os contracheques da Folha de Ativos (que não são copiados para cá).
    """

    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="financial_lines")
    link = models.ForeignKey("employment.EmploymentLink", on_delete=models.PROTECT, null=True, blank=True,
                             related_name="financial_lines")
    registration = models.CharField("matrícula", max_length=20, blank=True)
    competence = models.DateField("competência (1º dia do mês)")
    payroll_kind = models.CharField("folha", max_length=12, default="MENSAL",
                                    choices=[("MENSAL", "Mensal"), ("DECIMO", "13º salário"), ("FERIAS", "Férias"),
                                             ("RESCISAO", "Rescisão"), ("COMPLEMENTAR", "Complementar")])
    code = models.CharField("código da rubrica", max_length=20)
    name = models.CharField("rubrica", max_length=120)
    nature = models.CharField("natureza", max_length=10,
                              choices=[("PROVENTO", "Provento"), ("DESCONTO", "Desconto"), ("BASE", "Base / informativa")])
    category = models.CharField("classificação", max_length=14, choices=FinancialCategory.choices, blank=True)
    amount = models.DecimalField("valor", max_digits=15, decimal_places=2)
    batch = models.ForeignKey(FinancialImport, on_delete=models.PROTECT, related_name="lines")

    class Meta:
        db_table = "financial_lines"
        ordering = ["competence", "nature", "code"]
        indexes = [models.Index(fields=["person", "competence"])]
        constraints = [models.UniqueConstraint(fields=["person", "registration", "competence", "payroll_kind", "code"],
                                               name="uniq_financial_line")]
