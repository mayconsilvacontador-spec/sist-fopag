"""
Motor da folha de benefícios (Fase 5).

- Rubrica: versionada (nova versão encerra a anterior). Cada item de folha guarda a
  VERSÃO usada, permitindo reproduzir folhas fechadas.
- Lançamento: valor fixo/variável por benefício (consignação, pensão alimentícia,
  diferenças), com competência inicial/final e parcelas.
- Folha (PayrollRun): uma por competência × folha (massa) × tipo. Etapas:
  ABERTA -> CALCULADA -> CONFERIDA -> FECHADA -> PAGA (reabertura com justificativa).
  Folha fechada não é recalculada; folha paga é imutável.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel


class RubricKind(models.TextChoices):
    PROVENTO = "PROVENTO", "Provento"
    DESCONTO = "DESCONTO", "Desconto"
    INFORMATIVA = "INFORMATIVA", "Informativa"


class RubricCalc(models.TextChoices):
    APOSENTADORIA = "APOSENTADORIA", "Proventos de aposentadoria (proporcional aos dias)"
    PENSAO = "PENSAO", "Pensão por morte (proporcional aos dias)"
    RETROATIVO = "RETROATIVO", "Retroativo do benefício (meses anteriores)"
    DECIMO = "DECIMO", "Gratificação natalina (13º)"
    CONTRIB_RPPS = "CONTRIB_RPPS", "Contribuição ao RPPS"
    CONTRIB_13 = "CONTRIB_13", "Contribuição ao RPPS sobre o 13º"
    IRRF = "IRRF", "IRRF"
    IRRF_13 = "IRRF_13", "IRRF sobre o 13º (tributação exclusiva)"
    IRRF_RRA = "IRRF_RRA", "IRRF sobre rendimentos acumulados (RRA)"
    PENSAO_ALIMENTICIA = "PENSAO_ALIMENTICIA", "Pensão alimentícia"
    PENSAO_ALIMENTICIA_13 = "PENSAO_ALIMENTICIA_13", "Pensão alimentícia sobre o 13º"
    CONSIGNACAO = "CONSIGNACAO", "Consignação"
    MANUAL = "MANUAL", "Lançamento (valor informado)"


# Formas de cálculo automáticas: só pode haver uma rubrica ativa de cada
AUTOMATIC_CALCS = {c for c in RubricCalc.values if c not in ("CONSIGNACAO", "MANUAL")}
# Formas que aceitam lançamentos por benefício
ENTRY_CALCS = {"CONSIGNACAO", "MANUAL", "PENSAO_ALIMENTICIA"}


class Rubric(InstitutionScopedModel):
    code = models.CharField("código", max_length=6)
    version = models.PositiveIntegerField("versão", default=1)
    name = models.CharField("descrição", max_length=80)
    kind = models.CharField("tipo", max_length=12, choices=RubricKind.choices)
    calc = models.CharField("forma de cálculo", max_length=24, choices=RubricCalc.choices)
    inc_ir = models.BooleanField("incide IRRF", default=False)
    inc_rpps = models.BooleanField("incide contribuição RPPS", default=False)
    inc_13 = models.BooleanField("integra o 13º", default=False)
    inc_margem = models.BooleanField("integra a base da margem consignável", default=False)
    ir_deduction = models.BooleanField("dedutível do IRRF (contribuição, pensão alimentícia)", default=False)
    esocial_nature = models.CharField("natureza da rubrica (eSocial, Tabela 03)", max_length=4, blank=True)
    esocial_inc_cp = models.CharField("incidência CP/RGPS (codIncCP)", max_length=2, blank=True, default="00")
    esocial_inc_irrf = models.CharField("incidência IRRF (codIncIRRF)", max_length=4, blank=True)
    esocial_inc_cprp = models.CharField("incidência RPPS (codIncCPRP)", max_length=2, blank=True)
    valid_from = models.DateField("vigência inicial")
    valid_to = models.DateField("vigência final", null=True, blank=True)
    change_reason = models.TextField("motivo da versão", blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "payroll_rubrics"
        verbose_name = "rubrica"
        ordering = ["code", "-version"]
        constraints = [models.UniqueConstraint(fields=["institution", "code", "version"], name="uq_rubric_version")]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Consignee(InstitutionScopedModel):
    name = models.CharField("consignatária", max_length=150)
    cnpj = models.CharField("CNPJ", max_length=14, blank=True)
    kind = models.CharField("tipo", max_length=12, choices=[("BANCO", "Instituição financeira"),
                                                             ("SINDICATO", "Sindicato"), ("ASSOCIACAO", "Associação"),
                                                             ("OUTROS", "Outros")])
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "payroll_consignees"
        verbose_name = "consignatária"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Entry(InstitutionScopedModel):
    """Lançamento fixo ou por prazo em um benefício (competências no 1º dia do mês)."""

    benefit = models.ForeignKey("concessao.Benefit", on_delete=models.PROTECT, related_name="entries",
                                verbose_name="benefício")
    rubric_code = models.CharField("rubrica", max_length=6)
    description = models.CharField("descrição complementar", max_length=120, blank=True)
    amount = models.DecimalField("valor", max_digits=15, decimal_places=2, null=True, blank=True)
    percent = models.DecimalField("percentual", max_digits=7, decimal_places=3, null=True, blank=True)
    base = models.CharField("base do percentual", max_length=8, blank=True,
                            choices=[("BRUTO", "Rendimento bruto"), ("LIQUIDO", "Bruto − contribuição − IRRF")])
    start = models.DateField("competência inicial")
    end = models.DateField("competência final", null=True, blank=True)
    installments = models.PositiveSmallIntegerField("nº de parcelas", null=True, blank=True)
    paid_installments = models.PositiveSmallIntegerField("parcelas pagas", default=0)
    consignee = models.ForeignKey(Consignee, on_delete=models.PROTECT, null=True, blank=True, related_name="entries",
                                  verbose_name="consignatária")
    contract = models.CharField("contrato / processo judicial", max_length=60, blank=True)
    alimony_beneficiary = models.ForeignKey("people.Person", on_delete=models.PROTECT, null=True, blank=True,
                                            related_name="+", verbose_name="alimentando (pensão alimentícia)")
    on_13 = models.BooleanField("incide também sobre o 13º (pensão alimentícia)", default=True)
    active = models.BooleanField("ativo", default=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        db_table = "payroll_entries_fixed"
        verbose_name = "lançamento"
        ordering = ["benefit", "rubric_code"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__isnull=False) | Q(percent__isnull=False),
                                   name="ck_entry_amount_or_percent"),
        ]


class IrExemption(InstitutionScopedModel):
    """Isenção de IR por moléstia grave (Lei 7.713/1988, art. 6º, XIV) — exige laudo oficial."""

    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="ir_exemptions",
                               verbose_name="beneficiário")
    start = models.DateField("início da isenção")
    end = models.DateField("fim da isenção (laudo com validade)", null=True, blank=True)
    disease = models.CharField("moléstia (Lei 7.713, art. 6º, XIV)", max_length=120)
    report = models.CharField("laudo pericial (órgão oficial, nº e data)", max_length=200)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "payroll_ir_exemptions"
        verbose_name = "isenção de IR"
        ordering = ["person__name", "-start"]


class RunKind(models.TextChoices):
    MENSAL = "MENSAL", "Mensal"
    DECIMO = "DECIMO", "13º (gratificação natalina)"


class RunStatus(models.TextChoices):
    ABERTA = "ABERTA", "Aberta"
    CALCULADA = "CALCULADA", "Calculada"
    CONFERIDA = "CONFERIDA", "Conferida"
    FECHADA = "FECHADA", "Fechada"
    PAGA = "PAGA", "Paga"


class PayrollRun(InstitutionScopedModel):
    competence = models.ForeignKey("institutions.Competence", on_delete=models.PROTECT, related_name="payroll_runs",
                                   verbose_name="competência")
    payroll_group = models.ForeignKey("institutions.PayrollGroup", on_delete=models.PROTECT, related_name="runs",
                                      verbose_name="folha")
    kind = models.CharField("tipo", max_length=12, choices=RunKind.choices, default=RunKind.MENSAL)
    sequence = models.PositiveSmallIntegerField("sequência", default=1)
    status = models.CharField("situação", max_length=10, choices=RunStatus.choices, default=RunStatus.ABERTA)
    totals = models.JSONField("totais", default=dict, blank=True)
    warnings = models.JSONField("avisos do cálculo", default=list, blank=True)
    calculated_at = models.DateTimeField("calculada em", null=True, blank=True)
    checked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+", verbose_name="conferida por")
    checked_at = models.DateTimeField("conferida em", null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+", verbose_name="fechada por")
    closed_at = models.DateTimeField("fechada em", null=True, blank=True)
    payment_date = models.DateField("data do pagamento", null=True, blank=True)
    close_effects = models.JSONField("efeitos do fechamento (para reabertura)", default=dict, blank=True)

    class Meta:
        db_table = "payroll_runs"
        verbose_name = "folha"
        ordering = ["-competence__year", "-competence__month", "payroll_group__segment", "kind", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["competence", "payroll_group", "kind", "sequence"], name="uq_payroll_run"),
        ]

    def __str__(self):
        return f"Folha {self.get_kind_display()} {self.competence} — {self.payroll_group.code}"


class PayrollEntry(InstitutionScopedModel):
    """Resultado por benefício na folha (contracheque)."""

    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="entries", verbose_name="folha")
    benefit = models.ForeignKey("concessao.Benefit", on_delete=models.PROTECT, related_name="payroll_entries",
                                verbose_name="benefício")
    beneficiary = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="payroll_entries",
                                    verbose_name="beneficiário")
    gross = models.DecimalField("rendimentos", max_digits=15, decimal_places=2, default=0)
    discounts = models.DecimalField("descontos", max_digits=15, decimal_places=2, default=0)
    net = models.DecimalField("líquido", max_digits=15, decimal_places=2, default=0)
    ir_base = models.DecimalField("base do IRRF", max_digits=15, decimal_places=2, default=0)
    rpps_base = models.DecimalField("base da contribuição", max_digits=15, decimal_places=2, default=0)
    bank = models.JSONField("conta de crédito", default=dict, blank=True)
    memory = models.JSONField("memória de cálculo", default=dict, blank=True)
    warnings = models.JSONField("avisos", default=list, blank=True)

    class Meta:
        db_table = "payroll_results"
        verbose_name = "contracheque"
        ordering = ["beneficiary__name"]
        constraints = [models.UniqueConstraint(fields=["run", "benefit"], name="uq_payroll_result")]


class PayrollItem(InstitutionScopedModel):
    entry = models.ForeignKey(PayrollEntry, on_delete=models.CASCADE, related_name="items", verbose_name="contracheque")
    rubric = models.ForeignKey(Rubric, on_delete=models.PROTECT, related_name="+", verbose_name="rubrica (versão)")
    code = models.CharField("código", max_length=6)
    name = models.CharField("descrição", max_length=120)
    kind = models.CharField("tipo", max_length=12, choices=RubricKind.choices)
    reference = models.CharField("referência", max_length=30, blank=True)
    amount = models.DecimalField("valor", max_digits=15, decimal_places=2)
    source_entry = models.ForeignKey(Entry, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                     verbose_name="lançamento de origem")

    class Meta:
        db_table = "payroll_items"
        verbose_name = "item da folha"
        ordering = ["kind", "code"]
