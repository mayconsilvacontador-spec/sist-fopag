"""
Registro de provedores da pesquisa global.

Cada módulo registra uma função que recebe (request, termo, limite) e
devolve uma lista de resultados. A permissão de visualização do módulo é
verificada antes de chamar o provedor. Próximas fases registrarão:
segurados (nome/CPF/matrícula), benefícios, processos, pensionistas e
instituidores.
"""
from dataclasses import dataclass

from django.db.models import Q


@dataclass
class SearchProvider:
    key: str
    label: str
    permission: str
    fn: callable


PROVIDERS: list[SearchProvider] = []


def provider(key: str, label: str, permission: str):
    def decorator(fn):
        PROVIDERS.append(SearchProvider(key, label, permission, fn))
        return fn
    return decorator


@provider("usuarios", "Usuários", "admin.usuarios:visualizar")
def search_users(request, term, limit):
    from apps.accounts.models import User
    from apps.core.validators import only_digits

    digits = only_digits(term)
    cond = Q(full_name__icontains=term) | Q(username__icontains=term) | Q(email__icontains=term)
    if len(digits) >= 3:
        cond |= Q(cpf__startswith=digits)
    qs = User.objects.filter(cond, memberships__institution=request.institution).distinct()[:limit]
    return [
        {"id": str(u.pk), "title": u.full_name, "subtitle": f"Login: {u.username}",
         "href": f"/administracao/usuarios?id={u.pk}"}
        for u in qs
    ]


@provider("perfis", "Perfis", "admin.perfis:visualizar")
def search_roles(request, term, limit):
    from apps.accounts.models import Role

    qs = Role.objects.filter(
        Q(name__icontains=term) | Q(code__icontains=term),
        Q(institution__isnull=True) | Q(institution=request.institution),
    )[:limit]
    return [
        {"id": str(r.pk), "title": r.name, "subtitle": f"Perfil {r.code}",
         "href": f"/administracao/perfis?id={r.pk}"}
        for r in qs
    ]


@provider("parametros", "Parâmetros", "admin.parametros:visualizar")
def search_parameters(request, term, limit):
    from apps.institutions.models import Parameter

    qs = Parameter.objects.filter(
        Q(key__icontains=term) | Q(description__icontains=term),
        institution=request.institution, valid_to__isnull=True,
    )[:limit]
    return [
        {"id": str(p.pk), "title": p.key, "subtitle": p.description or f"Versão {p.version}",
         "href": f"/administracao/parametros?key={p.key}"}
        for p in qs
    ]
