"""
COMPREV — controle da compensação previdenciária entre regimes (Lei 9.796/1999; Decreto 10.188/2019).

O requerimento, a análise e o pagamento acontecem no sistema COMPREV do governo federal. O SIST só CONTROLA: guarda
os requerimentos (nos dois sentidos), a situação de cada um, o valor mensal deferido (com vigência — nada é
sobrescrito) e os valores efetivamente recebidos/pagos por competência, para conferir o que o COMPREV creditou ou
debitou e levar a receita ao Financeiro.

Sentidos:
- A RECEBER: o órgão é o regime INSTITUIDOR (paga o benefício) e cobra do regime de ORIGEM (INSS ou outro RPPS) a
  parte do tempo que foi contribuída lá.
- A PAGAR: o órgão é o regime de ORIGEM (o servidor contribuiu aqui e se aposentou em outro regime) e paga ao
  regime instituidor.
"""
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel


class Direction(models.TextChoices):
    RECEBER = "RECEBER", "A receber (somos o regime instituidor)"
    PAGAR = "PAGAR", "A pagar (somos o regime de origem)"


class Counterpart(models.TextChoices):
    RGPS = "RGPS", "RGPS (INSS)"
    RPPS = "RPPS", "Outro RPPS"


class BenefitKind(models.TextChoices):
    APOSENTADORIA = "APOSENTADORIA", "Aposentadoria"
    PENSAO = "PENSAO", "Pensão por morte"


class Status(models.TextChoices):
    CADASTRADO = "CADASTRADO", "Em cadastramento"
    ENVIADO = "ENVIADO", "Enviado / em análise"
    EXIGENCIA = "EXIGENCIA", "Em exigência"
    DEFERIDO = "DEFERIDO", "Deferido (compensando)"
    INDEFERIDO = "INDEFERIDO", "Indeferido"
    CESSADO = "CESSADO", "Compensação cessada"
    CANCELADO = "CANCELADO", "Cancelado"


# Situações em que a compensação gera valores mensais
COMPENSATING = {Status.DEFERIDO, Status.CESSADO}
TRANSITIONS = {
    Status.CADASTRADO: {Status.ENVIADO, Status.CANCELADO},
    Status.ENVIADO: {Status.EXIGENCIA, Status.DEFERIDO, Status.INDEFERIDO, Status.CANCELADO},
    Status.EXIGENCIA: {Status.ENVIADO, Status.INDEFERIDO, Status.CANCELADO},
    Status.INDEFERIDO: {Status.ENVIADO},  # recurso / novo envio
    Status.DEFERIDO: {Status.CESSADO},
    Status.CESSADO: set(),
    Status.CANCELADO: set(),
}
NEEDS_REASON = {Status.INDEFERIDO, Status.CESSADO, Status.CANCELADO}


class ComprevProcess(InstitutionScopedModel):
    direction = models.CharField("sentido", max_length=8, choices=Direction.choices)
    counterpart_kind = models.CharField("outro regime", max_length=4, choices=Counterpart.choices)
    counterpart_name = models.CharField("nome do outro regime", max_length=200)
    counterpart_cnpj = models.CharField("CNPJ do outro regime", max_length=14, blank=True)
    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    benefit_kind = models.CharField("benefício", max_length=14, choices=BenefitKind.choices)
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="comprev_processes",
                               verbose_name="segurado (ou instituidor da pensão)")
    benefit = models.ForeignKey("concessao.Benefit", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                verbose_name="benefício pago por nós")
    averbacao = models.ForeignKey("previdencia.Averbacao", on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="+", verbose_name="averbação do tempo do outro regime")
    ctc = models.ForeignKey("previdencia.Ctc", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                            verbose_name="CTC emitida por nós")
    request_number = models.CharField("nº do requerimento no COMPREV", max_length=40, blank=True)
    requested_at = models.DateField("data do requerimento")
    benefit_start = models.DateField("início do benefício (DIB)", null=True, blank=True)
    rmi = models.DecimalField("renda mensal inicial do benefício", max_digits=15, decimal_places=2, null=True, blank=True)
    origin_days = models.PositiveIntegerField("tempo no regime de origem (dias)", null=True, blank=True)
    total_days = models.PositiveIntegerField("tempo total de contribuição (dias)", null=True, blank=True)
    status = models.CharField("situação", max_length=10, choices=Status.choices, default=Status.CADASTRADO)
    status_date = models.DateField("data da situação", null=True, blank=True)
    comp_start = models.DateField("início da compensação", null=True, blank=True)
    backlog_amount = models.DecimalField("atrasados / estoque deferido", max_digits=15, decimal_places=2, default=0)
    requirement_text = models.TextField("exigência", blank=True)
    requirement_due = models.DateField("prazo da exigência", null=True, blank=True)
    decision_reason = models.TextField("motivo (indeferimento, cessação, cancelamento)", blank=True)
    ended_at = models.DateField("fim da compensação", null=True, blank=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        db_table = "comprev_processes"
        verbose_name = "requerimento COMPREV"
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "direction", "request_number"],
                                    condition=~Q(request_number=""), name="uq_comprev_request_number"),
            models.CheckConstraint(condition=Q(backlog_amount__gte=0), name="ck_comprev_backlog"),
        ]

    def __str__(self):
        return f"COMPREV {self.request_number or 's/nº'} — {self.person}"


class ProcessEvent(InstitutionScopedModel):
    """Trilha da situação do requerimento (não é alterada nem excluída)."""

    process = models.ForeignKey(ComprevProcess, on_delete=models.PROTECT, related_name="events")
    date = models.DateField("data")
    status_from = models.CharField("de", max_length=10, choices=Status.choices, blank=True)
    status_to = models.CharField("para", max_length=10, choices=Status.choices)
    note = models.TextField("observação", blank=True)

    class Meta:
        db_table = "comprev_process_events"
        ordering = ["date", "created_at"]


class MonthlyValue(InstitutionScopedModel):
    """Valor mensal da compensação (pro rata) com vigência. Reajuste = nova vigência; a anterior fica no histórico."""

    process = models.ForeignKey(ComprevProcess, on_delete=models.PROTECT, related_name="values")
    valid_from = models.DateField("a partir da competência")
    amount = models.DecimalField("valor mensal", max_digits=15, decimal_places=2)
    reason = models.CharField("motivo", max_length=200)

    class Meta:
        db_table = "comprev_monthly_values"
        ordering = ["valid_from"]
        constraints = [
            models.UniqueConstraint(fields=["process", "valid_from"], name="uq_comprev_value_from"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="ck_comprev_value_amount"),
        ]


class MovementKind(models.TextChoices):
    MENSAL = "MENSAL", "Fluxo mensal"
    ATRASADOS = "ATRASADOS", "Atrasados / estoque"
    AJUSTE = "AJUSTE", "Ajuste / diferença a maior"
    GLOSA = "GLOSA", "Glosa / devolução (reduz)"


class Movement(InstitutionScopedModel):
    """Valor efetivamente recebido (A RECEBER) ou pago (A PAGAR). Estorno = inativar com motivo."""

    process = models.ForeignKey(ComprevProcess, on_delete=models.PROTECT, related_name="movements")
    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    direction = models.CharField("sentido", max_length=8, choices=Direction.choices)
    kind = models.CharField("tipo", max_length=10, choices=MovementKind.choices, default=MovementKind.MENSAL)
    competence = models.DateField("competência (1º dia do mês)")
    expected = models.DecimalField("valor previsto", max_digits=15, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField("valor", max_digits=15, decimal_places=2)
    date = models.DateField("data do crédito / pagamento")
    document = models.CharField("documento (aviso, OB, extrato)", max_length=60, blank=True)
    revenue = models.ForeignKey("financeiro.Revenue", on_delete=models.PROTECT, null=True, blank=True,
                                related_name="comprev_movements", verbose_name="receita no Financeiro")
    active = models.BooleanField("ativo", default=True)
    reversal_reason = models.TextField("motivo do estorno", blank=True)

    class Meta:
        db_table = "comprev_movements"
        ordering = ["-competence", "process__person__name"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="ck_comprev_movement_amount")]

    @property
    def signed(self):
        return -self.amount if self.kind == MovementKind.GLOSA else self.amount
