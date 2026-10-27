import io
from datetime import date
from decimal import Decimal

import pytest

from apps.cadastros.models import Bank, Ente, Organ, Position
from apps.concessao.models import Benefit
from apps.employment.models import EmploymentLink
from apps.financeiro.defaults import seed_financeiro
from apps.financeiro.models import BankFile, Contribution, PaymentItem, Revenue
from apps.folha.defaults import seed_payroll
from apps.folha.models import PayrollRun
from apps.institutions.models import PayrollGroup
from apps.institutions.services import ensure_payroll_groups, set_parameter
from apps.people.models import BankAccount, Person


@pytest.fixture
def base(institution):
    institution.cnpj = "11222333000181"
    institution.save()
    set_parameter(institution, "rgps.teto", "8157.41", date(2025, 1, 1))
    ensure_payroll_groups(institution)
    seed_payroll(institution)
    seed_financeiro(institution)
    prev = PayrollGroup.objects.get(institution=institution, segment="PREVIDENCIARIO")
    fin = PayrollGroup.objects.get(institution=institution, segment="FINANCEIRO")
    bb = Bank.objects.create(institution=institution, code="001", name="Banco do Brasil")
    cef = Bank.objects.create(institution=institution, code="104", name="Caixa")
    return {"prev": prev, "fin": fin, "bb": bb, "cef": cef}


def _person(inst, cpf, name, bank, account):
    p = Person.objects.create(institution=inst, cpf=cpf, name=name, birth_date=date(1960, 1, 1), sex=2)
    BankAccount.objects.create(institution=inst, person=p, bank=bank, branch="1234", branch_digit="5",
                               account=account, account_digit="6", valid_from=date(2020, 1, 1))
    return p


def _closed_run(c, group):
    rid = c.post("/api/v1/folha/folhas/", {"year": 2025, "month": 10, "payroll_group": str(group.pk)},
                 format="json").json()["id"]
    for step in ("calculate", "check", "close"):
        assert c.post(f"/api/v1/folha/folhas/{rid}/{step}/").status_code == 200
    return rid


def test_pagamento_cnab_retorno_e_segregacao(institution, master, client_for, base):
    c = client_for(master)
    p1 = _person(institution, "52998224725", "Ana Paga", base["bb"], "1111")
    p2 = _person(institution, "11144477735", "Bruno Outro Banco", base["cef"], "2222")
    for p, v in ((p1, "3000.00"), (p2, "2000.00")):
        Benefit.objects.create(institution=institution, kind="APOSENTADORIA", beneficiary=p, payroll_group=base["prev"],
                               start_date=date(2024, 1, 1), amount=Decimal(v))
    rid = _closed_run(c, base["prev"])

    acc = lambda plan, num: c.post("/api/v1/financeiro/contas/", {  # noqa: E731
        "plan": str(plan.pk), "bank": str(base["bb"].pk), "branch": "1234", "branch_digit": "5", "account": num,
        "account_digit": "X", "agreement": "123456"}, format="json").json()["id"]
    acc_prev, acc_fin = acc(base["prev"].plan, "90001"), acc(base["fin"].plan, "90002")

    bad = c.post("/api/v1/financeiro/lotes/", {"run": rid, "account": acc_fin, "payment_date": "2025-10-30"}, format="json")
    assert bad.status_code == 409 and "Segregação" in bad.json()["detail"]
    batch = c.post("/api/v1/financeiro/lotes/", {"run": rid, "account": acc_prev, "payment_date": "2025-10-30"},
                   format="json").json()
    assert batch["items_count"] == 2 and Decimal(batch["total"]) == Decimal("5000.00")
    bid = batch["id"]
    assert c.post(f"/api/v1/financeiro/lotes/{bid}/remittance/").status_code == 409  # não aprovado
    c.post(f"/api/v1/financeiro/lotes/{bid}/approve/")
    f = c.post(f"/api/v1/financeiro/lotes/{bid}/remittance/").json()
    assert f["summary"]["quantidade"] == 2 and len(f["summary"]["lotes"]) == 2  # mesmo banco + TED
    content = BankFile.objects.get(pk=f["id"]).content
    lines = content.rstrip("\r\n").split("\r\n")
    assert all(len(ln) == 240 for ln in lines)
    assert lines[0][:3] == "001" and lines[0][17] == "2" and lines[0][18:32] == "11222333000181"
    assert lines[-1][3:8] == "99999" and lines[-1][17:23] == "000002"  # 2 lotes
    seg_a = [ln for ln in lines if ln[7] == "3" and ln[13] == "A"]
    assert seg_a[0][119:134] == "000000000300000" and seg_a[1][17:20] == "018"  # TED para a Caixa
    dl = c.get(f"/api/v1/financeiro/arquivos/{f['id']}/download/")
    assert dl.status_code == 200 and "attachment" in dl["Content-Disposition"]

    # Retorno: Ana paga (00), Bruno rejeitado (AN — conta inválida)
    ret = []
    for ln in lines:
        if ln[7] == "3" and ln[13] == "A":
            code = "00" if "ANA PAGA" in ln else "AN"
            ln = ln[:230] + code.ljust(10)
        ret.append(ln)
    up = io.BytesIO("\r\n".join(ret).encode("latin-1"))
    up.name = "retorno.ret"
    out = c.post("/api/v1/financeiro/arquivos/import-return/", {"account": acc_prev, "file": up}, format="multipart").json()
    assert out["PAGO"] == 1 and out["REJEITADO"] == 1
    assert PaymentItem.objects.get(beneficiary=p2).return_message.startswith("AN")
    assert PayrollRun.objects.get(pk=rid).status == "FECHADA"  # ainda falta um pagamento

    # Novo lote só com o rejeitado; confirmação manual -> folha PAGA
    b2 = c.post("/api/v1/financeiro/lotes/", {"run": rid, "account": acc_prev, "payment_date": "2025-11-03"},
                format="json").json()
    assert b2["items_count"] == 1
    c.post(f"/api/v1/financeiro/lotes/{b2['id']}/approve/")
    c.post(f"/api/v1/financeiro/lotes/{b2['id']}/remittance/")
    assert c.post(f"/api/v1/financeiro/lotes/{b2['id']}/confirm/", {"justification": "curto"}, format="json").status_code == 409
    c.post(f"/api/v1/financeiro/lotes/{b2['id']}/confirm/", {"justification": "Banco confirmou por ofício nº 12"},
           format="json")
    run = PayrollRun.objects.get(pk=rid)
    assert run.status == "PAGA" and run.payment_date == date(2025, 11, 3)


def test_arrecadacao_conciliacao_e_contabil(institution, master, client_for, base):
    c = client_for(master)
    ente = Ente.objects.create(institution=institution, name="Município")
    organ = Organ.objects.create(institution=institution, ente=ente, name="Prefeitura")
    pos = Position.objects.create(institution=institution, name="Agente", cargo_type=7)
    for i, (cpf, sal) in enumerate((("52998224725", "5000.00"), ("11144477735", "3000.00"))):
        p = Person.objects.create(institution=institution, cpf=cpf, name=f"Servidor {i}", birth_date=date(1980, 1, 1), sex=2)
        EmploymentLink.objects.create(institution=institution, person=p, organ=organ, position=pos, registration=str(i),
                                      public_service_start=date(2010, 1, 1), ente_start=date(2010, 1, 1),
                                      position_start=date(2010, 1, 1), segment="PREVIDENCIARIO", base_salary=Decimal(sal))
    plan_prev, plan_fin = base["prev"].plan, base["fin"].plan
    acc_prev = c.post("/api/v1/financeiro/contas/", {"plan": str(plan_prev.pk), "bank": str(base["bb"].pk), "branch": "1",
                                                     "account": "777", "purpose": "ARRECADACAO"}, format="json").json()["id"]
    acc_fin = c.post("/api/v1/financeiro/contas/", {"plan": str(plan_fin.pk), "bank": str(base["bb"].pk), "branch": "1",
                                                    "account": "888"}, format="json").json()["id"]

    out = c.post("/api/v1/arrecadacao/contribuicoes/estimate/?kind=SERVIDOR", {"competence": "2025-10"}, format="json").json()
    assert out["criadas"] == 2
    serv = Contribution.objects.get(kind="SERVIDOR")
    pat = Contribution.objects.get(kind="PATRONAL")
    assert serv.amount == Decimal("1120.00") and pat.amount == Decimal("1920.00")  # 14% e 24% de 8.000
    assert serv.due_date == date(2025, 11, 20)

    # Baixa na conta de outro plano é recusada
    assert c.post(f"/api/v1/arrecadacao/contribuicoes/{serv.pk}/pay/?kind=SERVIDOR",
                  {"amount": "1.120,00", "date": "2025-11-18", "account": acc_fin}, format="json").status_code == 409
    r = c.post(f"/api/v1/arrecadacao/contribuicoes/{serv.pk}/pay/?kind=SERVIDOR",
               {"amount": "1.120,00", "date": "2025-11-18", "account": acc_prev, "document": "GR 1"}, format="json")
    assert r.status_code == 201, r.json()
    c.post(f"/api/v1/arrecadacao/contribuicoes/{pat.pk}/pay/?kind=PATRONAL",
           {"amount": "1000,00", "date": "2025-11-25", "account": acc_prev}, format="json")

    rec = {x["kind"]: x for x in c.get("/api/v1/arrecadacao/conciliacao/", {"competence": "2025-10"}).json()}
    assert rec["SERVIDOR"]["situacao"] == "PAGO" and rec["PATRONAL"]["situacao"] == "PARCIAL"
    assert rec["PATRONAL"]["dias_atraso"] == 5 and rec["PATRONAL"]["diferenca"] == "920.00"
    div = c.get("/api/v1/arrecadacao/divergencias/").json()
    assert len(div) == 1 and div[0]["problema"] == "Pago a menor"

    # Parcelamento: cronograma nominal
    ag = c.post("/api/v1/arrecadacao/parcelamentos/", {
        "plan": str(plan_prev.pk), "organ": str(organ.pk), "number": "01/2025", "signed_date": "2025-01-10",
        "principal": "1000.00", "installments": 3, "first_due": "2025-02-10"}, format="json")
    assert ag.status_code == 201, ag.json()
    parcels = c.get(f"/api/v1/arrecadacao/parcelamentos/{ag.json()['id']}/parcels/").json()
    assert [p["amount"] for p in parcels] == ["333.33", "333.33", "333.34"] and parcels[2]["due_date"] == "2025-04-10"
    c.post(f"/api/v1/arrecadacao/parcelamentos/{ag.json()['id']}/parcels/{parcels[0]['id']}/pay/",
           {"amount": "340,00", "date": "2025-02-10", "account": acc_prev}, format="json")
    prog = c.get(f"/api/v1/arrecadacao/parcelamentos/{ag.json()['id']}/").json()["progress"]
    assert prog["pagas"] == 1 and prog["em_atraso"] == 2

    # Conciliação bancária (OFX): crédito de 1.120,00 casa com a receita do servidor
    ofx = ("OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><BANKID>001<ACCTID>777</BANKACCTFROM>"
           "<BANKTRANLIST><STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20251119<TRNAMT>1120.00<FITID>A1<MEMO>GR 1"
           "<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20251130<TRNAMT>55.10<FITID>A2<MEMO>RENDIMENTO"
           "</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")
    up = io.BytesIO(ofx.encode())
    up.name = "extrato.ofx"
    res = c.post("/api/v1/financeiro/extrato/import/", {"account": acc_prev, "file": up}, format="multipart").json()
    assert res["lancamentos"] == 2 and res["conciliados_automaticamente"] == 1
    lines = c.get("/api/v1/financeiro/extrato/", {"account": acc_prev, "reconciled": "false"}).json()["results"]
    assert len(lines) == 1
    assert c.post(f"/api/v1/financeiro/extrato/{lines[0]['id']}/match/", {"note": ""}, format="json").status_code == 409
    rv = c.post("/api/v1/arrecadacao/receitas/", {"plan": str(plan_prev.pk), "kind": "RENDIMENTOS", "date": "2025-11-30",
                                                  "competence": "2025-11-01", "amount": "55.10", "account": acc_prev},
                format="json")
    assert rv.status_code == 201, rv.json()
    assert c.post(f"/api/v1/financeiro/extrato/{lines[0]['id']}/match/", {"revenue": rv.json()["id"]},
                  format="json").json()["reconciled"] is True

    # Integração contábil: de-para e exportação
    c.post("/api/v1/financeiro/contabil/", {"plan": str(plan_prev.pk), "source": "RECEITA", "source_code": "CONTRIBUICAO",
                                            "debit": "1.1.1.1.1.06", "credit": "4.2.1.0.0.00"}, format="json")
    prev = c.get("/api/v1/financeiro/contabil/preview/", {"plan": str(plan_prev.pk), "competence": "2025-10"}).json()
    assert len(prev["lancamentos"]) == 1 and prev["lancamentos"][0]["valor"] == "2120.00"
    exp = c.post("/api/v1/financeiro/contabil/export/", {"plan": str(plan_prev.pk), "competence": "2025-10"},
                 format="json").json()
    csv_resp = c.get(f"/api/v1/financeiro/contabil/exports/{exp['id']}/download/")
    assert csv_resp.status_code == 200 and b"2120,00" in csv_resp.content

    # Estorno de receita exige justificativa
    rid = Revenue.objects.get(document="GR 1").pk
    assert c.post(f"/api/v1/arrecadacao/receitas/{rid}/reverse/", {"justification": "x"}, format="json").status_code == 409
