"""
Vínculos funcionais e histórico funcional.

Um vínculo liga uma pessoa do Cadastro Único a um órgão/cargo/matrícula.
Os campos atendem diretamente:
- leiaute SPREV (DT_ING_SERV_PUB, DT_ING_ENTE, DT_ING_CARREIRA, DT_ING_CARGO,
  CO_TIPO_VINCULO, CO_SITUACAO_FUNCIONAL, CO_CRITERIO_ELEGIBILIDADE, abono,
  previdência complementar) e a massa (CO_TIPO_FUNDO);
- Deliberação TCE-RJ 260 (forma de admissão, cargo inicial, afastamentos com
  indicação de contribuição).
"""
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel
from apps.institutions.models import Segment


class LinkType(models.IntegerChoices):  # CO_TIPO_VINCULO (SPREV)
    EFETIVO = 1, "Servidor efetivo"
    EFETIVO_COMISSAO = 2, "Efetivo ocupante de cargo em comissão"
    ESTAVEL = 3, "Estável (art. 19 ADCT)"
    OUTROS = 4, "Outros"


class Regime(models.TextChoices):
    ESTATUTARIO = "ESTATUTARIO", "Estatutário (RPPS)"
    CELETISTA = "CELETISTA", "Celetista (RGPS)"


class AdmissionForm(models.IntegerChoices):  # Deliberação TCE-RJ 260
    CONTRATO_TEMPORARIO = 1, "Contrato temporário"
    CONTRATO_INDETERMINADO = 2, "Contrato por prazo indeterminado"
    CONCURSO = 3, "Concurso público"
    NOMEACAO_DIRETA = 4, "Nomeação direta"


class Eligibility(models.IntegerChoices):  # CO_CRITERIO_ELEGIBILIDADE (SPREV)
    SEM_CRITERIO = 1, "Sem critério diferenciado"
    DEFICIENCIA = 2, "Com deficiência (art. 40, § 4º, I, CF)"
    PROFESSOR = 3, "Professor"
    ATIVIDADE_RISCO = 4, "Atividade de risco (art. 40, § 4º, II, CF)"
    INSALUBRE = 5, "Atividade prejudicial à saúde (art. 40, § 4º, III, CF)"


class FunctionalSituation(models.IntegerChoices):  # CO_SITUACAO_FUNCIONAL (SPREV)
    EM_EXERCICIO = 1, "Em exercício"
    LICENCIADO_COM = 2, "Licenciado(a) com remuneração"
    LICENCIADO_SEM = 3, "Licenciado(a) sem remuneração"
    CEDIDO_COM = 4, "Cedido(a) com ônus"
    CEDIDO_SEM = 5, "Cedido(a) sem ônus"
    REQUISITADO_COM = 6, "Requisitado(a) com ônus"
    REQUISITADO_SEM = 7, "Requisitado(a) sem ônus"
    DISPONIBILIDADE = 8, "Em disponibilidade"
    MANDATO_ELETIVO = 9, "Afastado(a) para mandato eletivo"
    RECLUSO = 10, "Recluso(a) ou detido(a)"
    OUTROS = 11, "Outros"


class LinkStatus(models.TextChoices):
    ATIVO = "ATIVO", "Ativo"
    APOSENTADO = "APOSENTADO", "Aposentado"
    EXONERADO = "EXONERADO", "Exonerado / demitido"
    FALECIDO = "FALECIDO", "Falecido"
    ENCERRADO = "ENCERRADO", "Encerrado (outros motivos)"


# Situações em que o vínculo ainda é de servidor ativo
ACTIVE_STATUSES = [LinkStatus.ATIVO]


class EmploymentLink(InstitutionScopedModel):
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="employment_links",
                               verbose_name="pessoa")
    organ = models.ForeignKey("cadastros.Organ", on_delete=models.PROTECT, related_name="+", verbose_name="órgão")
    position = models.ForeignKey("cadastros.Position", on_delete=models.PROTECT, related_name="+",
                                 verbose_name="cargo atual")
    initial_position = models.ForeignKey(
        "cadastros.Position", on_delete=models.PROTECT, related_name="+", null=True, blank=True,
        verbose_name="cargo inicial", help_text="Cargo de ingresso, se diferente do atual (Deliberação 260).",
    )
    workplace = models.ForeignKey("cadastros.Workplace", on_delete=models.PROTECT, related_name="+", null=True,
                                  blank=True, verbose_name="lotação")
    registration = models.CharField("matrícula", max_length=20)
    link_type = models.PositiveSmallIntegerField("tipo de vínculo", choices=LinkType.choices, default=LinkType.EFETIVO)
    regime = models.CharField("regime", max_length=12, choices=Regime.choices, default=Regime.ESTATUTARIO)
    admission_form = models.PositiveSmallIntegerField("forma de admissão", choices=AdmissionForm.choices,
                                                      default=AdmissionForm.CONCURSO)
    public_service_start = models.DateField("ingresso no serviço público")
    ente_start = models.DateField("ingresso no ente")
    career_start = models.DateField("ingresso na carreira", null=True, blank=True)
    position_start = models.DateField("início no cargo atual")
    statutory_since = models.DateField("estatutário desde", null=True, blank=True)
    class_level = models.CharField("classe / nível / referência", max_length=50, blank=True)
    base_salary = models.DecimalField("vencimento base (R$)", max_digits=15, decimal_places=2, null=True, blank=True)
    weekly_hours = models.PositiveSmallIntegerField("carga horária semanal (horas)", null=True, blank=True)
    eligibility = models.PositiveSmallIntegerField("critério de elegibilidade", choices=Eligibility.choices,
                                                   default=Eligibility.SEM_CRITERIO)
    situation = models.PositiveSmallIntegerField("situação funcional", choices=FunctionalSituation.choices,
                                                 default=FunctionalSituation.EM_EXERCICIO)
    segment = models.CharField("massa (fundo)", max_length=20, choices=Segment.choices, default=Segment.PREVIDENCIARIO)
    life_purchase = models.ForeignKey("institutions.LifePurchase", on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="+", verbose_name="lote de compra de vidas")
    permanence_bonus_since = models.DateField("abono de permanência desde", null=True, blank=True)
    complementary_pension = models.BooleanField("sujeito à previdência complementar", default=False)
    status = models.CharField("status", max_length=12, choices=LinkStatus.choices, default=LinkStatus.ATIVO)
    end_date = models.DateField("data de encerramento", null=True, blank=True)
    end_reason = models.CharField("motivo do encerramento", max_length=255, blank=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        db_table = "employment_links"
        verbose_name = "vínculo"
        ordering = ["-position_start"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "organ", "registration"], name="uq_link_registration"),
            models.CheckConstraint(
                condition=Q(status="ATIVO", end_date__isnull=True) | (~Q(status="ATIVO") & Q(end_date__isnull=False)),
                name="ck_link_status_end_date",
            ),
            models.CheckConstraint(
                condition=~Q(segment="COMPRA_VIDAS") | Q(life_purchase__isnull=False),
                name="ck_link_life_purchase_lot",
            ),
        ]

    def __str__(self):
        return f"{self.registration} - {self.person}"


class EventType(models.TextChoices):
    NOMEACAO = "NOMEACAO", "Nomeação / admissão"
    POSSE = "POSSE", "Posse / exercício"
    PROGRESSAO = "PROGRESSAO", "Progressão / promoção"
    ENQUADRAMENTO = "ENQUADRAMENTO", "Enquadramento / transformação de cargo"
    LOTACAO = "LOTACAO", "Mudança de lotação"
    LICENCA = "LICENCA", "Licença"
    AFASTAMENTO = "AFASTAMENTO", "Afastamento"
    FALTAS = "FALTAS", "Faltas não abonadas"
    SUSPENSAO = "SUSPENSAO", "Suspensão"
    DISPONIBILIDADE = "DISPONIBILIDADE", "Disponibilidade"
    CESSAO = "CESSAO", "Cessão / requisição"
    RETORNO = "RETORNO", "Retorno ao exercício"
    ABONO = "ABONO", "Concessão de abono de permanência"
    GRATIFICACAO = "GRATIFICACAO", "Gratificação / vantagem"
    APOSENTADORIA = "APOSENTADORIA", "Aposentadoria"
    EXONERACAO = "EXONERACAO", "Exoneração / demissão"
    FALECIMENTO = "FALECIMENTO", "Falecimento"
    OUTROS = "OUTROS", "Outros"


# Eventos que afastam o servidor e podem não contar como tempo de contribuição (Deliberação 260)
ABSENCE_EVENTS = {EventType.LICENCA, EventType.AFASTAMENTO, EventType.FALTAS, EventType.SUSPENSAO,
                  EventType.DISPONIBILIDADE}


class FunctionalEvent(InstitutionScopedModel):
    """Histórico funcional: cada fato da vida funcional, com o ato que o formalizou. Nunca sobrescrito."""

    link = models.ForeignKey(EmploymentLink, on_delete=models.PROTECT, related_name="events", verbose_name="vínculo")
    event_type = models.CharField("tipo", max_length=20, choices=EventType.choices)
    start_date = models.DateField("início")
    end_date = models.DateField("fim", null=True, blank=True)
    days = models.PositiveIntegerField("dias", null=True, blank=True,
                                       help_text="Para faltas: total de dias no período.")
    with_pay = models.BooleanField("com remuneração", default=True)
    contributed = models.BooleanField("houve contribuição previdenciária", default=True)
    counts_as_service = models.BooleanField("conta como tempo de contribuição", default=True)
    act_type = models.CharField("natureza do ato", max_length=30, blank=True, help_text="Portaria, decreto...")
    act_number = models.CharField("número do ato", max_length=30, blank=True)
    act_date = models.DateField("data do ato", null=True, blank=True)
    publication = models.CharField("publicação", max_length=120, blank=True)
    description = models.TextField("descrição")

    class Meta:
        db_table = "functional_events"
        verbose_name = "evento funcional"
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                                   name="ck_event_dates"),
        ]

    def __str__(self):
        return f"{self.get_event_type_display()} em {self.start_date:%d/%m/%Y}"
