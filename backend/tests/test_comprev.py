"""COMPREV (controle): requerimento, situação, valor com vigência, fluxo, recebimento → receita, segregação e alertas."""
from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.alerts.checks import CHECKS
from apps.cadastros.models import Bank
from apps.comprev.models import ComprevProcess, Movement
from apps.concessao.models import Benefit
from apps.financeiro.models import Revenue, TreasuryAccount
from apps.institutions.models import BenefitPlan
from apps.previdencia.models import Averbacao

from .test_fase5 import folha, person  # noqa: F401 (fixture)

URL = "/api/v1/comprev"


def _setup(inst, folha):  # noqa: F811
    p = person(inst, 300000001, "Segurada Comprev", date(1960, 3, 3))
    b = Benefit.objects.create(institution=inst, kind="APOSENTADORIA", beneficiary=p, payroll_group=folha,
                               start_date=date(2024, 1, 1), amount=Decimal("5000.00"))
    Averbacao.objects.create(institution=inst, person=p, nature="01", issuer="Empresa X", start_date=date(1985, 1, 1),
                             end_date=date(1994, 12, 31), certified_days=3650, comprev=True)
    return p, b


def test_fluxo_completo_a_receber(institution, master, consulta, client_for, folha):  # noqa: F811
    c = client_for(master)
    inst = institution
    p, b = _setup(inst, folha)
    assert CHECKS["COMPREV"](inst)  # benefício com tempo averbado sem requerimento
    assert c.get(f"{URL}/processos/potencial/").json()[0]["person"] == str(p.pk)
    op = c.get(f"{URL}/processos/opcoes/?pessoa={p.pk}").json()
    assert op["beneficios"][0]["id"] == str(b.pk) and op["averbacoes"][0]["days"] == 3650

    body = {"direction": "RECEBER", "counterpart_kind": "RGPS", "person": str(p.pk), "benefit": str(b.pk),
            "requested_at": "2025-03-10", "rmi": "5000.00", "origin_days": 3650, "total_days": 12775}
    assert client_for(consulta).post(f"{URL}/processos/", body, format="json").status_code == 403
    r = c.post(f"{URL}/processos/", body, format="json")
    assert r.status_code == 201, r.json()
    d = r.json()
    pid = d["id"]
    # plano vem da folha do benefício; nome do INSS preenchido; pro rata sugerido = 5000 × 3650 / 12775
    assert d["plan"] == str(folha.plan_id) and "INSS" in d["counterpart_name"]
    assert d["valor_sugerido"] == "1428.57" and d["benefit_kind"] == "APOSENTADORIA"
    assert c.get(f"{URL}/processos/potencial/").json() == []

    st = lambda **kw: c.post(f"{URL}/processos/{pid}/situacao/", kw, format="json")  # noqa: E731
    assert st(status="ENVIADO", date="2025-03-10").status_code == 409  # sem nº do requerimento
    assert c.patch(f"{URL}/processos/{pid}/", {"request_number": "RQ-2025-001"}, format="json").status_code == 200
    assert st(status="DEFERIDO", date="2025-03-10").status_code == 409  # não pula etapa
    assert st(status="ENVIADO", date="2025-03-10").status_code == 200
    assert st(status="EXIGENCIA", date="2025-04-01", note="Juntar a CTC do INSS",
              requirement_due="2025-05-01").status_code == 200
    assert st(status="ENVIADO", date="2025-04-20", note="Exigência cumprida").status_code == 200
    r = st(status="DEFERIDO", date="2025-06-01", comp_start="2025-06", amount="1400.00", backlog="7000.00")
    assert r.status_code == 200, r.json()
    assert r.json()["valor_vigente"] == "1400.00"
    # Depois de deferido, os dados do requerimento não mudam
    assert c.patch(f"{URL}/processos/{pid}/", {"rmi": "9999"}, format="json").status_code == 400

    # Reajuste: nova vigência (não sobrescreve)
    assert c.post(f"{URL}/processos/{pid}/valor/", {"valid_from": "2025-06", "amount": "1500", "reason": "Reajuste anual"},
                  format="json").status_code == 409
    assert c.post(f"{URL}/processos/{pid}/valor/", {"valid_from": "2026-01", "amount": "1450.00",
                                                     "reason": "Reajuste anual 2026"}, format="json").status_code == 200

    mv = f"{URL}/movimentos/?sentido=RECEBER"
    r = c.post(mv, {"process": pid, "kind": "MENSAL", "competence": "2025-06", "amount": "1400.00",
                    "date": "2025-07-10", "document": "Aviso 1"}, format="json")
    assert r.status_code == 201, r.json()
    assert c.post(mv, {"process": pid, "kind": "MENSAL", "competence": "2025-06", "amount": "1400.00",
                       "date": "2025-07-10"}, format="json").status_code == 409  # duplicado
    assert c.post(mv, {"process": pid, "kind": "MENSAL", "competence": "2025-05", "amount": "1400.00",
                       "date": "2025-07-10"}, format="json").status_code == 409  # antes do início
    # Pagamentos: o requerimento A RECEBER não aparece
    assert c.post(f"{URL}/movimentos/?sentido=PAGAR", {"process": pid, "competence": "2025-07", "amount": "1",
                                                        "date": "2025-08-10"}, format="json").status_code == 400
    # Lote do mês com o valor previsto (julho) e atrasados
    r = c.post(f"{URL}/movimentos/lote/?sentido=RECEBER", {"competence": "2025-07", "date": "2025-08-10",
                                                            "document": "Aviso 2",
                                                            "items": [{"process": pid, "amount": "1400.00"}]},
               format="json")
    assert r.status_code == 201 and r.json()["lancados"] == 1
    assert c.post(mv, {"process": pid, "kind": "ATRASADOS", "competence": "2025-07", "amount": "3500.00",
                       "date": "2025-08-10"}, format="json").status_code == 201

    f = c.get(f"{URL}/fluxo/?competencia=2025-07").json()
    assert f["totais"]["RECEBER"]["previsto"] == "1400.00" and f["totais"]["RECEBER"]["realizado"] == "1400.00"
    assert f["totais"]["RECEBER"]["atrasados"] == "3500.00"
    assert c.get(f"{URL}/fluxo/?competencia=2026-01").json()["linhas"][0]["expected"] == "1450.00"

    ind = c.get(f"{URL}/indicadores/").json()
    assert ind["por_situacao"]["RECEBER"]["DEFERIDO"] == 1
    assert ind["atrasados"]["RECEBER"]["saldo"] == "3500.00"

    # Recebimento → receita do Financeiro; conta de outro plano é recusada (segregação)
    ids = [m.pk for m in Movement.objects.filter(process_id=pid, competence=date(2025, 7, 1))]
    other = BenefitPlan.objects.exclude(pk=folha.plan_id).filter(institution=inst).first()
    bank = Bank.objects.create(institution=inst, code="999", name="Banco")
    wrong = TreasuryAccount.objects.create(institution=inst, plan=other, bank=bank, branch="1", account="1")
    right = TreasuryAccount.objects.create(institution=inst, plan=folha.plan, bank=bank, branch="1", account="2")
    rv = f"{URL}/movimentos/receita/?sentido=RECEBER"
    assert c.post(rv, {"ids": [str(i) for i in ids], "account": str(wrong.pk)}, format="json").status_code == 409
    r = c.post(rv, {"ids": [str(i) for i in ids], "account": str(right.pk)}, format="json")
    assert r.status_code == 201, r.json()
    rev = Revenue.objects.get(pk=r.json()["receita"])
    assert rev.kind == "COMPREV" and rev.amount == Decimal("4900.00") and rev.plan_id == folha.plan_id
    # Estorno: bloqueado enquanto a receita estiver ativa
    m = Movement.objects.filter(process_id=pid, kind="ATRASADOS").first()
    assert c.post(f"{URL}/movimentos/{m.pk}/estornar/?sentido=RECEBER", {"reason": "Lançado em duplicidade"},
                  format="json").status_code == 409

    # Cessação com motivo
    assert st(status="CESSADO", date=timezone.localdate().isoformat(), note="curto").status_code == 409
    assert st(status="CESSADO", date=timezone.localdate().isoformat(), note="Óbito do aposentado",
              ended_at="2026-02").status_code == 200
    proc = ComprevProcess.objects.get(pk=pid)
    assert proc.ended_at == date(2026, 2, 1) and proc.events.count() == 5


def test_a_pagar_exige_outro_regime(institution, master, client_for, folha):  # noqa: F811
    c = client_for(master)
    p = person(institution, 300000002, "Ex-servidor", date(1958, 1, 1))
    plan = folha.plan
    body = {"direction": "PAGAR", "counterpart_kind": "RPPS", "counterpart_name": "RPPS de Outra Cidade",
            "person": str(p.pk), "plan": str(plan.pk), "benefit_kind": "APOSENTADORIA", "requested_at": "2025-01-05"}
    assert c.post(f"{URL}/processos/", body, format="json").status_code == 409  # RPPS sem CNPJ
    r = c.post(f"{URL}/processos/", {**body, "counterpart_cnpj": "11.222.333/0001-81"}, format="json")
    assert r.status_code == 201, r.json()
    assert r.json()["counterpart_cnpj"] == "11222333000181"
    assert c.get(f"{URL}/processos/?sentido=RECEBER").json()["count"] == 0
    assert c.get(f"{URL}/movimentos/?sentido=PAGAR").status_code == 200
    assert c.get(f"{URL}/movimentos/").status_code == 400  # sentido obrigatório
