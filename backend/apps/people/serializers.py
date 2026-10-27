from django.utils import timezone
from datetime import date

from rest_framework import serializers

from apps.core.validators import format_cpf, is_valid_cpf, only_digits

from .models import Address, BankAccount, Dependency, Document, ImportBatch, Person


def _display(field):
    return serializers.CharField(source=f"get_{field}_display", read_only=True)


def age_on(birth: date, ref: date | None = None) -> int:
    ref = ref or timezone.localdate()
    return ref.year - birth.year - ((ref.month, ref.day) < (birth.month, birth.day))


class PersonListSerializer(serializers.ModelSerializer):
    cpf_formatado = serializers.SerializerMethodField()
    idade = serializers.SerializerMethodField()
    sex_display = _display("sex")
    situacao = serializers.SerializerMethodField()

    class Meta:
        model = Person
        fields = ["id", "cpf", "cpf_formatado", "name", "social_name", "birth_date", "idade", "sex", "sex_display",
                  "death_date", "situacao"]

    def get_cpf_formatado(self, obj):
        return format_cpf(obj.cpf)

    def get_idade(self, obj):
        return age_on(obj.birth_date, obj.death_date)

    def get_situacao(self, obj):
        # Anotado na listagem (vínculos ativos e dependências); ver PersonViewSet
        if obj.death_date:
            return "Falecido(a)"
        return getattr(obj, "situacao_label", None)


class PersonSerializer(PersonListSerializer):
    # Aceitam valores com máscara; os validadores gravam só os dígitos
    cpf = serializers.CharField(max_length=14)
    name = serializers.CharField(max_length=150)  # obrigatório no cadastro manual
    pis_pasep = serializers.CharField(max_length=14, required=False, allow_blank=True)
    marital_status_display = _display("marital_status")

    class Meta:
        model = Person
        fields = PersonListSerializer.Meta.fields + [
            "marital_status", "marital_status_display", "mother_name", "father_name", "nationality",
            "birthplace_city", "birthplace_uf", "rg_number", "rg_issuer", "rg_uf", "rg_date", "pis_pasep", "voter_id",
            "education", "phone", "mobile", "email", "race", "has_disability", "disability_type", "is_invalid",
            "invalidity_date", "death_certificate", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_cpf(self, value):
        digits = only_digits(value)
        if not is_valid_cpf(digits):
            raise serializers.ValidationError("CPF inválido.")
        institution = self.context["request"].institution
        qs = Person.objects.filter(institution=institution, cpf=digits)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Já existe pessoa com este CPF no Cadastro Único.")
        return digits

    def validate_pis_pasep(self, value):
        digits = only_digits(value)
        if digits and len(digits) != 11:
            raise serializers.ValidationError("PIS/PASEP/NIT deve ter 11 dígitos.")
        return digits

    def validate(self, attrs):
        birth = attrs.get("birth_date", getattr(self.instance, "birth_date", None))
        if birth and birth > timezone.localdate():
            raise serializers.ValidationError({"birth_date": "Data de nascimento no futuro."})
        death = attrs.get("death_date", getattr(self.instance, "death_date", None))
        if death and birth and death < birth:
            raise serializers.ValidationError({"death_date": "O óbito não pode ser anterior ao nascimento."})
        if attrs.get("is_invalid") and not attrs.get("invalidity_date", getattr(self.instance, "invalidity_date", None)):
            raise serializers.ValidationError({"invalidity_date": "Informe a data da invalidez."})
        return attrs


class _PersonChildSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()

    def get_is_current(self, obj):
        return obj.valid_to is None


class AddressSerializer(_PersonChildSerializer):
    cep = serializers.CharField(max_length=9, required=False, allow_blank=True)
    uf_display = _display("uf")

    class Meta:
        model = Address
        fields = ["id", "person", "cep", "street", "number", "complement", "district", "city", "city_ibge", "uf", "uf_display",
                  "country", "valid_from", "valid_to", "is_current"]
        read_only_fields = ["valid_to"]

    def validate_cep(self, value):
        digits = only_digits(value)
        if digits and len(digits) != 8:
            raise serializers.ValidationError("CEP deve ter 8 dígitos.")
        return digits


class BankAccountSerializer(_PersonChildSerializer):
    bank_label = serializers.CharField(source="bank.__str__", read_only=True)
    account_type_display = _display("account_type")

    class Meta:
        model = BankAccount
        fields = ["id", "person", "bank", "bank_label", "branch", "branch_digit", "account", "account_digit",
                  "account_type", "account_type_display", "valid_from", "valid_to", "is_current"]
        read_only_fields = ["valid_to"]

    def validate_branch(self, value):
        return only_digits(value)

    def validate_account(self, value):
        digits = only_digits(value)
        if not digits:
            raise serializers.ValidationError("Informe o número da conta.")
        return digits


class DependencySerializer(serializers.ModelSerializer):
    kind_display = _display("kind")
    holder_name = serializers.CharField(source="holder.name", read_only=True)
    dependent_data = PersonListSerializer(source="dependent", read_only=True)
    active = serializers.SerializerMethodField()

    class Meta:
        model = Dependency
        fields = ["id", "holder", "holder_name", "dependent", "dependent_data", "kind", "kind_display", "start_date",
                  "end_date", "end_reason", "economic_dependency", "pension_eligible", "tax_dependent", "notes",
                  "active"]

    def get_active(self, obj):
        return obj.end_date is None

    def validate(self, attrs):
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        if end and start and end < start:
            raise serializers.ValidationError({"end_date": "O fim não pode ser anterior ao início."})
        if end and not attrs.get("end_reason", getattr(self.instance, "end_reason", "")):
            raise serializers.ValidationError({"end_reason": "Informe o motivo do fim da dependência."})
        return attrs


class ImportBatchSerializer(serializers.ModelSerializer):
    status_display = _display("status")
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    files = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = ["id", "source_system", "status", "status_display", "files", "report", "result", "imported_at",
                  "created_by_name", "created_at"]
        read_only_fields = fields

    def get_files(self, obj):
        # O caminho interno do arquivo não é exposto
        return [{k: v for k, v in f.items() if k != "caminho"} for f in obj.files]


class DocumentSerializer(serializers.ModelSerializer):
    doc_type_display = _display("doc_type")
    uploaded_by = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    pasta = serializers.SerializerMethodField()

    def get_pasta(self, obj):
        from .models import doc_folder

        return doc_folder(obj.doc_type)

    class Meta:
        model = Document
        fields = ["id", "person", "doc_type", "doc_type_display", "pasta", "description", "file_name", "file_size",
                  "content_type", "sha256", "version", "superseded", "uploaded_by", "created_at"]
        read_only_fields = fields
