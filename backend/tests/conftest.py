import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Membership, MembershipRole, Role, User
from apps.accounts.services import sync_permissions
from apps.institutions.models import BenefitPlan, Competence, FiscalYear, Institution, PlanKind

PASSWORD = "Senha@Forte#2026"


@pytest.fixture
def institution(db):
    sync_permissions(verbose=False)
    inst = Institution.objects.create(name="Instituto de Teste", short_name="TESTE", city="Barra Mansa", uf="RJ")
    BenefitPlan.objects.create(institution=inst, code="FIN", name="Plano Financeiro", kind=PlanKind.FINANCEIRO)
    BenefitPlan.objects.create(institution=inst, code="PREV", name="Plano Previdenciário", kind=PlanKind.PREVIDENCIARIO)
    fy = FiscalYear.objects.create(institution=inst, year=2026)
    Competence.objects.create(institution=inst, fiscal_year=fy, year=2026, month=9, is_reference=True)
    return inst


def make_user(institution, username, role_code, **extra):
    user = User(username=username, full_name=f"Usuário {username}", must_change_password=False,
                default_institution=institution, **extra)
    user.set_password(PASSWORD)
    user.save()
    m = Membership.objects.create(user=user, institution=institution)
    if role_code:
        MembershipRole.objects.create(membership=m, role=Role.objects.get(code=role_code, institution__isnull=True))
    return user


@pytest.fixture
def master(institution):
    return make_user(institution, "master", "MASTER")


@pytest.fixture
def consulta(institution):
    return make_user(institution, "consulta", "CONSULTA")


@pytest.fixture
def client_for():
    def _client(user):
        c = APIClient()
        c.force_authenticate(user)
        return c
    return _client


@pytest.fixture
def setores(institution):
    """Um usuário por setor do fluxo de concessão (segregação de funções)."""
    return {
        "beneficios": make_user(institution, "beneficios", "PREVIDENCIARIO"),
        "juridico": make_user(institution, "juridico", "JURIDICO"),
        "controle": make_user(institution, "controle", "CONTROLE_INTERNO"),
        "presidente": make_user(institution, "presidente", "PRESIDENCIA"),
        "folha": make_user(institution, "folha", "FOLHA"),
    }


def historico(institution, person, inicio, fim, valor, fator="1", tabela=None, regime="RPPS", fatores=True):
    """
    Histórico contributivo completo para o cálculo da concessão: salários mensais de `inicio` a `fim`, tabela de
    fatores (mês `tabela`, padrão = mês seguinte a `fim`) e séries de salário mínimo/teto do RGPS.
    """
    from datetime import date
    from decimal import Decimal

    from apps.previdencia.management.commands.seed_rules import seed_rgps_ceiling
    from apps.previdencia.models import ContributionSalary, CorrectionFactor

    seed_rgps_ceiling(institution)
    m = date(inicio.year, inicio.month, 1)
    tabela = tabela or date(fim.year + fim.month // 12, fim.month % 12 + 1, 1)
    while m <= fim:
        ContributionSalary.objects.get_or_create(institution=institution, person=person, competence=m, regime=regime,
                                                 defaults={"amount": Decimal(str(valor))})
        if fatores:
            CorrectionFactor.objects.get_or_create(institution=institution, table_month=tabela, competence=m,
                                                   defaults={"factor": Decimal(fator)})
        m = date(m.year + m.month // 12, m.month % 12 + 1, 1)


def anexar_checklist(client, cid):
    """Anexa um PDF de teste a cada documento pendente do setor que está com o processo (processo digital)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    data = client.get(f"/api/v1/concessoes/{cid}/checklist/").json()
    for item in data["itens"]:
        if item["sector"] == data["setor_atual"] and item["source"] == "ANEXO" and item["status"] == "PENDENTE":
            f = SimpleUploadedFile(f"{item['id']}.pdf", b"%PDF-1.4 teste " + item["id"].encode(), content_type="application/pdf")
            r = client.post(f"/api/v1/concessoes/{cid}/checklist/{item['id']}/attach/", {"file": f}, format="multipart")
            assert r.status_code == 200, r.json()


def enviar(client, cid):
    """Benefícios: completa o checklist e envia ao Jurídico (ciência dos avisos + senha)."""
    anexar_checklist(client, cid)
    return client.post(f"/api/v1/concessoes/{cid}/send/", {"acknowledge_warnings": True, "password": PASSWORD},
                       format="json")


def concluir(client_for, setores, cid, numero, data, revisao=False):
    """Percorre o fluxo da PREVIBAM: envio → parecer → (controle) → assinatura → publicação → implantação."""
    c = {k: client_for(u) for k, u in setores.items()}
    assert enviar(c["beneficios"], cid).status_code == 200
    anexar_checklist(c["juridico"], cid)
    r = c["juridico"].post(f"/api/v1/concessoes/{cid}/legal/", {"favorable": True, "password": PASSWORD,
                           "text": "Requisitos constitucionais e legais atendidos; fundamentação correta."}, format="json")
    assert r.status_code == 200, r.json()
    if not revisao:
        r = c["controle"].post(f"/api/v1/concessoes/{cid}/compliance/", {"conform": True, "password": PASSWORD,
                               "text": "Regras e memória de cálculo conferidas."}, format="json")
        assert r.status_code == 200, r.json()
    r = c["presidente"].post(f"/api/v1/concessoes/{cid}/sign/", {"nature": "PORTARIA", "number": numero,
                             "act_date": data, "password": PASSWORD}, format="json")
    assert r.status_code == 200, r.json()
    anexar_checklist(c["folha"], cid)
    r = c["folha"].post(f"/api/v1/concessoes/{cid}/publish/", {"publication_date": data, "password": PASSWORD,
                        "media": "Notícia Oficial nº 1"}, format="json")
    assert r.status_code == 200, r.json()
    r = c["folha"].post(f"/api/v1/concessoes/{cid}/implant/", {"password": PASSWORD}, format="json")
    assert r.status_code == 200, r.json()
    return r.json()
