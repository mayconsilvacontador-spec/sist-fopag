"""
Cadastro Único: cada pessoa (servidor, aposentado, pensionista, dependente)
é cadastrada UMA vez por instituição, identificada pelo CPF. Vínculos,
benefícios, dependências e processos apenas referenciam a pessoa.

Endereços e contas bancárias têm vigência: um novo registro encerra o
anterior — o histórico nunca é sobrescrito. Documentos são versionados e
guardados com hash SHA-256.

Códigos (sexo, estado civil, dependência, condição) seguem o leiaute SPREV.
"""
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel, ValidityModel
from apps.core.validators import validate_cpf
from apps.institutions.models import UF_CHOICES


class Sex(models.IntegerChoices):  # CO_SEXO (SPREV)
    FEMININO = 1, "Feminino"
    MASCULINO = 2, "Masculino"


class MaritalStatus(models.IntegerChoices):  # CO_EST_CIVIL (SPREV)
    SOLTEIRO = 1, "Solteiro(a)"
    CASADO = 2, "Casado(a)"
    VIUVO = 3, "Viúvo(a)"
    SEPARADO = 4, "Separado(a) judicialmente"
    DIVORCIADO = 5, "Divorciado(a)"
    UNIAO_ESTAVEL = 6, "União estável"
    OUTROS = 9, "Outros"


class Person(InstitutionScopedModel):
    cpf = models.CharField("CPF", max_length=11, validators=[validate_cpf])
    # Pode ficar vazio só em registros importados da base SPREV (o leiaute não traz o nome);
    # o cadastro manual exige o nome e a consulta à Receita completa os pendentes.
    name = models.CharField("nome", max_length=150, blank=True)
    social_name = models.CharField("nome social", max_length=150, blank=True)
    birth_date = models.DateField("data de nascimento")
    sex = models.PositiveSmallIntegerField("sexo", choices=Sex.choices)
    marital_status = models.PositiveSmallIntegerField("estado civil", choices=MaritalStatus.choices, null=True, blank=True)
    mother_name = models.CharField("nome da mãe", max_length=150, blank=True)
    father_name = models.CharField("nome do pai", max_length=150, blank=True)
    nationality = models.CharField("nacionalidade", max_length=60, default="Brasileira")
    birthplace_city = models.CharField("naturalidade (cidade)", max_length=120, blank=True)
    birthplace_uf = models.CharField("naturalidade (UF)", max_length=2, choices=UF_CHOICES, blank=True)
    rg_number = models.CharField("RG", max_length=20, blank=True)
    rg_issuer = models.CharField("órgão expedidor", max_length=20, blank=True)
    rg_uf = models.CharField("UF do RG", max_length=2, choices=UF_CHOICES, blank=True)
    rg_date = models.DateField("data de expedição", null=True, blank=True)
    pis_pasep = models.CharField("PIS/PASEP/NIT", max_length=11, blank=True)
    voter_id = models.CharField("título de eleitor", max_length=12, blank=True)
    education = models.CharField("escolaridade", max_length=60, blank=True)
    phone = models.CharField("telefone", max_length=20, blank=True)
    mobile = models.CharField("celular", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    race = models.PositiveSmallIntegerField(  # racaCor (eSocial)
        "raça/cor", null=True, blank=True,
        choices=[(1, "Branca"), (2, "Preta"), (3, "Parda"), (4, "Amarela"), (5, "Indígena"), (6, "Não informado")])
    has_disability = models.BooleanField("pessoa com deficiência", default=False)
    disability_type = models.CharField("tipo de deficiência", max_length=120, blank=True)
    is_invalid = models.BooleanField("inválido(a)", default=False,
                                     help_text="Condição de invalidez reconhecida (CO_CONDICAO = 2).")
    invalidity_date = models.DateField("data da invalidez", null=True, blank=True)
    death_date = models.DateField("data do óbito", null=True, blank=True)
    death_certificate = models.CharField("certidão de óbito", max_length=60, blank=True)
    notes = models.TextField("observações", blank=True)
    photo = models.FileField("foto", upload_to="fotos/%Y/", blank=True)
    photo_type = models.CharField("tipo da foto", max_length=20, blank=True)

    class Meta:
        db_table = "people"
        verbose_name = "pessoa"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["institution", "cpf"], name="uq_person_cpf"),
            models.CheckConstraint(condition=Q(death_date__isnull=True) | Q(death_date__gte=models.F("birth_date")),
                                   name="ck_person_death_after_birth"),
        ]
        indexes = [models.Index(fields=["institution", "name"])]

    def __str__(self):
        return self.name


class Address(InstitutionScopedModel, ValidityModel):
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="addresses", verbose_name="pessoa")
    cep = models.CharField("CEP", max_length=8, blank=True)
    street = models.CharField("logradouro", max_length=150)
    number = models.CharField("número", max_length=10, blank=True)
    complement = models.CharField("complemento", max_length=60, blank=True)
    district = models.CharField("bairro", max_length=80, blank=True)
    city = models.CharField("cidade", max_length=120)
    city_ibge = models.CharField("código IBGE do município", max_length=7, blank=True)
    uf = models.CharField("UF", max_length=2, choices=UF_CHOICES, blank=True)
    country = models.CharField("país", max_length=60, default="Brasil")

    class Meta:
        db_table = "addresses"
        verbose_name = "endereço"
        ordering = ["-valid_from"]


class AccountType(models.TextChoices):
    CORRENTE = "CORRENTE", "Conta corrente"
    POUPANCA = "POUPANCA", "Conta poupança"
    SALARIO = "SALARIO", "Conta salário"


class BankAccount(InstitutionScopedModel, ValidityModel):
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="bank_accounts", verbose_name="pessoa")
    bank = models.ForeignKey("cadastros.Bank", on_delete=models.PROTECT, related_name="+", verbose_name="banco")
    branch = models.CharField("agência", max_length=5)
    branch_digit = models.CharField("dígito da agência", max_length=1, blank=True)
    account = models.CharField("conta", max_length=15)
    account_digit = models.CharField("dígito da conta", max_length=2, blank=True)
    account_type = models.CharField("tipo", max_length=10, choices=AccountType.choices, default=AccountType.CORRENTE)

    class Meta:
        db_table = "bank_accounts"
        verbose_name = "conta bancária"
        ordering = ["-valid_from"]


class DependencyType(models.IntegerChoices):  # CO_TIPO_DEPENDECIA (SPREV)
    CONJUGE = 1, "Cônjuge"
    COMPANHEIRO = 2, "Companheiro(a)"
    FILHO_MENOR = 3, "Filho(a) menor não emancipado(a)"
    FILHO_INVALIDO = 4, "Filho(a) inválido(a)"
    PAIS = 5, "Pai/mãe com dependência econômica"
    ENTEADO_MENOR = 6, "Enteado(a) menor não emancipado(a), com dependência econômica"
    ENTEADO_INVALIDO = 7, "Enteado(a) inválido(a), com dependência econômica"
    IRMAO_MENOR = 8, "Irmão(ã) menor não emancipado(a), com dependência econômica"
    IRMAO_INVALIDO = 9, "Irmão(ã) inválido(a), com dependência econômica"
    TUTELADO = 10, "Menor tutelado"
    NETO = 11, "Neto(a)"
    EX_CONJUGE_ALIMENTOS = 12, "Ex-cônjuge que recebe pensão de alimentos"
    OUTROS = 99, "Outros"


class Dependency(InstitutionScopedModel):
    """Relação de dependência entre o segurado (titular) e outra pessoa do Cadastro Único."""

    holder = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="dependents", verbose_name="titular")
    dependent = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="dependencies_as_dependent",
                                  verbose_name="dependente")
    kind = models.PositiveSmallIntegerField("tipo de dependência", choices=DependencyType.choices)
    start_date = models.DateField("início da dependência")
    end_date = models.DateField("fim da dependência", null=True, blank=True)
    end_reason = models.CharField("motivo do fim", max_length=120, blank=True)
    economic_dependency = models.BooleanField("dependência econômica comprovada", default=False)
    pension_eligible = models.BooleanField("habilitado à pensão", default=True)
    tax_dependent = models.BooleanField("dependente para IR", default=False)
    notes = models.TextField("observações", blank=True)

    class Meta:
        db_table = "dependencies"
        verbose_name = "dependência"
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(condition=~Q(holder=models.F("dependent")), name="ck_dependency_not_self"),
            models.UniqueConstraint(fields=["holder", "dependent", "kind", "start_date"], name="uq_dependency"),
        ]

    def __str__(self):
        return f"{self.dependent} ({self.get_kind_display()}) de {self.holder}"


class DocumentType(models.TextChoices):
    IDENTIDADE = "IDENTIDADE", "Identidade (RG/CNH)"
    CPF = "CPF", "CPF"
    CERTIDAO_NASCIMENTO = "CERT_NASC", "Certidão de nascimento"
    CERTIDAO_CASAMENTO = "CERT_CASAMENTO", "Certidão de casamento / união estável"
    CERTIDAO_OBITO = "CERT_OBITO", "Certidão de óbito"
    COMPROVANTE_RESIDENCIA = "RESIDENCIA", "Comprovante de residência"
    CTC = "CTC", "Certidão de Tempo de Contribuição"
    LAUDO_MEDICO = "LAUDO", "Laudo médico"
    ATO = "ATO", "Ato / portaria / decreto"
    TITULO_ELEITOR = "TITULO", "Título de eleitor"
    RESERVISTA = "RESERVISTA", "Certificado de reservista"
    PIS = "PIS", "Cartão PIS/PASEP"
    ESCOLARIDADE = "ESCOLARIDADE", "Diploma / comprovante de escolaridade"
    NOMEACAO = "NOMEACAO", "Ato de nomeação / publicação"
    POSSE = "POSSE", "Termo de posse e exercício"
    EXAME_ADMISSIONAL = "EXAME_ADM", "Exame médico admissional"
    DECLARACAO_BENS = "DECL_BENS", "Declaração de bens"
    DECLARACAO_ACUMULACAO = "DECL_ACUMUL", "Declaração de acumulação de cargos"
    FICHA_FUNCIONAL = "FICHA_FUNC", "Ficha / histórico funcional"
    CONTRACHEQUE = "CONTRACHEQUE", "Contracheque / ficha financeira"
    OUTROS = "OUTROS", "Outros"


# Pasta de documentos da ficha do servidor
PERSONAL_DOCS = {"IDENTIDADE", "CPF", "CERT_NASC", "CERT_CASAMENTO", "CERT_OBITO", "RESIDENCIA", "TITULO", "RESERVISTA",
                 "PIS", "ESCOLARIDADE", "LAUDO"}
FUNCTIONAL_DOCS = {"NOMEACAO", "POSSE", "EXAME_ADM", "DECL_BENS", "DECL_ACUMUL", "FICHA_FUNC", "CONTRACHEQUE", "CTC", "ATO"}


def doc_folder(doc_type: str) -> str:
    return "PESSOAIS" if doc_type in PERSONAL_DOCS else "FUNCIONAIS" if doc_type in FUNCTIONAL_DOCS else "OUTROS"


class Document(InstitutionScopedModel):
    """Documento digitalizado da pessoa. Reenviar o mesmo tipo cria nova versão (a anterior é mantida)."""

    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="documents", verbose_name="pessoa")
    doc_type = models.CharField("tipo", max_length=20, choices=DocumentType.choices)
    description = models.CharField("descrição", max_length=255, blank=True)
    file = models.FileField("arquivo", upload_to="documentos/%Y/%m/")
    file_name = models.CharField("nome original", max_length=255)
    file_size = models.PositiveIntegerField("tamanho (bytes)")
    content_type = models.CharField("tipo do arquivo", max_length=100)
    sha256 = models.CharField("hash SHA-256", max_length=64)
    version = models.PositiveIntegerField("versão", default=1)
    superseded = models.BooleanField("substituído por versão mais nova", default=False)

    class Meta:
        db_table = "documents"
        verbose_name = "documento"
        ordering = ["doc_type", "-version"]

    def __str__(self):
        return f"{self.get_doc_type_display()} v{self.version} - {self.person}"


class ImportStatus(models.TextChoices):
    VALIDADO = "VALIDADO", "Validado (aguardando confirmação)"
    IMPORTADO = "IMPORTADO", "Importado"
    DESCARTADO = "DESCARTADO", "Descartado"


class ImportBatch(InstitutionScopedModel):
    """
    Lote de importação de segurados (leiaute da base atuarial SPREV).
    Fluxo: envio -> validação (nada é gravado) -> confirmação -> importação.
    Os arquivos originais ficam guardados com hash para conferência.
    """

    source_system = models.CharField("sistema / órgão de origem", max_length=150)
    status = models.CharField("situação", max_length=12, choices=ImportStatus.choices, default=ImportStatus.VALIDADO)
    files = models.JSONField("arquivos", default=list)  # [{nome, tipo, caminho, sha256, linhas}]
    report = models.JSONField("relatório de validação", default=dict)
    result = models.JSONField("resultado da importação", default=dict)
    imported_at = models.DateTimeField("importado em", null=True, blank=True)

    class Meta:
        db_table = "import_batches"
        verbose_name = "lote de importação"
        ordering = ["-created_at"]


class LegacyBenefit(InstitutionScopedModel):
    """
    Benefício (aposentadoria ou pensão) trazido de outro sistema, guardado como veio,
    até a Fase 4 (Concessão/Folha) implantá-lo. Nada é descartado.
    """

    batch = models.ForeignKey(ImportBatch, on_delete=models.PROTECT, related_name="benefits", verbose_name="lote")
    kind = models.CharField("tipo", max_length=15, choices=[("APOSENTADORIA", "Aposentadoria"), ("PENSAO", "Pensão")])
    beneficiary = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="legacy_benefits",
                                    verbose_name="beneficiário")
    instituidor = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                    verbose_name="instituidor (pensão)")
    registration = models.CharField("matrícula de origem", max_length=30, blank=True)
    segment = models.CharField("massa", max_length=20, blank=True)
    start_date = models.DateField("início do benefício", null=True, blank=True)
    amount = models.DecimalField("valor mensal", max_digits=15, decimal_places=2, null=True, blank=True)
    raw = models.JSONField("dados originais (leiaute SPREV)")
    implanted = models.BooleanField("já implantado na folha", default=False)

    class Meta:
        db_table = "legacy_benefits"
        verbose_name = "benefício importado"
        ordering = ["kind", "beneficiary__name"]
