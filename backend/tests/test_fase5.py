from datetime import date
from decimal import Decimal

import pytest

from apps.cadastros.models import Bank
from apps.concessao.models import Benefit
from apps.folha.defaults import seed_payroll
from apps.folha.engine import avos, paid_days
from apps.folha.models import Consignee, Entry, PayrollEntry, PayrollRun
from apps.folha.tax import IrTable, compute_ir
from apps.institutions.models import PayrollGroup
from apps.institutions.services import ensure_payroll_groups, set_parameter
from apps.people.models import BankAccount, Person


def cpf(n: int) -> str:
    base = f"{n:09d}"
    for size in (9, 10):
        s = sum(int(d) * w for d, w in zip(base, range(size + 1, 1, -1)))
        base += str((s * 10 % 11) % 10)
    return base


@pytest.fixture
def folha(institution):
    set_parameter(institution, "rgps.teto", "8157.41", date(2025, 1, 1))
    set_parameter(institution, "rgps.teto", "8475.55", date(2026, 1, 1), change_reason="Reajuste anual")
    ensure_payroll_groups(institution)
    seed_payroll(institution)
    return PayrollGroup.objects.get(institution=institution, segment="FINANCEIRO")


def person(inst, n, name, birth, sex=2, account=True):
    p = Person.objects.create(institution=inst, cpf=cpf(n), name=name, birth_date=birth, sex=sex)
    if account:
        bank = Bank.objects.create(institution=inst, code=f"{n % 900 + 1:03d}", name="Banco")
        BankAccount.objects.create(institution=inst, person=p, bank=bank, branch="1234", account="99999",
                                   valid_from=date(2020, 1, 1))
    return p


def _concession(inst, p):
    from django.utils import timezone

    from apps.concessao.models import Concession
    from apps.protocolo.models import Process, ProcessType, Sector

    sector = Sector.objects.create(institution=inst, name="Benefícios", code="BEN")
    ptype = ProcessType.objects.create(institution=inst, name="Aposentadoria")
    proc = Process.objects.create(institution=inst, number=1, year=2025, process_type=ptype, subject="Aposentadoria",
                                  interested=p, interested_name=p.name, current_sector=sector,
                                  opened_at=timezone.now(), opened_date=date(2025, 8, 1), deadline_days=60,
                                  due_date=date(2025, 10, 1))
    return Concession.objects.create(institution=inst, process=proc, kind="APOSENTADORIA", person=p, stage="IMPLANTADO")


def test_ir_e_dias():
    assert paid_days(date(2025, 8, 16), None, date(2025, 8, 1), date(2025, 8, 31)) == 15
    assert paid_days(date(2020, 1, 1), date(2025, 2, 28), date(2025, 2, 1), date(2025, 2, 28)) == 30
    assert paid_days(date(2020, 1, 1), date(2025, 3, 10), date(2025, 3, 1), date(2025, 3, 31)) == 10

    class B:
        start_date, end_date = date(2025, 3, 20), None
    assert avos(B, 2025) == 9  # março tem 12 dias (< 15): abril a dezembro

    from apps.folha.defaults import IR_TABLES

    t25 = IrTable(**_table(IR_TABLES[1][1]))
    t26 = IrTable(**_table(IR_TABLES[2][1]))
    # 2025: 70 anos, R$ 10.000 — parcela isenta 1.903,98; desconto simplificado (607,20 > contribuição 257,96)
    r = compute_ir(t25, taxable=Decimal("10000"), pension_income=Decimal("10000"), contribution=Decimal("257.96"),
                   dependents=0, alimony=Decimal(0), over_65=True, molestia=False)
    assert r.method == "SIMPLIFICADO" and r.tax == Decimal("1150.70")
    # 2026 (Lei 15.270/2025): até R$ 5.000 o imposto é zerado; R$ 6.000 tem redução de 179,75
    r = compute_ir(t26, taxable=Decimal("4500"), pension_income=Decimal("4500"), contribution=Decimal(0),
                   dependents=0, alimony=Decimal(0), over_65=False, molestia=False)
    assert r.tax == 0 and r.reduction == Decimal("200.39")
    r = compute_ir(t26, taxable=Decimal("6000"), pension_income=Decimal("6000"), contribution=Decimal(0),
                   dependents=0, alimony=Decimal(0), over_65=False, molestia=False)
    assert r.reduction == Decimal("179.75") and r.tax == Decimal("394.54")
    # Moléstia grave: isento
    assert compute_ir(t26, taxable=Decimal("9000"), pension_income=Decimal("9000"), contribution=Decimal(0),
                      dependents=0, alimony=Decimal(0), over_65=False, molestia=True).tax == 0


def _table(v):
    D = lambda x: Decimal(str(x)) if x is not None else None  # noqa: E731
    return {"brackets": [(D(a), D(b), D(c)) for a, b, c in v["faixas"]], "dependent": D(v["deducao_dependente"]),
            "simplified": D(v["desconto_simplificado"]), "exempt_65": D(v["parcela_isenta_65"]),
            "reduction": v["reducao"], "source": v["fonte"]}


def test_folha_mensal_fluxo_completo(institution, master, consulta, client_for, folha):
    c = client_for(master)
    inst = institution
    apos = person(inst, 100000001, "Antônio", date(1955, 1, 10))
    b_apos = Benefit.objects.create(institution=inst, kind="APOSENTADORIA", beneficiary=apos, payroll_group=folha,
                                    start_date=date(2020, 1, 1), amount=Decimal("10000.00"),
                                    legacy=None, registration="A1")
    # Pensão com duas cotas (total 12.000): teto aplicado ao total e contribuição rateada
    inst_p = person(inst, 100000002, "Instituidor", date(1950, 1, 1), account=False)
    w = person(inst, 100000003, "Viúva", date(1970, 1, 1), sex=1)
    f = person(inst, 100000004, "Filho", date(2010, 1, 1))
    q1 = Benefit.objects.create(institution=inst, kind="PENSAO", beneficiary=w, instituidor=inst_p, payroll_group=folha,
                                start_date=date(2021, 1, 1), amount=Decimal("6000.00"))
    Benefit.objects.create(institution=inst, kind="PENSAO", beneficiary=f, instituidor=inst_p, payroll_group=folha,
                           start_date=date(2021, 1, 1), amount=Decimal("6000.00"))
    # Concedido no SIST com início em 16/08/2025: retroativo de agosto (15 dias) e setembro
    novo = person(inst, 100000005, "Novo", date(1960, 5, 5))
    Benefit.objects.create(institution=inst, kind="APOSENTADORIA", beneficiary=novo, payroll_group=folha,
                           start_date=date(2025, 8, 16), amount=Decimal("3000.00"),
                           concession=_concession(inst, novo))

    # Pensão alimentícia 30% do bruto e consignação acima da margem
    alimentando = person(inst, 100000006, "Alimentando", date(2012, 1, 1), account=False)
    r = c.post("/api/v1/folha/pensoes-alimenticias/", {
        "benefit": str(b_apos.pk), "rubric_code": "0201", "percent": "30", "start": "2025-01-01",
        "contract": "0001234-56.2024.8.19.0007", "alimony_beneficiary": str(alimentando.pk)}, format="json")
    assert r.status_code == 201, r.json()
    banco = Consignee.objects.create(institution=inst, name="Banco Consignante", kind="BANCO")
    r = c.post("/api/v1/folha/consignacoes/", {"benefit": str(q1.pk), "rubric_code": "0301", "amount": "500.00",
                                               "start": "2025-10-01", "installments": 2, "consignee": str(banco.pk)},
               format="json")
    assert r.status_code == 201, r.json()
    c.post("/api/v1/folha/consignacoes/", {"benefit": str(q1.pk), "rubric_code": "0301", "amount": "5000.00",
                                           "start": "2025-10-01", "consignee": str(banco.pk)}, format="json")
    # Lançamento em rubrica automática é recusado
    assert c.post("/api/v1/folha/diferencas/", {"benefit": str(b_apos.pk), "rubric_code": "0111", "amount": "10",
                                                "start": "2025-10-01"}, format="json").status_code in (400, 409)

    assert client_for(consulta).post("/api/v1/folha/folhas/", {"year": 2025, "month": 10, "payroll_group": str(folha.pk)},
                                     format="json").status_code == 403
    run = c.post("/api/v1/folha/folhas/", {"year": 2025, "month": 10, "payroll_group": str(folha.pk)}, format="json")
    assert run.status_code == 201, run.json()
    rid = run.json()["id"]
    calc = c.post(f"/api/v1/folha/folhas/{rid}/calculate/")
    assert calc.status_code == 200, calc.json()
    assert calc.json()["status"] == "CALCULADA" and calc.json()["totals"]["beneficiarios"] == 4

    def items(benefit):
        pe = PayrollEntry.objects.get(run_id=rid, benefit=benefit)
        return pe, {(i.code, i.reference): i.amount for i in pe.items.all()}

    pe, it = items(b_apos)
    assert it[("0001", "")] == Decimal("10000.00")
    assert it[("0101", "")] == Decimal("257.96")           # 14% × (10.000 − 8.157,41)
    assert it[("0201", "30.000%")] == Decimal("3000.00")   # 30% do bruto
    # IR: 10.000 − 1.903,98 (65+) − (257,96 + 3.000) = 4.838,06 → 27,5% − 908,73 = 421,74
    assert pe.memory["irrf"]["metodo"] == "LEGAL" and pe.memory["irrf"]["imposto"] == "421.74"

    pe_q1, it_q1 = items(q1)
    assert it_q1[("0101", "")] == Decimal("268.98")  # 14% × (12.000 − 8.157,41) / 2
    assert ("0301", "1/2") in it_q1  # 500,00 cabe na margem
    assert any("margem consignável insuficiente" in w for w in pe_q1.warnings)

    pe_novo = PayrollEntry.objects.get(run_id=rid, benefit__beneficiary=novo)
    retro = {i.code: i for i in pe_novo.items.all()}["0005"]
    assert retro.amount == Decimal("4500.00")  # 15 dias de agosto (1.500) + setembro (3.000)

    comp = c.get(f"/api/v1/folha/folhas/{rid}/comparison/").json()
    assert comp["anterior"] is None and len(comp["avisos"]) >= 1

    # Fechar exige conferência; reabrir exige justificativa
    assert c.post(f"/api/v1/folha/folhas/{rid}/close/").status_code == 409
    assert c.post(f"/api/v1/folha/folhas/{rid}/check/").json()["status"] == "CONFERIDA"
    assert c.post(f"/api/v1/folha/folhas/{rid}/close/").json()["status"] == "FECHADA"
    assert c.post(f"/api/v1/folha/folhas/{rid}/calculate/").status_code == 409
    e = Entry.objects.get(benefit=q1, installments=2)
    assert e.paid_installments == 1
    assert c.post(f"/api/v1/folha/folhas/{rid}/reopen/", {"justification": "curta"}, format="json").status_code == 409
    assert c.post(f"/api/v1/folha/folhas/{rid}/reopen/", {"justification": "Correção de lançamento indevido"},
                  format="json").json()["status"] == "CONFERIDA"
    e.refresh_from_db()
    assert e.paid_installments == 0
    c.post(f"/api/v1/folha/folhas/{rid}/close/")
    assert c.post(f"/api/v1/folha/folhas/{rid}/pay/", {"payment_date": "2025-10-30"}, format="json").json()["status"] == "PAGA"
    assert c.post(f"/api/v1/folha/folhas/{rid}/reopen/", {"justification": "Tentativa após pagamento"},
                  format="json").status_code == 409

    credit = c.get(f"/api/v1/folha/folhas/{rid}/credit/").json()
    assert len(credit) == 4 and all(r["banco"] for r in credit)
    summary = c.get(f"/api/v1/folha/folhas/{rid}/summary/").json()
    assert next(r for r in summary if r["codigo"] == "0101")["quantidade"] == 3  # novo (3.000) não contribui

    # Novembro: retroativo não se repete; última parcela da consignação
    rid2 = c.post("/api/v1/folha/folhas/", {"year": 2025, "month": 11, "payroll_group": str(folha.pk)},
                  format="json").json()["id"]
    c.post(f"/api/v1/folha/folhas/{rid2}/calculate/")
    pe_novo2 = PayrollEntry.objects.get(run_id=rid2, benefit__beneficiary=novo)
    assert not pe_novo2.items.filter(code="0005").exists()
    assert c.get(f"/api/v1/folha/folhas/{rid2}/comparison/").json()["anterior"] == "10/2025"
    c.post(f"/api/v1/folha/folhas/{rid2}/check/")
    c.post(f"/api/v1/folha/folhas/{rid2}/close/")
    e.refresh_from_db()
    assert e.paid_installments == 2 and e.active is False

    # 13º: avos do ano; contribuição e IRRF exclusivos
    rid13 = c.post("/api/v1/folha/folhas/", {"year": 2025, "month": 12, "payroll_group": str(folha.pk), "kind": "DECIMO"},
                   format="json").json()["id"]
    c.post(f"/api/v1/folha/folhas/{rid13}/calculate/")
    p13 = PayrollEntry.objects.get(run_id=rid13, benefit__beneficiary=novo)
    assert {i.code: i.amount for i in p13.items.all()}["0010"] == Decimal("1250.00")  # 5/12 de 3.000 (ago com 16 dias)
    a13 = {i.code: i.amount for i in PayrollEntry.objects.get(run_id=rid13, benefit=b_apos).items.all()}
    assert a13["0010"] == Decimal("10000.00") and a13["0102"] == Decimal("257.96") and a13["0202"] == Decimal("3000.00")
    c.post(f"/api/v1/folha/folhas/{rid13}/check/")
    c.post(f"/api/v1/folha/folhas/{rid13}/close/")

    inf = c.get("/api/v1/folha/informe-rendimentos/", {"person": str(apos.pk), "year": 2025}).json()
    assert inf["quadro_3"]["2_contribuicao_previdenciaria_oficial"] == "515.92"
    assert inf["quadro_3"]["4_pensao_alimenticia"] == "6000.00"
    assert inf["quadro_4"]["1_parcela_isenta_65_anos"] == "5711.94"  # 2 meses + 13º

    retro = c.get("/api/v1/folha/retroativos/").json()["results"]
    assert len(retro) == 1 and retro[0]["valor"] == "4500.00" and len(retro[0]["meses"]) == 2
    slips = c.get("/api/v1/folha/contracheques/", {"beneficiary": str(apos.pk)}).json()["results"]
    assert len(slips) == 3 and slips[0]["competencia"] == "12/2025"
    assert c.get(f"/api/v1/folha/contracheques/{slips[0]['id']}/").json()["items"]
    assert c.get(f"/api/v1/folha/folhas/{rid}/entries/").json()["count"] == 4

    # Moléstia grave: IRRF zerado a partir da isenção (folha de janeiro/2026)
    assert c.post("/api/v1/folha/isencoes-ir/", {"person": str(apos.pk), "start": "2026-01-01", "disease": "Neoplasia maligna",
                                                 "report": "Junta médica oficial, laudo 12/2025"}, format="json").status_code == 201
    # Não se pula competência: a próxima mensal é 12/2025
    assert c.post("/api/v1/folha/folhas/", {"year": 2026, "month": 1, "payroll_group": str(folha.pk)},
                  format="json").status_code == 409
    rid_dez = c.post("/api/v1/folha/folhas/", {"year": 2025, "month": 12, "payroll_group": str(folha.pk)},
                     format="json").json()["id"]
    for step in ("calculate", "check", "close"):
        c.post(f"/api/v1/folha/folhas/{rid_dez}/{step}/")
    rid_jan = c.post("/api/v1/folha/folhas/", {"year": 2026, "month": 1, "payroll_group": str(folha.pk)},
                     format="json").json()["id"]
    assert c.post(f"/api/v1/folha/folhas/{rid_jan}/calculate/").status_code == 200
    jan = PayrollEntry.objects.get(run_id=rid_jan, benefit=b_apos)
    assert not jan.items.filter(code="0111").exists() and jan.memory["irrf"]["metodo"] == "ISENTO_MOLESTIA"
    # Contribuição de 2026 usa o teto de 2026 (8.475,55): 14% × 1.524,45 = 213,42
    assert jan.items.get(code="0101").amount == Decimal("213.42")

    # Painel usa a folha real
    dash = c.get("/api/v1/dashboard/", {"plano": "FINANCEIRO"})
    assert dash.status_code == 200
    assert PayrollRun.objects.filter(institution=inst).count() == 5


def test_rubrica_versionada(institution, master, client_for, folha):
    c = client_for(master)
    rubs = c.get("/api/v1/folha/rubricas/", {"search": "0050"}).json()["results"]
    rid = rubs[0]["id"]
    # Rubrica ainda não usada: pode editar
    assert c.patch(f"/api/v1/folha/rubricas/{rid}/", {"name": "Diferença de proventos (ajuste)"},
                   format="json").status_code == 200
    v2 = c.post(f"/api/v1/folha/rubricas/{rid}/version/", {"valid_from": "2026-01-01", "reason": "Passa a integrar a margem",
                                                           "inc_margem": True}, format="json")
    assert v2.status_code == 201, v2.json()
    assert v2.json()["version"] == 2 and v2.json()["inc_margem"] is True
    old = c.get(f"/api/v1/folha/rubricas/{rid}/").json()
    assert old["valid_to"] == "2025-12-31"
    # Segunda rubrica automática de IRRF é recusada
    assert c.post("/api/v1/folha/rubricas/", {"code": "0999", "name": "IR duplicado", "kind": "DESCONTO", "calc": "IRRF",
                                              "valid_from": "2025-01-01"}, format="json").status_code == 409
