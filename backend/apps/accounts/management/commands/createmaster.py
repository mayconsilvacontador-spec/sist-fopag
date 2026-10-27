"""
Cria (ou promove) um usuário com perfil MASTER na instituição informada.

Exemplos:
    python manage.py createmaster --username maycon --full-name "Maycon Silva" --email maycon@exemplo.com
    python manage.py createmaster --username maycon --institution PREVIBAM

A senha é solicitada no terminal (não aparece no histórico). Para uso em
scripts, defina a variável de ambiente SIST_MASTER_PASSWORD.
"""
import getpass
import os

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Membership, MembershipRole, Role, User
from apps.accounts.services import sync_permissions
from apps.audit.services import log_event
from apps.core.context import audit_context
from apps.institutions.models import Institution


class Command(BaseCommand):
    help = "Cria um usuário administrador com perfil MASTER."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--full-name", default="")
        parser.add_argument("--email", default="")
        parser.add_argument("--institution", default="PREVIBAM", help="Sigla da instituição.")
        parser.add_argument("--superuser", action="store_true",
                            help="Também concede acesso ao /django-admin/ (técnico).")

    @transaction.atomic
    def handle(self, *args, **opts):
        sync_permissions(verbose=False)
        institution = Institution.objects.filter(short_name__iexact=opts["institution"]).first()
        if institution is None:
            raise CommandError(
                f"Instituição '{opts['institution']}' não encontrada. Execute antes: python manage.py seed_initial"
            )
        username = opts["username"].strip().lower()
        user = User.objects.filter(username__iexact=username).first()
        created = user is None

        with audit_context(source="command", justification="Criação de usuário MASTER via linha de comando"):
            if created:
                full_name = opts["full_name"] or input("Nome completo: ").strip()
                if not full_name:
                    raise CommandError("Nome completo é obrigatório.")
                password = os.environ.get("SIST_MASTER_PASSWORD") or self._ask_password()
                user = User(username=username, full_name=full_name, email=opts["email"],
                            default_institution=institution, must_change_password=False)
                try:
                    password_validation.validate_password(password, user)
                except ValidationError as exc:
                    raise CommandError("Senha inválida: " + " ".join(exc.messages))
                user.set_password(password)
                user.is_staff = bool(opts["superuser"])
                user.is_superuser = bool(opts["superuser"])
                user.save()
            membership, _ = Membership.objects.get_or_create(user=user, institution=institution)
            master = Role.objects.get(code="MASTER", institution__isnull=True)
            MembershipRole.objects.get_or_create(membership=membership, role=master)
            log_event("PERMISSION_CHANGE", module="admin.usuarios", obj=user,
                      new={"perfis": ["MASTER"]}, institution_id=institution.pk)

        verb = "criado" if created else "promovido a MASTER"
        self.stdout.write(self.style.SUCCESS(f"Usuário '{username}' {verb} em {institution.short_name}."))

    def _ask_password(self) -> str:
        p1 = getpass.getpass("Senha (mín. 10 caracteres): ")
        p2 = getpass.getpass("Confirme a senha: ")
        if p1 != p2:
            raise CommandError("As senhas não conferem.")
        return p1
