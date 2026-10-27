"""
Gestão financeira e arrecadação (Fase 7).

Segregação de massas: toda entidade financeira tem FK obrigatória para o plano (benefit_plans). Conta bancária,
lote de pagamento, contribuição, aporte, parcelamento e receita sempre pertencem a UM plano — o lote de pagamento
só aceita conta do mesmo plano da folha (Financeiro paga pela conta do Financeiro; Previdenciário e Compra de
Vidas, pela do Previdenciário).

Nada é excluído: lotes e arquivos ficam registrados (com hash SHA-256); itens rejeitados pelo banco vão para um
novo lote.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import InstitutionScopedModel


class TreasuryAccount(InstitutionScopedModel):
    """Conta bancária da instituição (uma ou mais por plano)."""

    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    bank = models.ForeignKey("cadastros.Bank", on_delete=models.PROTECT, related_name="+", verbose_name="banco")
    branch = models.CharField("agência", max_length=5)
    branch_digit = models.CharField("dígito da agência", max_length=1, blank=True)
    account = models.CharField("conta", max_length=12)
    account_digit = models.CharField("dígito da conta", max_length=2, blank=True)
    purpose = models.CharField("finalidade", max_length=12, default="PAGAMENTO",
                               choices=[("PAGAMENTO", "Pagamento de benefícios"), ("ARRECADACAO", "Arrecadação"),
                                        ("APLICACAO", "Aplicação financeira"), ("OUTROS", "Outros")])
    description = models.CharField("descrição", max_length=120, blank=True)
    # CNAB 240 (dados do convênio com o banco)
    agreement = models.CharField("código do convênio (CNAB)", max_length=20, blank=True)
    cnab_service = models.CharField("tipo de serviço CNAB", max_length=2, default="30",
                                    help_text="30 = pagamento de salários/benefícios; 98 = pagamentos diversos.")
    cnab_file_version = models.CharField("versão do leiaute do arquivo", max_length=3, default="089")
    cnab_batch_version = models.CharField("versão do leiaute do lote", max_length=3, default="045")
    next_nsa = models.PositiveIntegerField("próximo NSA (nº sequencial do arquivo)", default=1)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "treasury_accounts"
        verbose_name = "conta bancária da instituição"
        ordering = ["plan__code", "bank__code"]

    def __str__(self):
        return f"{self.bank.code} ag. {self.branch} c/c {self.account}-{self.account_digit} ({self.plan.code})"


# ------------------------------------------------------------------ pagamentos
class BatchStatus(models.TextChoices):
    RASCUNHO = "RASCUNHO", "Rascunho"
    APROVADO = "APROVADO", "Aprovado"
    ARQUIVO_GERADO = "ARQUIVO_GERADO", "Arquivo gerado (aguardando retorno)"
    PROCESSADO = "PROCESSADO", "Retorno processado"
    CANCELADO = "CANCELADO", "Cancelado"


class PaymentBatch(InstitutionScopedModel):
    payroll_run = models.ForeignKey("folha.PayrollRun", on_delete=models.PROTECT, related_name="payment_batches",
                                    verbose_name="folha")
    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT, related_name="batches",
                                verbose_name="conta pagadora")
    number = models.PositiveIntegerField("nº do lote")
    payment_date = models.DateField("data do crédito")
    status = models.CharField("situação", max_length=16, choices=BatchStatus.choices, default=BatchStatus.RASCUNHO)
    total = models.DecimalField("valor total", max_digits=15, decimal_places=2, default=0)
    items_count = models.PositiveIntegerField("quantidade", default=0)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+", verbose_name="aprovado por")
    approved_at = models.DateTimeField("aprovado em", null=True, blank=True)
    notes = models.TextField("observações", blank=True)

    class Meta:
        db_table = "payment_batches"
        verbose_name = "lote de pagamento"
        ordering = ["-number"]
        constraints = [models.UniqueConstraint(fields=["institution", "number"], name="uq_payment_batch_number")]

    def __str__(self):
        return f"Lote {self.number}"


class ItemStatus(models.TextChoices):
    PENDENTE = "PENDENTE", "A enviar"
    ENVIADO = "ENVIADO", "Enviado ao banco"
    PAGO = "PAGO", "Pago"
    REJEITADO = "REJEITADO", "Rejeitado pelo banco"


class PaymentItem(InstitutionScopedModel):
    batch = models.ForeignKey(PaymentBatch, on_delete=models.PROTECT, related_name="items", verbose_name="lote")
    payroll_entry = models.ForeignKey("folha.PayrollEntry", on_delete=models.PROTECT, related_name="payment_items",
                                      verbose_name="contracheque")
    beneficiary = models.ForeignKey("people.Person", on_delete=models.PROTECT, related_name="+",
                                    verbose_name="beneficiário")
    our_number = models.CharField("seu número (identificação no arquivo)", max_length=20)
    bank = models.JSONField("conta de crédito", default=dict)
    amount = models.DecimalField("valor", max_digits=15, decimal_places=2)
    status = models.CharField("situação", max_length=10, choices=ItemStatus.choices, default=ItemStatus.PENDENTE)
    return_code = models.CharField("ocorrência do banco", max_length=10, blank=True)
    return_message = models.CharField("mensagem", max_length=255, blank=True)

    class Meta:
        db_table = "payment_items"
        verbose_name = "item de pagamento"
        ordering = ["beneficiary__name"]
        constraints = [models.UniqueConstraint(fields=["institution", "our_number"], name="uq_payment_our_number")]


class BankFile(InstitutionScopedModel):
    account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT, related_name="files", verbose_name="conta")
    kind = models.CharField("tipo", max_length=10, choices=[("REMESSA", "Remessa (CNAB 240)"),
                                                             ("RETORNO", "Retorno (CNAB 240)"),
                                                             ("EXTRATO", "Extrato (OFX)")])
    batch = models.ForeignKey(PaymentBatch, on_delete=models.PROTECT, null=True, blank=True, related_name="files",
                              verbose_name="lote")
    nsa = models.PositiveIntegerField("NSA", null=True, blank=True)
    file_name = models.CharField("nome do arquivo", max_length=120)
    content = models.TextField("conteúdo")
    sha256 = models.CharField("SHA-256", max_length=64)
    summary = models.JSONField("resumo", default=dict, blank=True)

    class Meta:
        db_table = "bank_files"
        verbose_name = "arquivo bancário"
        ordering = ["-created_at"]


# ------------------------------------------------------------------ arrecadação
class ContributionKind(models.TextChoices):
    SERVIDOR = "SERVIDOR", "Contribuição do servidor (ativo)"
    PATRONAL = "PATRONAL", "Contribuição patronal"
    APOSENTADOS = "APOSENTADOS", "Contribuição de aposentados e pensionistas (retida na folha)"


class Contribution(InstitutionScopedModel):
    """Contribuição devida por competência, órgão e plano."""

    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    organ = models.ForeignKey("cadastros.Organ", on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                              verbose_name="órgão")
    kind = models.CharField("tipo", max_length=12, choices=ContributionKind.choices)
    competence = models.DateField("competência (1º dia do mês)")
    base = models.DecimalField("base de cálculo", max_digits=15, decimal_places=2)
    rate = models.DecimalField("alíquota", max_digits=7, decimal_places=4)
    amount = models.DecimalField("valor devido", max_digits=15, decimal_places=2)
    due_date = models.DateField("vencimento")
    source = models.CharField("origem", max_length=12,
                              choices=[("ESTIMADA", "Estimada pelos vínculos (vencimento base)"),
                                       ("INFORMADA", "Informada pelo órgão"),
                                       ("FOLHA", "Folha de benefícios do RPPS")])
    payroll_run = models.ForeignKey("folha.PayrollRun", on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="+", verbose_name="folha de origem")
    notes = models.TextField("observações", blank=True)
    active = models.BooleanField("ativa", default=True)

    class Meta:
        db_table = "contributions"
        verbose_name = "contribuição"
        ordering = ["-competence", "organ__name", "kind"]


class AporteKind(models.TextChoices):
    DEFICIT = "DEFICIT", "Aporte para equacionamento do déficit atuarial"
    INSUFICIENCIA = "INSUFICIENCIA", "Cobertura de insuficiência financeira (Plano Financeiro)"
    COMPRA_VIDAS = "COMPRA_VIDAS", "Aporte da operação de Compra de Vidas"
    OUTROS = "OUTROS", "Outros aportes"


class Aporte(InstitutionScopedModel):
    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    kind = models.CharField("tipo", max_length=14, choices=AporteKind.choices)
    competence = models.DateField("competência (1º dia do mês)")
    amount = models.DecimalField("valor devido", max_digits=15, decimal_places=2)
    due_date = models.DateField("vencimento")
    legal_basis = models.CharField("fundamento legal", max_length=255, blank=True)
    life_purchase = models.ForeignKey("institutions.LifePurchase", on_delete=models.PROTECT, null=True, blank=True,
                                      related_name="+", verbose_name="lote de compra de vidas")
    notes = models.TextField("observações", blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "aportes"
        verbose_name = "aporte"
        ordering = ["-competence"]


class InstallmentAgreement(InstitutionScopedModel):
    """Termo de acordo de parcelamento de débitos do ente (registrado no CADPREV)."""

    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    organ = models.ForeignKey("cadastros.Organ", on_delete=models.PROTECT, related_name="+", verbose_name="órgão devedor")
    number = models.CharField("nº do termo", max_length=40)
    cadprev_number = models.CharField("nº no CADPREV", max_length=40, blank=True)
    signed_date = models.DateField("data do termo")
    legal_basis = models.CharField("lei autorizativa", max_length=255, blank=True)
    principal = models.DecimalField("valor consolidado", max_digits=15, decimal_places=2)
    installments = models.PositiveSmallIntegerField("nº de parcelas")
    first_due = models.DateField("vencimento da 1ª parcela")
    index = models.CharField("índice de atualização", max_length=10, default="IPCA",
                             choices=[("IPCA", "IPCA"), ("INPC", "INPC"), ("SELIC", "SELIC"), ("NENHUM", "Nenhum")])
    monthly_interest = models.DecimalField("juros ao mês (%)", max_digits=6, decimal_places=3, default=0)
    debt_period = models.CharField("competências parceladas", max_length=120, blank=True)
    status = models.CharField("situação", max_length=10, default="ATIVO",
                              choices=[("ATIVO", "Em dia / ativo"), ("QUITADO", "Quitado"), ("RESCINDIDO", "Rescindido")])
    notes = models.TextField("observações", blank=True)

    class Meta:
        db_table = "installment_agreements"
        verbose_name = "parcelamento"
        ordering = ["-signed_date"]
        constraints = [models.UniqueConstraint(fields=["institution", "number"], name="uq_installment_agreement")]


class Installment(InstitutionScopedModel):
    agreement = models.ForeignKey(InstallmentAgreement, on_delete=models.PROTECT, related_name="parcels",
                                  verbose_name="parcelamento")
    number = models.PositiveSmallIntegerField("parcela")
    due_date = models.DateField("vencimento")
    amount = models.DecimalField("valor nominal", max_digits=15, decimal_places=2)

    class Meta:
        db_table = "installments"
        verbose_name = "parcela"
        ordering = ["agreement", "number"]
        constraints = [models.UniqueConstraint(fields=["agreement", "number"], name="uq_installment_number")]


class RevenueKind(models.TextChoices):
    CONTRIBUICAO = "CONTRIBUICAO", "Contribuição"
    APORTE = "APORTE", "Aporte"
    PARCELAMENTO = "PARCELAMENTO", "Parcela de parcelamento"
    COMPREV = "COMPREV", "Compensação previdenciária (COMPREV)"
    RENDIMENTOS = "RENDIMENTOS", "Rendimentos de aplicações"
    OUTRAS = "OUTRAS", "Outras receitas"


class Revenue(InstitutionScopedModel):
    """Receita realizada (crédito efetivo). Pagamentos de contribuição, aporte e parcela são receitas."""

    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    kind = models.CharField("tipo", max_length=12, choices=RevenueKind.choices)
    date = models.DateField("data do crédito")
    competence = models.DateField("competência (1º dia do mês)", null=True, blank=True)
    amount = models.DecimalField("valor principal", max_digits=15, decimal_places=2)
    fines = models.DecimalField("multa/juros/atualização", max_digits=15, decimal_places=2, default=0)
    account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                verbose_name="conta de crédito")
    contribution = models.ForeignKey(Contribution, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="payments", verbose_name="contribuição")
    aporte = models.ForeignKey(Aporte, on_delete=models.PROTECT, null=True, blank=True, related_name="payments",
                               verbose_name="aporte")
    installment = models.ForeignKey(Installment, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name="payments", verbose_name="parcela")
    description = models.CharField("descrição", max_length=200, blank=True)
    document = models.CharField("documento (guia, OB, aviso)", max_length=60, blank=True)
    active = models.BooleanField("ativa", default=True, help_text="Estorno = inativar com justificativa.")

    class Meta:
        db_table = "revenues"
        verbose_name = "receita"
        ordering = ["-date"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="ck_revenue_amount")]


# ------------------------------------------------------------------ conciliação bancária
class StatementLine(InstitutionScopedModel):
    account = models.ForeignKey(TreasuryAccount, on_delete=models.PROTECT, related_name="statement_lines",
                                verbose_name="conta")
    file = models.ForeignKey(BankFile, on_delete=models.PROTECT, related_name="lines", verbose_name="extrato")
    date = models.DateField("data")
    amount = models.DecimalField("valor (+ crédito / − débito)", max_digits=15, decimal_places=2)
    fitid = models.CharField("identificador do lançamento", max_length=80)
    memo = models.CharField("histórico", max_length=255, blank=True)
    revenue = models.ForeignKey(Revenue, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                verbose_name="receita conciliada")
    batch = models.ForeignKey(PaymentBatch, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                              verbose_name="lote de pagamento conciliado")
    reconciled = models.BooleanField("conciliado", default=False)
    note = models.CharField("justificativa (conciliação manual)", max_length=255, blank=True)

    class Meta:
        db_table = "statement_lines"
        verbose_name = "lançamento do extrato"
        ordering = ["-date", "fitid"]
        constraints = [models.UniqueConstraint(fields=["account", "fitid"], name="uq_statement_fitid")]


# ------------------------------------------------------------------ contabilidade
class AccountingMapping(InstitutionScopedModel):
    """De-para contábil: rubrica da folha ou tipo de receita -> contas (PCASP) por plano."""

    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    source = models.CharField("origem", max_length=10, choices=[("RUBRICA", "Rubrica da folha"),
                                                                 ("RECEITA", "Tipo de receita"),
                                                                 ("PAGAMENTO", "Pagamento líquido da folha")])
    source_code = models.CharField("código (rubrica ou tipo de receita)", max_length=20)
    debit = models.CharField("conta débito", max_length=30)
    credit = models.CharField("conta crédito", max_length=30)
    history = models.CharField("histórico padrão", max_length=150, blank=True)
    active = models.BooleanField("ativo", default=True)

    class Meta:
        db_table = "accounting_mappings"
        verbose_name = "de-para contábil"
        ordering = ["plan", "source", "source_code"]
        constraints = [models.UniqueConstraint(fields=["plan", "source", "source_code"], condition=Q(active=True),
                                               name="uq_accounting_mapping_active")]


class AccountingExport(InstitutionScopedModel):
    plan = models.ForeignKey("institutions.BenefitPlan", on_delete=models.PROTECT, related_name="+", verbose_name="plano")
    period = models.DateField("competência (1º dia do mês)")
    lines = models.PositiveIntegerField("lançamentos")
    total = models.DecimalField("total", max_digits=15, decimal_places=2)
    content = models.TextField("arquivo (CSV)")
    sha256 = models.CharField("SHA-256", max_length=64)
    unmapped = models.JSONField("sem de-para", default=list, blank=True)

    class Meta:
        db_table = "accounting_exports"
        verbose_name = "exportação contábil"
        ordering = ["-created_at"]
