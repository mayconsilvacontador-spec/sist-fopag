"""
Gestão previdenciária (Fase 3): averbações, histórico contributivo, índices de
correção, regras de aposentadoria versionadas e Certidão de Tempo de
Contribuição (CTC).

O tempo de contribuição é APURADO (não digitado): vínculos estatutários do
Cadastro + averbações − afastamentos que não contam (histórico funcional).
As naturezas de tempo seguem a Deliberação TCE-RJ 260 (01 a 05).
"""
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel


class TimeNature(models.TextChoices):  # Deliberação 260 — tipo do tempo de serviço
    INSS_PRIVADO = "01", "INSS — iniciativa privada"
    INSS_PUBLICO = "02", "INSS — órgão público"
    RPPS_OUTRO = "03", "RPPS de outro órgão público"
    FORCAS_ARMADAS = "04", "Forças Armadas"
    RPPS_ORIGEM = "05", "RPPS do órgão de origem"


PUBLIC_SERVICE_NATURES = {TimeNature.INSS_PUBLICO, TimeNature.RPPS_OUTRO, TimeNature.FORCAS_ARMADAS,
                          TimeNature.RPPS_ORIGEM}


class Averbacao(InstitutionScopedModel):
    """Tempo de contribuição de outro regime/órgão, certificado por CTC/CTPS, averbado para o segurado."""

    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="averbacoes",
                               verbose_name="segurado")
    nature = models.CharField("natureza do tempo", max_length=2, choices=TimeNature.choices)
    issuer = models.CharField("órgão / empresa emissora", max_length=150)
    issuer_cnpj = models.CharField("CNPJ do emissor", max_length=14, blank=True)
    certificate_number = models.CharField("nº da certidão (CTC / CNIS)", max_length=40, blank=True)
    certificate_date = models.DateField("data da certidão", null=True, blank=True)
    start_date = models.DateField("início")
    end_date = models.DateField("fim")
    certified_days = models.PositiveIntegerField(
        "dias certificados (líquidos)", help_text="Total líquido constante da certidão (já descontadas faltas).")
    magisterio = models.BooleanField("exercício de magistério", default=False)
    special_activity = models.BooleanField("atividade especial (insalubre)", default=False)
    conversion_extra_days = models.PositiveIntegerField(
        "acréscimo por conversão de tempo especial", default=0,
        help_text="Somente para períodos até 12/11/2019 (vedada a conversão após a EC 103).")
    act_number = models.CharField("ato de averbação", max_length=40, blank=True)
    act_date = models.DateField("data do ato", null=True, blank=True)
    comprev = models.BooleanField("sujeito à compensação previdenciária (COMPREV)", default=True)
    notes = models.TextField("observações", blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "averbacoes"
        verbose_name = "averbação"
        verbose_name_plural = "averbações"
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=models.F("start_date")), name="ck_averbacao_dates"),
        ]

    @property
    def is_public_service(self) -> bool:
        return self.nature in PUBLIC_SERVICE_NATURES


class ContributionRegime(models.TextChoices):
    RPPS = "RPPS", "RPPS"
    RGPS = "RGPS", "RGPS (INSS)"


class ContributionSalary(InstitutionScopedModel):
    """Salário de contribuição mensal (base para média — Lei 10.887/2004 e EC 103 art. 26). Desde 07/1994."""

    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="contribution_salaries",
                               verbose_name="segurado")
    competence = models.DateField("competência (1º dia do mês)")
    regime = models.CharField("regime", max_length=4, choices=ContributionRegime.choices,
                              default=ContributionRegime.RPPS)
    source_label = models.CharField("vínculo / empregador", max_length=150, blank=True)
    amount = models.DecimalField("salário de contribuição (R$)", max_digits=15, decimal_places=2)
    origin = models.CharField("origem do dado", max_length=20, default="MANUAL",
                              help_text="MANUAL, IMPORTACAO, FOLHA (Fase 5).")

    class Meta:
        db_table = "contribution_salaries"
        verbose_name = "salário de contribuição"
        ordering = ["competence"]
        constraints = [
            models.UniqueConstraint(fields=["person", "competence", "regime", "source_label"],
                                    name="uq_contribution_salary"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="ck_contribution_amount"),
        ]


class CorrectionFactor(InstitutionScopedModel):
    """
    Fator de atualização monetária dos salários de contribuição (tabela mensal
    publicada pelo Ministério da Previdência). table_month = mês da tabela
    (mês do cálculo); competence = competência do salário a atualizar.
    """

    table_month = models.DateField("mês da tabela")
    competence = models.DateField("competência")
    factor = models.DecimalField("fator", max_digits=14, decimal_places=8)

    class Meta:
        db_table = "correction_factors"
        verbose_name = "fator de correção"
        ordering = ["-table_month", "competence"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "table_month", "competence"], name="uq_correction_factor"),
        ]


class RetirementRule(InstitutionScopedModel):
    """
    Regra de aposentadoria versionada. `engine` identifica a lógica no código
    (apps/previdencia/rules.py) e `params` guarda os números (idades, tempos,
    pontuações). Uma regra só pode ser usada se os requisitos forem cumpridos
    dentro da sua vigência (valid_from..valid_to) e se o servidor atender à data
    de ingresso exigida.
    """

    code = models.CharField("código", max_length=40)
    name = models.CharField("nome", max_length=150)
    legal_basis = models.CharField("fundamentação", max_length=255)
    engine = models.CharField("motor de cálculo", max_length=40)
    group = models.CharField("grupo", max_length=30, help_text="PERMANENTE, TRANSICAO, DIREITO_ADQUIRIDO, COMPULSORIA")
    for_teacher = models.BooleanField("regra de professor", default=False)
    params = models.JSONField("parâmetros")
    valid_from = models.DateField("requisitos a partir de", null=True, blank=True)
    valid_to = models.DateField("requisitos até", null=True, blank=True,
                                help_text="Último dia para cumprir os requisitos (direito adquirido).")
    proventos = models.CharField("forma de cálculo dos proventos", max_length=255)
    paridade = models.CharField("paridade", max_length=150, blank=True)
    gives_permanence_bonus = models.BooleanField("dá direito a abono de permanência", default=True)
    notes = models.TextField("observações", blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "retirement_rules"
        verbose_name = "regra de aposentadoria"
        ordering = ["group", "code"]
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="uq_retirement_rule_code")]

    def __str__(self):
        return self.name


class CtcStatus(models.TextChoices):
    EMITIDA = "EMITIDA", "Emitida"
    CANCELADA = "CANCELADA", "Cancelada"


class Ctc(InstitutionScopedModel):
    """
    Certidão de Tempo de Contribuição. O conteúdo é congelado no momento da
    emissão (snapshot) — alterações posteriores no cadastro não mudam a certidão.
    Não há exclusão: cancelamento com justificativa.
    """

    number = models.PositiveIntegerField("número")
    year = models.PositiveSmallIntegerField("ano")
    person = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="ctcs", verbose_name="segurado")
    destination = models.CharField("órgão / regime de destino", max_length=200)
    purpose = models.CharField("finalidade", max_length=200, default="Averbação / contagem recíproca")
    period_start = models.DateField("período certificado — início")
    period_end = models.DateField("período certificado — fim")
    snapshot = models.JSONField("conteúdo da certidão")
    sha256 = models.CharField("hash do conteúdo", max_length=64)
    process = models.ForeignKey("protocolo.Process", on_delete=models.PROTECT, null=True, blank=True,
                                related_name="+", verbose_name="processo")
    status = models.CharField("situação", max_length=10, choices=CtcStatus.choices, default=CtcStatus.EMITIDA)
    cancel_reason = models.TextField("motivo do cancelamento", blank=True)

    class Meta:
        db_table = "ctcs"
        verbose_name = "CTC"
        ordering = ["-year", "-number"]
        constraints = [models.UniqueConstraint(fields=["institution", "year", "number"], name="uq_ctc_number")]

    @property
    def code(self) -> str:
        return f"{self.number:04d}/{self.year}"
