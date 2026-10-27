"""
Instituição (RPPS), planos (segregação de massas), exercícios, competências
e parâmetros versionados.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel, InstitutionScopedModel, ValidityModel
from apps.core.validators import validate_cnpj

UF_CHOICES = [(uf, uf) for uf in (
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO"
).split()]

MONTH_NAMES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


class InstitutionKind(models.TextChoices):
    """Tipo de órgão. Define quais módulos ficam disponíveis (ver accounts.catalog)."""

    RPPS = "RPPS", "RPPS (instituto ou fundo de previdência)"
    PREFEITURA = "PREFEITURA", "Prefeitura"
    AUTARQUIA = "AUTARQUIA", "Autarquia"
    FUNDACAO = "FUNDACAO", "Fundação pública"
    CAMARA = "CAMARA", "Câmara Municipal"
    FUNDO = "FUNDO", "Fundo municipal"


class Institution(BaseModel):
    """Órgão usuário do sistema (RPPS, Prefeitura, Autarquia, Fundo). Multi-instituição desde a Fase 1."""

    kind = models.CharField("tipo de órgão", max_length=20, choices=InstitutionKind.choices,
                            default=InstitutionKind.RPPS)
    name = models.CharField("razão social", max_length=255)
    short_name = models.CharField("sigla", max_length=40, unique=True)
    cnpj = models.CharField(
        "CNPJ", max_length=14, blank=True, null=True, unique=True,
        validators=[validate_cnpj], help_text="Somente dígitos.",
    )
    ente_name = models.CharField("ente federativo", max_length=255, blank=True)
    ente_cnpj = models.CharField(
        "CNPJ do ente", max_length=14, blank=True, validators=[validate_cnpj]
    )
    address = models.CharField("endereço", max_length=255, blank=True)
    district = models.CharField("bairro", max_length=120, blank=True)
    city = models.CharField("cidade", max_length=120, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UF_CHOICES, blank=True)
    cep = models.CharField("CEP", max_length=8, blank=True)
    phone = models.CharField("telefone", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    website = models.URLField("site", blank=True)
    ibge_code = models.CharField(
        "código IBGE do ente", max_length=7, blank=True,
        help_text="7 dígitos. Usado na base de dados da avaliação atuarial (CO_IBGE).",
    )
    life_purchase_enabled = models.BooleanField(
        "possui compra de vidas", default=False, editable=False,
        help_text="Alterado somente por services.set_life_purchase (exige justificativa).",
    )
    active = models.BooleanField("ativa", default=True)
    # Identidade visual (brasão do município contratante e imagem de fundo das telas)
    coat_of_arms = models.FileField("brasão", upload_to="identidade/", blank=True)
    coat_of_arms_type = models.CharField("tipo do brasão", max_length=20, blank=True)
    background_image = models.FileField("imagem de fundo", upload_to="identidade/", blank=True)
    background_type = models.CharField("tipo da imagem de fundo", max_length=20, blank=True)
    background_intensity = models.PositiveSmallIntegerField(
        "intensidade da imagem de fundo (%)", default=15,
        help_text="Quanto a imagem aparece atrás das telas (5 a 60%); o restante é coberto pelo fundo claro.")

    class Meta:
        db_table = "institutions"
        verbose_name = "instituição"
        verbose_name_plural = "instituições"
        ordering = ["short_name"]

    def __str__(self):
        return self.short_name


class PlanKind(models.TextChoices):
    FINANCEIRO = "FINANCEIRO", "Plano Financeiro"
    PREVIDENCIARIO = "PREVIDENCIARIO", "Plano Previdenciário"


class BenefitPlan(InstitutionScopedModel):
    """
    Plano de custeio para segregação de massas.

    Toda entidade financeira/previdenciária das próximas fases terá FK
    obrigatória para esta tabela, permitindo filtros TODOS/FINANCEIRO/
    PREVIDENCIÁRIO sem misturar informações.
    """

    code = models.CharField("código", max_length=20)
    name = models.CharField("nome", max_length=120)
    kind = models.CharField("tipo", max_length=20, choices=PlanKind.choices)
    description = models.TextField("descrição", blank=True)
    legal_basis = models.CharField("fundamento legal", max_length=255, blank=True)
    start_date = models.DateField("data de início da segregação", null=True, blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "benefit_plans"
        verbose_name = "plano"
        verbose_name_plural = "planos"
        ordering = ["kind", "code"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "code"], name="uq_plan_institution_code"),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class Segment(models.TextChoices):
    """
    Massa de beneficiários — define a folha em que cada benefício é pago.

    A Compra de Vidas é uma massa do Plano Previdenciário (fundo em
    capitalização), mas tem folha própria: as vidas transferidas do Plano
    Financeiro precisam ser identificadas separadamente para a avaliação
    atuarial, a contabilidade e a prestação de contas.
    """

    FINANCEIRO = "FINANCEIRO", "Plano Financeiro"
    PREVIDENCIARIO = "PREVIDENCIARIO", "Plano Previdenciário — massa própria"
    COMPRA_VIDAS = "COMPRA_VIDAS", "Plano Previdenciário — Compra de Vidas"


SEGMENT_PLAN_KIND = {
    Segment.FINANCEIRO: PlanKind.FINANCEIRO,
    Segment.PREVIDENCIARIO: PlanKind.PREVIDENCIARIO,
    Segment.COMPRA_VIDAS: PlanKind.PREVIDENCIARIO,
}


class PayrollGroup(InstitutionScopedModel):
    """
    Folha de benefícios (uma por massa). As entidades de folha das próximas
    fases (beneficiários, folhas mensais, lançamentos) apontam para cá; o
    plano de custeio é derivado da folha.
    """

    segment = models.CharField("massa", max_length=20, choices=Segment.choices)
    code = models.CharField("código", max_length=20)
    name = models.CharField("nome", max_length=120)
    plan = models.ForeignKey(
        BenefitPlan, on_delete=models.PROTECT, related_name="payroll_groups", verbose_name="plano",
    )
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "payroll_groups"
        verbose_name = "folha"
        verbose_name_plural = "folhas"
        ordering = ["segment"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "segment"], name="uq_payroll_group_segment"),
            models.UniqueConstraint(fields=["institution", "code"], name="uq_payroll_group_code"),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"


class LifePurchase(InstitutionScopedModel):
    """
    Operação (lote) de Compra de Vidas: transferência de segurados e
    beneficiários do Plano Financeiro para o Plano Previdenciário, com
    o respectivo aporte de recursos. Não há exclusão: inativar.

    Na Fase 4/5, cada beneficiário da folha COMPRA_VIDAS terá FK obrigatória
    para o lote que o transferiu.
    """

    number = models.PositiveIntegerField("número do lote")
    cutoff_date = models.DateField("data de corte")
    effective_date = models.DateField("início do pagamento pelo Plano Previdenciário", null=True, blank=True)
    legal_act = models.CharField("ato legal", max_length=255, help_text="Lei, decreto ou portaria que autorizou.")
    legal_act_date = models.DateField("data do ato legal", null=True, blank=True)
    actuarial_study = models.CharField(
        "estudo atuarial", max_length=255, blank=True,
        help_text="Identificação do estudo/parecer atuarial que fundamentou a operação.",
    )
    transferred_amount = models.DecimalField(
        "valor transferido (R$)", max_digits=15, decimal_places=2, null=True, blank=True,
    )
    lives_count = models.PositiveIntegerField("quantidade de vidas informada", null=True, blank=True)
    origin_plan = models.ForeignKey(
        BenefitPlan, on_delete=models.PROTECT, related_name="+", verbose_name="plano de origem",
    )
    destination_plan = models.ForeignKey(
        BenefitPlan, on_delete=models.PROTECT, related_name="+", verbose_name="plano de destino",
    )
    notes = models.TextField("observações", blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "life_purchases"
        verbose_name = "lote de compra de vidas"
        verbose_name_plural = "lotes de compra de vidas"
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "number"], name="uq_life_purchase_number"),
            models.CheckConstraint(
                condition=Q(transferred_amount__isnull=True) | Q(transferred_amount__gte=0),
                name="ck_life_purchase_amount",
            ),
        ]

    def __str__(self):
        return f"Lote {self.number} - corte {self.cutoff_date:%d/%m/%Y}"


class FiscalYearStatus(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    FECHADO = "FECHADO", "Fechado"


class FiscalYear(InstitutionScopedModel):
    year = models.PositiveSmallIntegerField("exercício")
    status = models.CharField(
        "situação", max_length=10, choices=FiscalYearStatus.choices,
        default=FiscalYearStatus.ABERTO,
    )
    closed_at = models.DateTimeField("fechado em", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", verbose_name="fechado por",
    )
    notes = models.TextField("observações", blank=True)

    class Meta:
        db_table = "fiscal_years"
        verbose_name = "exercício"
        verbose_name_plural = "exercícios"
        ordering = ["-year"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "year"], name="uq_fiscal_year"),
            models.CheckConstraint(condition=Q(year__gte=1990) & Q(year__lte=2100), name="ck_fiscal_year_range"),
        ]

    def __str__(self):
        return str(self.year)


class CompetenceStatus(models.TextChoices):
    ABERTA = "ABERTA", "Aberta"
    FECHADA = "FECHADA", "Fechada"


class Competence(InstitutionScopedModel):
    """
    Competência (mês de referência) da instituição.

    A folha de benefícios (Fase 5) terá seu próprio ciclo de status
    (ABERTA → EM CÁLCULO → ... → PAGA) apontando para esta competência.
    """

    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.PROTECT, related_name="competences",
        verbose_name="exercício",
    )
    year = models.PositiveSmallIntegerField("ano")
    month = models.PositiveSmallIntegerField("mês")
    status = models.CharField(
        "situação", max_length=10, choices=CompetenceStatus.choices,
        default=CompetenceStatus.ABERTA,
    )
    is_reference = models.BooleanField("competência de referência", default=False)
    closed_at = models.DateTimeField("fechada em", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+", verbose_name="fechada por",
    )

    class Meta:
        db_table = "competences"
        verbose_name = "competência"
        verbose_name_plural = "competências"
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "year", "month"], name="uq_competence"),
            models.UniqueConstraint(
                fields=["institution"], condition=Q(is_reference=True),
                name="uq_competence_single_reference",
            ),
            models.CheckConstraint(condition=Q(month__gte=1) & Q(month__lte=12), name="ck_competence_month"),
        ]

    def __str__(self):
        return f"{self.month:02d}/{self.year}"

    @property
    def label(self) -> str:
        return f"{MONTH_NAMES[self.month - 1]}/{self.year}"


class Parameter(InstitutionScopedModel, ValidityModel):
    """
    Parâmetro institucional versionado.

    Nunca é sobrescrito: uma alteração cria nova versão e encerra a vigência
    da anterior (ver services.set_parameter). Isso permite reproduzir
    cálculos antigos com o valor vigente na época.
    """

    key = models.CharField("chave", max_length=100)
    value = models.JSONField("valor")
    description = models.CharField("descrição", max_length=255, blank=True)
    version = models.PositiveIntegerField("versão", default=1)
    change_reason = models.TextField("motivo da alteração", blank=True)

    class Meta:
        db_table = "parameters"
        verbose_name = "parâmetro"
        verbose_name_plural = "parâmetros"
        ordering = ["key", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "key", "version"], name="uq_parameter_version"),
        ]
        indexes = [models.Index(fields=["institution", "key", "valid_from"])]

    def __str__(self):
        return f"{self.key} v{self.version}"
