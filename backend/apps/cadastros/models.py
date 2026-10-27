"""
Cadastros básicos (tabelas de referência) usados pelo Cadastro Único, pelos
vínculos funcionais e pelo Protocolo.

Os códigos seguem os leiautes oficiais para que nenhum dado precise ser
convertido depois:
- Poder / tipo de poder / tipo de cargo: leiaute SPREV da avaliação atuarial
  (CO_PODER, CO_TIPO_PODER, CO_TIPO_CARGO);
- Código do órgão no SIGFIS: Deliberação TCE-RJ nº 260/2013 (4 dígitos).
Nada é excluído: registros referenciados são inativados.
"""
from django.db import models

from apps.core.models import InstitutionScopedModel
from apps.core.validators import validate_cnpj
from apps.institutions.models import UF_CHOICES


class EnteKind(models.TextChoices):
    MUNICIPIO = "MUNICIPIO", "Município"
    ESTADO = "ESTADO", "Estado"
    DISTRITO_FEDERAL = "DF", "Distrito Federal"
    UNIAO = "UNIAO", "União"


class Ente(InstitutionScopedModel):
    """Ente federativo ao qual os órgãos e servidores estão vinculados."""

    name = models.CharField("nome", max_length=150)
    kind = models.CharField("tipo", max_length=10, choices=EnteKind.choices, default=EnteKind.MUNICIPIO)
    cnpj = models.CharField("CNPJ", max_length=14, blank=True, validators=[validate_cnpj])
    ibge_code = models.CharField("código IBGE", max_length=7, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UF_CHOICES, blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "entes"
        verbose_name = "ente"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["institution", "name"], name="uq_ente_name")]

    def __str__(self):
        return self.name


class Poder(models.IntegerChoices):  # CO_PODER (SPREV)
    EXECUTIVO = 1, "Executivo"
    LEGISLATIVO = 2, "Legislativo"
    JUDICIARIO = 3, "Judiciário"
    MINISTERIO_PUBLICO = 4, "Ministério Público"
    TRIBUNAL_CONTAS = 5, "Tribunal de Contas"
    DEFENSORIA = 6, "Defensoria Pública"


class TipoPoder(models.IntegerChoices):  # CO_TIPO_PODER (SPREV)
    DIRETA = 1, "Administração Direta"
    INDIRETA = 2, "Administração Indireta"


class Organ(InstitutionScopedModel):
    """Órgão ou entidade (Prefeitura, Câmara, autarquias, fundações)."""

    ente = models.ForeignKey(Ente, on_delete=models.PROTECT, related_name="organs", verbose_name="ente")
    name = models.CharField("nome", max_length=150)
    short_name = models.CharField("sigla", max_length=30, blank=True)
    cnpj = models.CharField("CNPJ", max_length=14, blank=True, validators=[validate_cnpj])
    poder = models.PositiveSmallIntegerField("poder", choices=Poder.choices, default=Poder.EXECUTIVO)
    tipo_poder = models.PositiveSmallIntegerField("administração", choices=TipoPoder.choices, default=TipoPoder.DIRETA)
    sigfis_code = models.CharField(
        "código SIGFIS (TCE-RJ)", max_length=4, blank=True,
        help_text="Código do órgão jurisdicionado no SIGFIS — usado na Deliberação 260.",
    )
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "organs"
        verbose_name = "órgão"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["institution", "name"], name="uq_organ_name")]

    def __str__(self):
        return self.short_name or self.name


class TipoCargo(models.IntegerChoices):  # CO_TIPO_CARGO (SPREV)
    MAGISTRADO = 1, "Magistrados, membros do MP ou de Tribunal de Contas"
    PROFESSOR_BASICO = 2, "Professor da educação infantil e do ensino fundamental e médio"
    PROFESSOR_SUPERIOR = 3, "Professor do ensino superior"
    POLICIAL_CIVIL = 4, "Policial civil"
    AGENTE_PENITENCIARIO = 5, "Agente penitenciário"
    GUARDA_MUNICIPAL = 6, "Guarda municipal"
    DEMAIS = 7, "Demais servidores"
    MILITAR = 8, "Militar"


class Position(InstitutionScopedModel):
    """Cargo efetivo (ou emprego/função) e a carreira a que pertence."""

    name = models.CharField("cargo", max_length=150)
    career = models.CharField("carreira", max_length=150, blank=True)
    cargo_type = models.PositiveSmallIntegerField("tipo de cargo", choices=TipoCargo.choices, default=TipoCargo.DEMAIS)
    cbo = models.CharField("CBO", max_length=6, blank=True)
    education = models.CharField("escolaridade exigida", max_length=60, blank=True)
    weekly_hours = models.PositiveSmallIntegerField("carga horária semanal", null=True, blank=True)
    legal_basis = models.CharField("lei de criação", max_length=255, blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "positions"
        verbose_name = "cargo"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["institution", "name"], name="uq_position_name")]

    def __str__(self):
        return self.name


class Workplace(InstitutionScopedModel):
    """Lotação: setor, secretaria ou unidade onde o servidor trabalha."""

    organ = models.ForeignKey(Organ, on_delete=models.PROTECT, related_name="workplaces", verbose_name="órgão")
    name = models.CharField("nome", max_length=150)
    code = models.CharField("código", max_length=20, blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "workplaces"
        verbose_name = "lotação"
        verbose_name_plural = "lotações"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["institution", "organ", "name"], name="uq_workplace_name")]

    def __str__(self):
        return self.name


class Bank(InstitutionScopedModel):
    code = models.CharField("código", max_length=3)
    name = models.CharField("nome", max_length=120)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "banks"
        verbose_name = "banco"
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["institution", "code"], name="uq_bank_code")]

    def __str__(self):
        return f"{self.code} - {self.name}"


class BankBranch(InstitutionScopedModel):
    bank = models.ForeignKey(Bank, on_delete=models.PROTECT, related_name="branches", verbose_name="banco")
    number = models.CharField("agência", max_length=5)
    digit = models.CharField("dígito", max_length=1, blank=True)
    name = models.CharField("nome", max_length=120, blank=True)
    city = models.CharField("cidade", max_length=120, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UF_CHOICES, blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "bank_branches"
        verbose_name = "agência"
        ordering = ["bank__code", "number"]
        constraints = [models.UniqueConstraint(fields=["institution", "bank", "number"], name="uq_branch_number")]

    def __str__(self):
        return f"{self.number}{'-' + self.digit if self.digit else ''} {self.name}".strip()


# Códigos COMPE públicos dos principais bancos (carga inicial; o usuário pode incluir outros)
DEFAULT_BANKS = [
    ("001", "Banco do Brasil"), ("004", "Banco do Nordeste"), ("021", "Banestes"), ("033", "Santander"),
    ("037", "Banpará"), ("041", "Banrisul"), ("070", "BRB"), ("077", "Banco Inter"), ("104", "Caixa Econômica Federal"),
    ("208", "BTG Pactual"), ("237", "Bradesco"), ("260", "Nu Pagamentos (Nubank)"), ("336", "C6 Bank"),
    ("341", "Itaú Unibanco"), ("422", "Safra"), ("748", "Sicredi"), ("756", "Sicoob"),
]
