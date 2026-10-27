"""
Cenários da auditoria jurídica e técnica da concessão de aposentadoria (out/2026).

Base legal conferida: Emenda à LOM 28/2025 (arts. 4º e 5º), Lei Municipal 3.965/2011 (arts. 30, 32, 62 e 63),
EC 41/2003 (art. 2º, § 1º), EC 47/2005 (art. 3º), EC 103/2019 (art. 26, § 4º), CF art. 40, § 2º.
Data-base da média e do tempo na concessão: abertura do processo (critério da PREVIBAM).
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pytest

from apps.cadastros.models import Ente, Organ, Position
from apps.concessao import services as cs
from apps.concessao.models import Concession, ConcessionStep
from apps.employment.models import EmploymentLink
from apps.institutions.services import ensure_payroll_groups, set_parameter
from apps.people.models import Person
from apps.previdencia.calculo import Averages, estimate
from apps.previdencia.management.commands.seed_rules import seed_rgps_ceiling
from apps.previdencia.models import ContributionSalary, RetirementRule
from apps.previdencia.rules import RuleEvaluator, seed_rules
from apps.previdencia.services import simulate
from apps.previdencia.tempo import PersonTime
from apps.protocolo.models import ProcessType, Sector
from tests.conftest import PASSWORD, anexar_checklist, historico

REFORM = date(2025, 6, 15)
_seq = iter(range(100000000, 999999999))


def novo_cpf() -> str:
    """CPF fictício com dígitos verificadores válidos."""
    base = [int(x) for x in str(next(_seq))]
    for n in (10, 11):
        d = (sum(a * b for a, b in zip(base, range(n, 1, -1))) * 10) % 11
        base.append(0 if d == 10 else d)
    return "".join(map(str, base))


def q(v) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@pytest.fixture
def ctx(institution, master, setores):
    seed_rules(institution, REFORM)
    set_parameter(institution, "previdencia.vigencia_reforma_local", REFORM.isoformat(), REFORM)
    seed_rgps_ceiling(institution)
    ensure_payroll_groups(institution)
    organ = Organ.objects.create(institution=institution, ente=Ente.objects.create(institution=institution, name="M"),
                                 name="Prefeitura")
    pos = Position.objects.create(institution=institution, name="Médico", cargo_type=7)
    sector = Sector.objects.create(institution=institution, name="Benefícios", code="BEN")
    sector.members.add(master, setores["beneficios"])
    ptype = ProcessType.objects.create(institution=institution, name="Aposentadoria", deadline_days=60)
    return {"inst": institution, "organ": organ, "pos": pos, "sector": sector, "ptype": ptype}


def servidor(ctx, birth, sex, start, name="Servidor"):
    p = Person.objects.create(institution=ctx["inst"], cpf=novo_cpf(), name=name, birth_date=birth, sex=sex)
    EmploymentLink.objects.create(institution=ctx["inst"], person=p, organ=ctx["organ"], position=ctx["pos"],
                                  registration=p.cpf[-6:], public_service_start=start, ente_start=start,
                                  position_start=start, career_start=start, segment="FINANCEIRO")
    return p


def abrir(ctx, client, person):
    pid = client.post("/api/v1/protocol/processes/", {"process_type": str(ctx["ptype"].pk), "sector": str(ctx["sector"].pk),
                                                      "subject": "Aposentadoria", "interested": str(person.pk),
                                                      "interested_name": "x"}, format="json").json()["id"]
    return client.post("/api/v1/concessoes/", {"kind": "APOSENTADORIA", "person": str(person.pk), "process": pid},
                       format="json").json()["id"]


def avaliar(person, code, on, eligible=None):
    pt = PersonTime(person)
    ev = RuleEvaluator(person, pt, today=on)
    rule = RetirementRule.objects.get(institution=person.institution, code=code)
    res = ev.evaluate(rule)
    return estimate(rule, ev, Averages(person, on, pt), on, eligible=eligible or res.eligible_date), res


def adriana(ctx):
    """Servidora do processo 000001/2026: ingresso em 1993, 30 anos de contribuição antes da reforma local."""
    p = servidor(ctx, date(1962, 1, 20), 1, date(1993, 6, 24), "Adriana")
    historico(ctx["inst"], p, date(1994, 7, 1), date(2026, 7, 1), "2000.00", tabela=date(2026, 9, 1))
    historico(ctx["inst"], p, date(2026, 8, 1), date(2026, 8, 1), "6000.00", tabela=date(2026, 9, 1))
    return p


# 1 ---------------------------------------------------------------- benefício mais favorável
def test_1_adriana_regra_menos_vantajosa_e_recusada(ctx, client_for, setores):
    ben = client_for(setores["beneficios"])
    cid = abrir(ctx, ben, adriana(ctx))
    comp = ben.get(f"/api/v1/concessoes/{cid}/comparativo/?validity_date=2026-09-01").json()
    assert comp["melhor"] in ("EC41_ART6", "EC47_ART3") and comp["pendencias"] == []
    best = comp["regras"][0]
    assert Decimal(best["valor"]) == Decimal("6000.00") and best["forma"].startswith("Integralidade")
    r = ben.post(f"/api/v1/concessoes/{cid}/frame/", {"rule": "CF40_IIIB", "validity_date": "2026-09-01",
                                                      "validity_class": 3}, format="json")
    assert r.status_code == 409 and "mais favorável" in r.json()["detail"] and "art. 5º, § 2º" in r.json()["detail"]


# 2 ---------------------------------------------------------------- opção do servidor justificada
def test_2_opcao_justificada_por_regra_menos_vantajosa(ctx, client_for, setores):
    ben = client_for(setores["beneficios"])
    cid = abrir(ctx, ben, adriana(ctx))
    body = {"rule": "CF40_IIIB", "validity_date": "2026-09-01", "validity_class": 3,
            "option_reason": "Servidora optou expressamente, ciente da diferença de valores.", "option_signed": True}
    assert ben.post(f"/api/v1/concessoes/{cid}/frame/", {**body, "option_signed": False},
                    format="json").status_code == 409
    r = ben.post(f"/api/v1/concessoes/{cid}/frame/", body, format="json")
    assert r.status_code == 200, r.json()
    opcao = Concession.objects.get(pk=cid).analysis["opcao"]
    assert opcao["melhor_regra"] in ("EC41_ART6", "EC47_ART3") and opcao["termo_assinado"] is True
    assert ConcessionStep.objects.filter(concession_id=cid, text__contains="Opção por regra menos vantajosa").exists()


# 3 ---------------------------------------------------------------- sem tabela de fatores
def test_3_sem_tabela_de_fatores_bloqueia(ctx, client_for, setores):
    p = servidor(ctx, date(1960, 1, 1), 1, date(1990, 1, 1))
    historico(ctx["inst"], p, date(1994, 7, 1), date(2026, 8, 1), "3000.00", fatores=False)
    avg = Averages(p, date(2026, 9, 1), PersonTime(p))
    assert any("Sem tabela de fatores" in x for x in avg.pendencias)
    ben = client_for(setores["beneficios"])
    cid = abrir(ctx, ben, p)
    assert ben.post(f"/api/v1/concessoes/{cid}/frame/", {"rule": "EC41_ART6", "validity_date": "2026-09-01",
                                                         "validity_class": 3}, format="json").status_code == 200
    r = ben.post(f"/api/v1/concessoes/{cid}/calculate/")
    assert r.status_code == 409 and "Cálculo bloqueado" in r.json()["detail"]


# 4 ---------------------------------------------------------------- média atualizada
def test_4_media_com_fatores_confere_com_calculo_manual(ctx):
    p = servidor(ctx, date(1970, 1, 1), 1, date(2000, 1, 1))
    historico(ctx["inst"], p, date(2000, 1, 1), date(2009, 12, 1), "1000.00", fator="2")
    avg = Averages(p, date(2010, 1, 1), PersonTime(p))
    assert avg.pendencias == []
    assert avg.media100 == Decimal("2000.00") and avg.media80 == Decimal("2000.00")
    assert avg.memoria["competencias"] == 120 and avg.memoria["competencias_80"] == 96


# 5 ---------------------------------------------------------------- piso do salário mínimo por competência
def test_5_competencia_abaixo_do_salario_minimo(ctx):
    p = servidor(ctx, date(1970, 1, 1), 1, date(1994, 7, 1))
    historico(ctx["inst"], p, date(1994, 7, 1), date(1994, 7, 1), "50.00")
    avg = Averages(p, date(1994, 8, 1))
    assert avg.memoria["elevadas_ao_salario_minimo"] == 1 and avg.media100 == Decimal("64.79")


# 6 ---------------------------------------------------------------- teto do RGPS nos meses de RGPS
def test_6_competencia_rgps_acima_do_teto(ctx):
    p = servidor(ctx, date(1970, 1, 1), 1, date(2010, 1, 1))
    historico(ctx["inst"], p, date(2000, 1, 1), date(2000, 1, 1), "10000.00", regime="RGPS")
    avg = Averages(p, date(2000, 2, 1))
    assert avg.memoria["limitadas_ao_teto_rgps"] == 1 and avg.media100 == Decimal("1255.32")


# 7 ---------------------------------------------------------------- lacuna no vínculo com o RPPS
def test_7_mes_sem_contribuicao_no_vinculo_e_pendencia(ctx):
    p = servidor(ctx, date(1970, 1, 1), 1, date(2000, 1, 1))
    historico(ctx["inst"], p, date(2000, 1, 1), date(2009, 12, 1), "1000.00")
    ContributionSalary.objects.filter(person=p, competence=date(2005, 3, 1)).delete()
    avg = Averages(p, date(2010, 1, 1), PersonTime(p))
    assert avg.gaps == [date(2005, 3, 1)] and any("03/2005" in x for x in avg.pendencias)


# 8 ---------------------------------------------------------------- limite antes da proporção
def proporcional(ctx):
    p = servidor(ctx, date(1960, 1, 1), 1, date(2000, 1, 1))
    historico(ctx["inst"], p, date(2000, 1, 1), date(2009, 12, 1), "8000.00", tabela=date(2026, 9, 1))
    historico(ctx["inst"], p, date(2010, 1, 1), date(2026, 8, 1), "3000.00", tabela=date(2026, 9, 1))
    return p


def test_8_proporcional_aplica_fracao_depois_do_limite(ctx):
    p = proporcional(ctx)
    est, res = avaliar(p, "CF40_IIIB", date(2026, 9, 1))
    assert res.status == "CUMPRIDA"
    frac = Decimal(est["fracao"])
    assert frac < 1
    assert Decimal(est["valor"]) == q(Decimal("3000.00") * frac)  # média (5.343,75) limitada a 3.000,00, depois × fração
    assert "limitada à remuneração" in est["forma"] and "art. 63" in est["forma"]


# 9 ---------------------------------------------------------------- simulação = concessão
def test_9_simulacao_e_concessao_tem_a_mesma_proporcao(ctx, client_for, setores):
    p = proporcional(ctx)
    cid = abrir(ctx, client_for(setores["beneficios"]), p)
    c = Concession.objects.get(pk=cid)
    c.request_date = date(2026, 9, 1)
    c.save(update_fields=["request_date"])
    comp = cs.compare_rules(c, date(2026, 10, 1))
    assert comp["data_base"] == "2026-09-01"
    sim = next(r for r in simulate(p, date(2026, 9, 1))["regras"] if r["codigo"] == "CF40_IIIB")
    conc = next(r for r in comp["regras"] if r["codigo"] == "CF40_IIIB")
    assert sim["estimativa"]["valor"] == conc["valor"]


# 10 --------------------------------------------------------------- corte da reforma local
def test_10_requisito_ate_14_06_2025_vale_e_em_15_06_2025_nao(ctx):
    rule = RetirementRule.objects.get(institution=ctx["inst"], code="CF40_IIIB")
    ok = servidor(ctx, date(1965, 6, 14), 1, date(1990, 1, 1))
    late = servidor(ctx, date(1965, 6, 15), 1, date(1990, 1, 1))
    r1 = RuleEvaluator(ok, today=date(2026, 9, 1)).evaluate(rule)
    r2 = RuleEvaluator(late, today=date(2026, 9, 1)).evaluate(rule)
    assert r1.status == "CUMPRIDA" and r1.eligible_date == date(2025, 6, 14)
    assert r2.status == "NAO_ALCANCAVEL"


# 11 --------------------------------------------------------------- compulsória antes e depois da reforma
def test_11_compulsoria_antes_e_depois_da_reforma(ctx):
    old = servidor(ctx, date(1945, 1, 1), 2, date(1990, 1, 1))
    historico(ctx["inst"], old, date(1994, 7, 1), date(2019, 12, 1), "3000.00")
    est, res = avaliar(old, "COMPULSORIA", date(2020, 1, 1))
    assert res.eligible_date == date(2020, 1, 1)
    frac = Decimal(est["fracao"])
    assert "antes da reforma" in est["forma"] and Decimal(est["valor"]) == q(Decimal("3000.00") * frac) and frac < 1

    new = servidor(ctx, date(1951, 3, 1), 2, date(2010, 1, 1))
    historico(ctx["inst"], new, date(2010, 1, 1), date(2026, 2, 1), "6000.00")
    est, res = avaliar(new, "COMPULSORIA", date(2026, 3, 1))
    frac = Decimal(est["fracao"])
    assert "art. 26, § 4º" in est["forma"] and frac < 1
    assert Decimal(est["valor"]) == q(Decimal("3600.00") * frac)  # 60% da média × tempo ÷ 20 anos


# 12 --------------------------------------------------------------- piso do benefício
def test_12_provento_abaixo_do_salario_minimo_e_elevado(ctx):
    p = servidor(ctx, date(1955, 1, 1), 1, date(2012, 1, 2))
    historico(ctx["inst"], p, date(2012, 1, 1), date(2026, 8, 1), "1000.00")
    est, res = avaliar(p, "CF40_IIIB", date(2026, 9, 1))
    assert res.status == "CUMPRIDA"
    assert est["valor"] == "1621.00" and "salário mínimo" in est["forma"]


# 13 --------------------------------------------------------------- EC 47 com idade reduzida
def test_13_ec47_reduz_idade_pelo_tempo_excedente(ctx):
    p = servidor(ctx, date(1966, 1, 1), 2, date(1984, 1, 1))
    res = RuleEvaluator(p, today=date(2026, 9, 1)).evaluate(
        RetirementRule.objects.get(institution=ctx["inst"], code="EC47_ART3"))
    assert res.status == "CUMPRIDA" and res.eligible_date < REFORM
    idade = next(r for r in res.requirements if r.key == "idade")
    assert int(idade.required.split()[0]) < 60  # 60 anos reduzidos pelos anos de contribuição acima de 35


# 14 --------------------------------------------------------------- ciência dos avisos antes do Jurídico
def test_14_envio_ao_juridico_exige_ciencia_dos_avisos(ctx, client_for, setores):
    ben = client_for(setores["beneficios"])
    cid = abrir(ctx, ben, adriana(ctx))
    assert ben.post(f"/api/v1/concessoes/{cid}/frame/", {"rule": "EC41_ART6", "validity_date": "2026-09-01",
                                                         "validity_class": 3}, format="json").status_code == 200
    calc = ben.post(f"/api/v1/concessoes/{cid}/calculate/").json()
    assert calc["total"] == "6000.00" and calc["calculation"]["data_base"] == "2026-09-01"
    assert any("art. 4º, parágrafo único" in a for a in calc["calculation"]["avisos"])
    r = ben.post(f"/api/v1/concessoes/{cid}/send/")
    assert r.status_code == 409 and "ciência" in r.json()["detail"]
    anexar_checklist(ben, cid)
    r = ben.post(f"/api/v1/concessoes/{cid}/send/", {"acknowledge_warnings": True, "password": PASSWORD},
                 format="json")
    assert r.status_code == 200 and r.json()["stage"] == "ANALISE_JURIDICA"
    assert ConcessionStep.objects.filter(concession_id=cid, action="ENVIO_JURIDICO", text__startswith="Ciente").exists()


# extra ------------------------------------------------------------ redutor da EC 41, art. 2º
def test_redutor_ec41_35_ate_2005_e_5_depois(ctx):
    p = servidor(ctx, date(1955, 6, 1), 1, date(1980, 1, 1))
    historico(ctx["inst"], p, date(1994, 7, 1), date(2006, 5, 1), "2000.00", tabela=date(2006, 6, 1))
    pt = PersonTime(p)
    ev = RuleEvaluator(p, pt, today=date(2006, 6, 1))
    rule = RetirementRule.objects.get(institution=ctx["inst"], code="EC41_ART2")
    avg = Averages(p, date(2006, 6, 1), pt)
    antes = estimate(rule, ev, avg, date(2006, 6, 1), eligible=date(2005, 1, 1))  # 49 anos: 6 × 3,5%
    depois = estimate(rule, ev, avg, date(2006, 6, 1), eligible=date(2006, 6, 1))  # 51 anos: 4 × 5%
    assert "redutor de 21.0%" in antes["forma"] and "redutor de 20%" in depois["forma"]


def test_sem_salario_minimo_cadastrado_e_pendencia(ctx):
    from apps.institutions.models import Parameter

    p = servidor(ctx, date(1970, 1, 1), 1, date(2000, 1, 1))
    historico(ctx["inst"], p, date(2000, 1, 1), date(2000, 12, 1), "1000.00")
    Parameter.objects.filter(institution=ctx["inst"], key="salario_minimo").delete()
    avg = Averages(p, date(2001, 1, 1), PersonTime(p))
    assert any("Salário mínimo não cadastrado" in x for x in avg.pendencias)
