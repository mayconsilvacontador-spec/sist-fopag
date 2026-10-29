"""
Regras do fluxo de concessão, cálculo de pensão e operações sobre benefícios.

Pensão por morte:
- Óbito a partir da vigência local da reforma (Barra Mansa: 15/06/2025 — Emenda à LOM 28/2025, art. 3º):
  EC 103, art. 23: cota familiar de 50% + 10% por dependente (até 100%) sobre a aposentadoria recebida ou
  a que teria direito por incapacidade permanente na data do óbito; havendo dependente inválido ou com
  deficiência, 100% até o teto do RGPS + cota familiar sobre o excedente; cotas NÃO reversíveis.
- Óbito anterior: art. 40, § 7º, CF (EC 41): totalidade até o teto do RGPS + 70% do excedente.
- Duração da cota do cônjuge/companheiro: art. 77, § 2º, V, "c", da Lei 8.213/1991 (idades da Portaria
  ME 424/2020), aplicável por remissão do art. 23 da EC 103; filhos e irmãos até 21 anos, salvo invalidez.
"""
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from .models import (
    STAGE_ORDER, Benefit, BenefitEvent, BenefitEventKind, BenefitKind, BenefitStatus, Concession, Modality, Parcel,
    PensionQuota, QuotaDuration, Stage, ValidityClass,
)

CENT = Decimal("0.01")
REFORM_PARAM = "previdencia.vigencia_reforma_local"
TETO_PARAM = "rgps.teto"


def _q(v) -> Decimal:
    return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP)


def _money(v) -> Decimal | None:
    """Aceita '5.300,00', '5300,00' ou '5300.00'. Inválido -> None."""
    if v is None:
        return None
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _brl(v) -> str:
    return "R$ " + f"{Decimal(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def _require(c: Concession, *stages):
    if c.stage not in stages:
        allowed = ", ".join(Stage(s).label.lower() for s in stages)
        raise BusinessRuleError(f"Operação não permitida na etapa '{c.get_stage_display()}'. Etapa exigida: {allowed}.")


def reform_date(institution) -> date | None:
    from apps.institutions.services import get_parameter

    v = get_parameter(institution, REFORM_PARAM)
    return date.fromisoformat(v) if v else None


def rgps_ceiling(institution, on: date) -> tuple[Decimal, list[str]]:
    from apps.institutions.models import Parameter

    p = (Parameter.objects.filter(institution=institution, key=TETO_PARAM, valid_from__lte=on)
         .exclude(valid_to__lt=on).order_by("-valid_from").first())
    if p is None:
        raise BusinessRuleError("Cadastre o teto do RGPS (parâmetro 'rgps.teto') em Administração › Parâmetros.")
    warn = [] if p.valid_from.year == on.year else [
        f"Teto do RGPS de {on.year} não cadastrado — usado o de {p.valid_from.year} (R$ {p.value})."]
    return Decimal(str(p.value)), warn


MODALITY_BY_RULE = {
    "CF40_IIIB": Modality.IDADE, "COMPULSORIA": Modality.COMPULSORIA, "EC103_ART21": Modality.ESPECIAL_INSALUBRE,
    "EC103_ART10_ESPECIAL": Modality.ESPECIAL_INSALUBRE,
}


def _log(c: Concession, what: str, **extra):
    mod = {"APOSENTADORIA": "aposentadoria", "PENSAO": "pensao", "REVISAO": "revisao"}.get(c.kind, "processos")
    log_event("UPDATE", module=f"concessao.{mod}",
              obj=c, object_repr=f"Concessão — {what}", extra=extra or None)


# ---------------------------------------------------------------------------- abertura
@transaction.atomic
def open_concession(institution, *, process, kind, person, link=None, request_date=None, benefit=None) -> Concession:
    from apps.employment.models import EmploymentLink

    if process.institution_id != institution.pk or (person is not None and person.institution_id != institution.pk):
        raise BusinessRuleError("Processo ou pessoa de outra instituição.")
    if process.status not in ("EM_TRAMITACAO", "SOBRESTADO"):
        raise BusinessRuleError("O processo do Protocolo está encerrado.")
    if Concession.objects.filter(process=process).exclude(stage__in=[Stage.INDEFERIDO, Stage.DESISTENCIA]).exists():
        raise BusinessRuleError("Já existe concessão em andamento para este processo.")
    if kind == "REVISAO":
        if benefit is None or benefit.institution_id != institution.pk:
            raise BusinessRuleError("Escolha o benefício a revisar.")
        if benefit.status == BenefitStatus.CESSADO:
            raise BusinessRuleError("Benefício cessado não pode ser revisto.")
        if Concession.objects.filter(revised_benefit=benefit).exclude(stage__in=[Stage.IMPLANTADO, Stage.INDEFERIDO, Stage.ANULADO]).exists():
            raise BusinessRuleError("Já existe revisão em andamento para este benefício.")
        c = Concession.objects.create(institution=institution, process=process, kind=kind, person=benefit.beneficiary,
                                      revised_benefit=benefit, link=benefit.concession.link if benefit.concession_id else None,
                                      request_date=request_date or process.opened_date, legal_basis=benefit.legal_basis,
                                      paridade=benefit.paridade, integralidade=benefit.integralidade, modality=benefit.modality)
        return c
    if link is None:
        link = (EmploymentLink.objects.filter(person=person, regime="ESTATUTARIO").order_by("-position_start").first())
    if kind == BenefitKind.APOSENTADORIA:
        if link is None or link.status != "ATIVO":
            raise BusinessRuleError("A aposentadoria exige vínculo estatutário ativo do servidor.")
        if Benefit.objects.filter(beneficiary=person, kind=BenefitKind.APOSENTADORIA, status="ATIVO",
                                  concession__link=link).exists():
            raise BusinessRuleError("O servidor já tem aposentadoria ativa por este vínculo.")
    else:
        if not person.death_date:
            raise BusinessRuleError("Informe a data do óbito do instituidor no cadastro antes de abrir a pensão.")
    c = Concession.objects.create(institution=institution, process=process, kind=kind, person=person, link=link,
                                  request_date=request_date or process.opened_date,
                                  death_date=person.death_date if kind == BenefitKind.PENSAO else None)
    return c


# ---------------------------------------------------------------------------- data-base e comparativo
def default_base_date(c: Concession, validity_date: date) -> date:
    """Data-base da média e do tempo: abertura do processo (critério da PREVIBAM), sem passar da data de validade."""
    req = c.request_date or c.process.opened_date
    return min(req, validity_date) if req else validity_date


def base_date(c: Concession) -> date:
    v = (c.analysis or {}).get("data_base_calculo")
    return date.fromisoformat(v) if v else default_base_date(c, c.validity_date)


def remuneration_at(c: Concession, on: date):
    """Remuneração do cargo efetivo: última remuneração de contribuição ao RPPS até a data-base."""
    from apps.previdencia.models import ContributionSalary

    s = (ContributionSalary.objects.filter(person=c.person, regime="RPPS", competence__lte=on)
         .order_by("-competence").first())
    if s is not None:
        return s.amount, s.competence
    if c.link and c.link.base_salary:
        return c.link.base_salary, None
    return None, None


def compare_rules(c: Concession, validity_date: date, base: date | None = None) -> dict:
    """
    Todas as regras cumpridas até a data de validade, com o valor de cada uma na data-base — para que o servidor
    receba o benefício mais favorável (Emenda à LOM 28/2025, art. 5º, § 2º).
    """
    from apps.previdencia.calculo import Averages, estimate
    from apps.previdencia.models import RetirementRule
    from apps.previdencia.rules import RuleEvaluator
    from apps.previdencia.services import is_teacher
    from apps.previdencia.tempo import PersonTime

    base = base or default_base_date(c, validity_date)
    pt = PersonTime(c.person, reference_link=c.link)
    ev = RuleEvaluator(c.person, pt, today=validity_date)
    avg = Averages(c.person, base, pt)
    remun, _ = remuneration_at(c, base)
    teacher = is_teacher(pt)
    rows = []
    for rule in RetirementRule.objects.filter(institution=c.institution, active=True):
        if rule.for_teacher and not teacher:
            continue
        res = ev.evaluate(rule)
        if not res.applies or res.eligible_date is None or res.eligible_date > validity_date:
            continue
        est = estimate(rule, ev, avg, base, eligible=res.eligible_date, remuneration=remun)
        rows.append({"codigo": rule.code, "nome": rule.name, "fundamento": rule.legal_basis, "grupo": rule.group,
                     "data_cumprimento": res.eligible_date.isoformat(), "valor": est["valor"], "forma": est["forma"],
                     "paridade": rule.paridade, "avisos": est["avisos"]})
    rows.sort(key=lambda r: Decimal(r["valor"]) if r["valor"] else Decimal(-1), reverse=True)
    best = rows[0] if rows and rows[0]["valor"] else None
    return {"data_validade": validity_date.isoformat(), "data_base": base.isoformat(), "regras": rows,
            "melhor": best["codigo"] if best else None, "pendencias": avg.pendencias, "avisos": avg.warnings,
            "observacao": "Valores estimados com os dados cadastrados; com pendências, a ordem pode mudar."}


# ---------------------------------------------------------------------------- enquadramento
@transaction.atomic
def frame_retirement(c: Concession, *, rule=None, modality=None, validity_date: date, validity_class: int,
                     validity_legal_basis="", invalidity_cause=None, cid="", medical_report_date=None,
                     judicial=False, judicial_process="", local_legal_basis="", user=None,
                     base_date_override: date | None = None, base_date_reason="",
                     option_reason="", option_signed=False) -> Concession:
    from apps.previdencia.rules import RuleEvaluator
    from apps.previdencia.services import time_report

    _require(c, Stage.INSTRUCAO, Stage.ENQUADRADO, Stage.CALCULADO)
    if c.kind != BenefitKind.APOSENTADORIA:
        raise BusinessRuleError("Enquadramento por regra é só para aposentadoria.")
    is_invalidity = modality == Modality.INCAPACIDADE
    if not is_invalidity and rule is None:
        raise BusinessRuleError("Escolha a regra de aposentadoria.")
    if is_invalidity and not (medical_report_date and invalidity_cause):
        raise BusinessRuleError("Aposentadoria por incapacidade exige data do laudo médico e causa.")
    if validity_date < c.person.birth_date:
        raise BusinessRuleError("Data de validade inválida.")

    base = default_base_date(c, validity_date)
    if base_date_override and base_date_override != base:
        if base_date_override > validity_date:
            raise BusinessRuleError("A data-base do cálculo não pode ser posterior à data de validade.")
        if len((base_date_reason or "").strip()) < 20:
            raise BusinessRuleError("Justifique a data-base diferente da abertura do processo (mínimo de 20 caracteres).")
        base = base_date_override
    analysis = {"data_validade": validity_date.isoformat(), "tempo": time_report(c.person, validity_date)["totais"],
                "data_base_calculo": base.isoformat(),
                "data_base_motivo": (base_date_reason or "").strip() if base_date_override else
                "Abertura do processo (critério da PREVIBAM)"}
    option_text = ""
    if rule is not None:
        ev = RuleEvaluator(c.person, today=validity_date)
        res = ev.evaluate(rule)
        if not res.applies:
            raise BusinessRuleError("A regra não se aplica a este servidor: " + " ".join(res.notes))
        ref = f"{res.reference_date:%d/%m/%Y}" if res.reference_date else "na data de validade"
        if res.eligible_date is None or res.eligible_date > validity_date:
            falta = [f"{q.label}: exigido {q.required}, apurado em {ref}: {q.achieved}"
                     for q in res.requirements if not q.met]
            raise BusinessRuleError("Na data de validade o servidor NÃO cumpre os requisitos da regra. " + "; ".join(falta))
        comp = compare_rules(c, validity_date, base)
        chosen = next((r for r in comp["regras"] if r["codigo"] == rule.code), None)
        best = next((r for r in comp["regras"] if r["codigo"] == comp["melhor"]), None)
        less = best is not None and best["codigo"] != rule.code and (
            not chosen or not chosen["valor"] or Decimal(best["valor"]) > Decimal(chosen["valor"]))
        if less:
            if len((option_reason or "").strip()) < 30 or not option_signed:
                raise BusinessRuleError(
                    f"Existe regra mais favorável: {best['nome']} ({best['fundamento']}), estimada em "
                    f"{_brl(best['valor'])}" + (f", contra {_brl(chosen['valor'])}" if chosen and chosen["valor"] else "")
                    + ". O servidor tem direito ao benefício mais favorável (direito adquirido — conferir a legislação do RPPS). "
                    "Para enquadrar em regra menos vantajosa, registre a justificativa (mínimo de 30 caracteres) e "
                    "confirme que o termo de opção assinado pelo servidor está juntado ao processo.")
            option_text = (f"Opção por regra menos vantajosa. Mais favorável: {best['nome']} (R$ {best['valor']}). "
                           f"Justificativa: {option_reason.strip()} — termo de opção do servidor juntado.")
            analysis["opcao"] = {"melhor_regra": best["codigo"], "melhor_valor": best["valor"],
                                 "valor_escolhida": chosen["valor"] if chosen else None,
                                 "justificativa": option_reason.strip(), "termo_assinado": True}
        analysis["comparativo"] = comp
        analysis["regra"] = {"codigo": rule.code, "nome": rule.name, "fundamento": rule.legal_basis,
                             "data_cumprimento": res.eligible_date.isoformat(),
                             "data_referencia": res.reference_date.isoformat() if res.reference_date else None,
                             "requisitos": [{"descricao": q.label, "exigido": q.required, "atual": q.achieved}
                                            for q in res.requirements]}
        modality = modality or MODALITY_BY_RULE.get(rule.code) or (
            Modality.PROFESSOR if rule.for_teacher else Modality.TEMPO_CONTRIBUICAO)
        c.legal_basis = rule.legal_basis
    else:
        c.legal_basis = c.legal_basis or "Art. 40, § 1º, I, CF (aposentadoria por incapacidade permanente)"
    c.rule, c.modality = rule, modality
    c.validity_date, c.validity_class, c.validity_legal_basis = validity_date, validity_class, validity_legal_basis
    c.invalidity_cause, c.cid, c.medical_report_date = invalidity_cause, cid, medical_report_date
    c.judicial, c.judicial_process = judicial, judicial_process
    if not local_legal_basis:  # norma da regra; senão, a legislação local vigente cadastrada para aposentadoria
        from apps.previdencia.legislacao import main_norm

        norm = (rule.norm if rule is not None and rule.norm_id else None) or main_norm(c.institution)
        local_legal_basis = norm.citation if norm else ""
    c.local_legal_basis = local_legal_basis
    c.analysis, c.stage = analysis, Stage.ENQUADRADO
    c.save()
    _log(c, "enquadramento", regra=rule.code if rule else "INCAPACIDADE", data_validade=validity_date.isoformat(),
         data_base=base.isoformat(), opcao=bool(option_text))
    _instruction_step(c, user, "enquadramento" + (f" — {option_text}" if option_text else ""))
    return c


# ---------------------------------------------------------------------------- cálculo
@transaction.atomic
def calculate(c: Concession, user=None) -> Concession:
    _require(c, Stage.ENQUADRADO, Stage.CALCULADO)
    if c.kind == "REVISAO":
        raise BusinessRuleError("Na revisão, informe o novo valor (não há cálculo automático).")
    c.parcels.all().delete()
    c.quotas.all().delete()
    if c.kind == BenefitKind.APOSENTADORIA:
        _calc_retirement(c)
    else:
        _calc_pension(c)
    c.stage = Stage.CALCULADO
    c.save()
    _log(c, "cálculo", total=str(c.total))
    _instruction_step(c, user, "cálculo")
    return c


def _calc_retirement(c: Concession):
    """
    Proventos com média e tempo apurados na DATA-BASE (abertura do processo, salvo justificativa no enquadramento).
    Pendências da média (sem tabela de fatores, competências sem fator, salário mínimo/teto não cadastrados,
    lacunas no vínculo) BLOQUEIAM o cálculo — nada de valores nominais ou presumidos.
    """
    from apps.previdencia.calculo import Averages, estimate, salario_minimo
    from apps.previdencia.rules import RuleEvaluator
    from apps.previdencia.tempo import DAYS_YEAR, PersonTime

    base = base_date(c)
    pt = PersonTime(c.person, reference_link=c.link)
    avg = Averages(c.person, base, pt)
    if avg.pendencias:
        raise BusinessRuleError("Cálculo bloqueado — resolva antes: " + " | ".join(avg.pendencias))
    ev = RuleEvaluator(c.person, pt, today=c.validity_date)
    remun, comp = remuneration_at(c, base)
    warnings = list(avg.warnings)
    fraction = None
    if remun is not None:
        Parcel.objects.create(institution=c.institution, concession=c, kind="REMUNERACAO",
                              name="Remuneração de contribuição", correlation="Vencimento", amount=remun,
                              legal_basis="Última remuneração até a data-base do cálculo")
    if c.modality == Modality.INCAPACIDADE:
        whole = Decimal(ev.summary(base).contribuicao // DAYS_YEAR)
        if c.invalidity_cause in (1, 2):
            pct, how = Decimal(100), "100% da média (acidente em serviço / moléstia profissional — EC 103, art. 26, § 3º, II)"
        else:
            pct = min(Decimal(100), 60 + 2 * max(Decimal(0), whole - 20))
            how = f"{pct}% da média (60% + 2% por ano acima de 20 — EC 103, art. 26, § 2º)"
        value = _q(avg.media100 * pct / 100) if avg.media100 else None
        if value is not None and remun is not None and value > remun:
            value, how = remun, how + " — limitada à remuneração do cargo efetivo"
        floor = salario_minimo(c.institution, base)
        if value is not None and floor and value < floor:
            value, how = floor, how + " — elevada ao salário mínimo (CF, art. 40, § 2º)"
        integral = paridade = False
    else:
        regra = (c.analysis or {}).get("regra") or {}
        eligible = date.fromisoformat(regra["data_cumprimento"]) if regra.get("data_cumprimento") else None
        est = estimate(c.rule, ev, avg, base, eligible=eligible, remuneration=remun)
        value = Decimal(est["valor"]) if est["valor"] else None
        how, fraction = est["forma"], est.get("fracao")
        warnings += est["avisos"]
        integral = how.startswith("Integralidade")
        paridade = integral
        if integral:
            warnings.append("Integralidade calculada pela última remuneração de contribuição. Confira a composição da "
                            "remuneração do cargo efetivo conforme a legislação do RPPS (em regra: vantagens do cargo, "
                            "adicionais de caráter individual e médias das parcelas variáveis).")
    if value is None:
        raise BusinessRuleError("Não foi possível calcular: cadastre os salários de contribuição (Histórico "
                                "contributivo) ou a remuneração do vínculo.")
    name = "Proventos integrais" if integral else "Parcela única (MÉDIA)"
    Parcel.objects.create(institution=c.institution, concession=c, kind="PROVENTO", name=name, amount=value,
                          correlation="Vencimento" if integral else "Média", legal_basis=(c.legal_basis or "")[:100],
                          proportionality=Decimal(fraction) if fraction else None)
    c.integralidade, c.paridade, c.total = integral, paridade, value
    c.calculation = {"forma": how, "avisos": list(dict.fromkeys(warnings)), "media100": str(avg.media100 or ""),
                     "media80": str(avg.media80 or ""), "competencias": avg.months, "ultima_remuneracao": str(remun or ""),
                     "competencia_ultima_remuneracao": comp.strftime("%m/%Y") if comp else "",
                     "data_base": base.isoformat(), "fracao": fraction or "", "memoria": avg.memoria}


SPOUSE_TABLE = [(22, 3), (28, 6), (31, 10), (42, 15), (45, 20)]  # idade < limite -> anos de duração


def _quota_duration(dep, relation: int, death: date) -> tuple[str, date | None, str]:
    from apps.previdencia.rules import age_years

    if relation == 1:
        age = age_years(dep.birth_date, death)
        if dep.is_invalid or dep.has_disability:
            return QuotaDuration.VITALICIA, None, "Cônjuge inválido ou com deficiência — enquanto durar a condição"
        for limit, years in SPOUSE_TABLE:
            if age < limit:
                return (QuotaDuration.TEMPORARIA, _add_years(death, years),
                        f"Cônjuge com {age} anos no óbito: {years} anos (Lei 8.213/1991, art. 77, § 2º, V, 'c')")
        return QuotaDuration.VITALICIA, None, f"Cônjuge com {age} anos no óbito: vitalícia (45 anos ou mais)"
    if relation in (2, 5):
        if dep.is_invalid or dep.has_disability:
            return QuotaDuration.VITALICIA, None, "Inválido ou com deficiência — enquanto durar a condição"
        return QuotaDuration.TEMPORARIA, _add_years(dep.birth_date, 21), "Até completar 21 anos"
    return QuotaDuration.VITALICIA, None, "Enquanto mantida a dependência econômica"


RELATION_BY_DEPENDENCY = {1: 1, 2: 1, 12: 1, 3: 2, 6: 2, 10: 2, 11: 2, 4: 3, 7: 3, 5: 4, 8: 5, 9: 5}


def _calc_pension(c: Concession):
    from django.db.models import Q

    from apps.people.models import Dependency
    from apps.previdencia.calculo import Averages
    from apps.previdencia.rules import RuleEvaluator
    from apps.previdencia.tempo import DAYS_YEAR

    death = c.death_date or c.person.death_date
    if not death:
        raise BusinessRuleError("Data do óbito não informada.")
    deps = list(Dependency.objects.filter(holder=c.person, pension_eligible=True, start_date__lte=death)
                .filter(Q(end_date__isnull=True) | Q(end_date__gte=death)).select_related("dependent"))
    if not deps:
        raise BusinessRuleError("O instituidor não tem dependentes habilitados à pensão na data do óbito "
                                "(Pasta do Servidor › Dependentes).")
    warnings = []
    # Base: aposentadoria recebida ou a que teria direito por incapacidade na data do óbito
    retired = Benefit.objects.filter(beneficiary=c.person, kind=BenefitKind.APOSENTADORIA,
                                     status__in=[BenefitStatus.ATIVO, BenefitStatus.SUSPENSO]).first()
    if retired is not None:
        base, base_how = retired.amount, "Aposentadoria recebida pelo instituidor"
        c.instituidor_benefit = retired
    else:
        avg = Averages(c.person, death)
        if avg.media100 is None:
            remun, _ = _last_remuneration_at(c, death)
            if remun is None:
                raise BusinessRuleError("Sem salários de contribuição nem remuneração para calcular a base da pensão.")
            base, base_how = remun, "Remuneração do servidor (sem histórico contributivo para a média)"
            warnings.append("Base calculada pela remuneração: cadastre o histórico contributivo para a média.")
        else:
            years = Decimal(RuleEvaluator(c.person, today=death).summary(death).contribuicao) / DAYS_YEAR
            pct = min(Decimal(100), 60 + 2 * max(Decimal(0), years.to_integral_value(rounding="ROUND_FLOOR") - 20))
            base = _q(avg.media100 * pct / 100)
            base_how = f"Aposentadoria por incapacidade a que teria direito: {pct}% da média"
        warnings += avg.warnings + avg.pendencias

    ceiling, w = rgps_ceiling(c.institution, death)
    warnings += w
    reform = reform_date(c.institution)
    n = len(deps)
    invalid = any(d.dependent.is_invalid or d.dependent.has_disability for d in deps)
    if reform and death >= reform:
        cota = min(Decimal(100), Decimal(50) + Decimal(10) * n)
        if invalid:
            total = min(base, ceiling) + max(Decimal(0), base - ceiling) * cota / 100
            how = (f"EC 103, art. 23, § 2º (dependente inválido/com deficiência): 100% até o teto do RGPS "
                   f"(R$ {ceiling}) + {cota}% do excedente")
        else:
            total = base * cota / 100
            how = f"EC 103, art. 23: cota familiar de {cota}% (50% + 10% × {n} dependente(s))"
        reversible = False
    else:
        total = min(base, ceiling) + max(Decimal(0), base - ceiling) * Decimal("0.7")
        how = f"Art. 40, § 7º, CF (EC 41): até o teto do RGPS (R$ {ceiling}) + 70% do excedente"
        reversible = True
    total = _q(total)
    share = _q(total / n)
    for d in deps:
        relation = RELATION_BY_DEPENDENCY.get(d.kind, 6)
        duration, end, basis = _quota_duration(d.dependent, relation, death)
        PensionQuota.objects.create(institution=c.institution, concession=c, dependent=d.dependent, relation=relation,
                                    percent=(Decimal(100) / n).quantize(Decimal("0.001")), amount=share,
                                    duration=duration, end_date=end, duration_basis=basis)
    c.total, c.integralidade, c.paridade = total, False, False
    c.validity_date = c.validity_date or death
    c.legal_basis = c.legal_basis or ("Art. 23 da EC 103/2019" if not reversible
                                      else "Art. 40, § 7º, da Constituição Federal (redação da EC 41/2003)")
    c.calculation = {"base": str(base), "base_forma": base_how, "forma": how, "teto_rgps": str(ceiling),
                     "dependentes": n, "cotas_reversiveis": reversible, "avisos": warnings,
                     "observacao": "Duração das cotas do cônjuge pressupõe 18 contribuições e 2 anos de casamento/"
                                   "união estável; caso contrário, 4 meses (Lei 8.213, art. 77, § 2º, V, 'b')."}


def _last_remuneration_at(c: Concession, on: date):
    from apps.previdencia.models import ContributionSalary

    s = (ContributionSalary.objects.filter(person=c.person, regime="RPPS", competence__lte=on)
         .order_by("-competence").first())
    if s:
        return s.amount, s.competence
    if c.link and c.link.base_salary:
        return c.link.base_salary, None
    return None, None


def update_parcels(c: Concession, parcels: list[dict], user=None) -> Concession:
    """Substitui as parcelas (ajuste manual do analista) e recalcula o total dos proventos."""
    _require(c, Stage.CALCULADO)
    if c.kind != BenefitKind.APOSENTADORIA:
        raise BusinessRuleError("Na pensão, ajuste as cotas.")
    with transaction.atomic():
        c.parcels.all().delete()
        for p in parcels:
            Parcel.objects.create(institution=c.institution, concession=c, kind=p.get("kind", "PROVENTO"),
                                  name=p["name"][:60], legal_basis=p.get("legal_basis", "")[:100],
                                  correlation=p.get("correlation", "")[:40], percent=p.get("percent") or None,
                                  proportionality=p.get("proportionality") or None, amount=_q(_money(p["amount"]) or 0),
                                  in_reference=p.get("in_reference", True))
        total = sum((x.amount for x in c.parcels.filter(kind="PROVENTO")), Decimal(0))
        if total <= 0:
            raise BusinessRuleError("Informe ao menos uma parcela de proventos com valor.")
        c.total = _q(total)
        c.save()
    _log(c, "ajuste de parcelas", total=str(c.total))
    _instruction_step(c, user, "ajuste de parcelas")
    return c


# ---------------------------------------------------------------------------- instrução (trilha) e revisão
def _instruction_step(c: Concession, user, what: str):
    """Registra quem instruiu (base da segregação de funções). As decisões ficam em workflow.py."""
    if user is None:
        return
    from .models import ConcessionStep, StepAction

    ConcessionStep.objects.create(institution=c.institution, concession=c, action=StepAction.INSTRUCAO, role="INSTRUCAO",
                                  stage_from=c.stage, stage_to=c.stage, user=user, text=what)


@transaction.atomic
def set_revision(c: Concession, *, amount, validity_date: date, reason: str, user=None) -> Concession:
    """Instrução da revisão: novo valor proposto e data de efeito (decisão segue Jurídico → Presidência)."""
    _require(c, Stage.INSTRUCAO, Stage.ENQUADRADO, Stage.CALCULADO)
    if c.kind != "REVISAO":
        raise BusinessRuleError("Operação exclusiva da revisão de benefício.")
    value = _money(amount)
    if value is None or value <= 0:
        raise BusinessRuleError("Informe o novo valor (ex.: 5.300,00).")
    if not reason or len(reason.strip()) < 20:
        raise BusinessRuleError("Descreva o motivo da revisão (mínimo de 20 caracteres).")
    if validity_date < c.revised_benefit.start_date:
        raise BusinessRuleError("A data de efeito não pode ser anterior ao início do benefício.")
    c.parcels.all().delete()
    Parcel.objects.create(institution=c.institution, concession=c, kind="PROVENTO", name="Valor revisto",
                          amount=_q(value), legal_basis=(c.legal_basis or "")[:100])
    c.total, c.validity_date, c.revision_reason = _q(value), validity_date, reason.strip()
    c.validity_class = ValidityClass.OUTRA
    c.calculation = {"forma": "Revisão", "valor_anterior": str(c.revised_benefit.amount), "valor_novo": str(_q(value))}
    c.stage = Stage.CALCULADO
    c.save()
    _log(c, "instrução da revisão", valor=str(c.total))
    _instruction_step(c, user, "instrução da revisão")
    return c

# ---------------------------------------------------------------------------- implantação
def _payroll_group(institution, segment: str):
    from apps.institutions.models import PayrollGroup
    from apps.institutions.services import ensure_payroll_groups

    ensure_payroll_groups(institution)
    g = PayrollGroup.objects.filter(institution=institution, segment=segment, active=True).first()
    if g is None:
        raise BusinessRuleError(f"Folha da massa {segment} não encontrada ou inativa.")
    return g


@transaction.atomic
def implant(c: Concession) -> list[Benefit]:
    from apps.employment.models import EventType, FunctionalEvent, LinkStatus

    _require(c, Stage.PUBLICADO)
    act = f"{c.get_act_nature_display()} nº {c.act_number} de {c.act_date:%d/%m/%Y}, publicada em " \
          f"{c.publication_date:%d/%m/%Y} ({c.publication_media})"
    created = []
    if c.kind == "REVISAO":
        b = event(c.revised_benefit, BenefitEventKind.REVISAO, c.validity_date,
                  f"Revisão — {act}. Motivo: {c.revision_reason}", act=act[:100], amount=c.total, process=c.process,
                  from_concession=True)
        _move_done(c, act, 1)
        return [b]
    if c.kind == BenefitKind.APOSENTADORIA:
        link = c.link
        segment = link.segment if link else "PREVIDENCIARIO"
        b = Benefit.objects.create(
            institution=c.institution, kind=BenefitKind.APOSENTADORIA, modality=c.modality, beneficiary=c.person,
            concession=c, payroll_group=_payroll_group(c.institution, segment),
            life_purchase=link.life_purchase if link else None, registration=link.registration if link else "",
            legal_basis=c.legal_basis, start_date=c.validity_date, amount=c.total, integralidade=c.integralidade,
            paridade=c.paridade)
        created.append(b)
        if link and link.status == LinkStatus.ATIVO:
            end = c.validity_date - timedelta(days=1)
            link.status, link.end_date, link.end_reason = LinkStatus.APOSENTADO, max(end, link.position_start), \
                f"Aposentadoria — {c.legal_basis}"
            link.save()
            FunctionalEvent.objects.create(institution=c.institution, link=link, event_type=EventType.APOSENTADORIA,
                                           start_date=c.validity_date, act_type=c.get_act_nature_display(),
                                           act_number=c.act_number, act_date=c.act_date,
                                           publication=c.publication_media, description=f"Aposentadoria — {c.legal_basis}")
    else:
        source_link = c.link
        segment = (c.instituidor_benefit.payroll_group.segment if c.instituidor_benefit
                   else source_link.segment if source_link else "PREVIDENCIARIO")
        group = _payroll_group(c.institution, segment)
        for q in c.quotas.select_related("dependent"):
            b = Benefit.objects.create(
                institution=c.institution, kind=BenefitKind.PENSAO, beneficiary=q.dependent, instituidor=c.person,
                concession=c, payroll_group=group,
                life_purchase=(c.instituidor_benefit.life_purchase if c.instituidor_benefit else
                               source_link.life_purchase if source_link else None),
                legal_basis=c.legal_basis, start_date=c.validity_date, end_date=q.end_date, amount=q.amount,
                percent=q.percent)
            created.append(b)
        if c.instituidor_benefit and c.instituidor_benefit.status != BenefitStatus.CESSADO:
            event(c.instituidor_benefit, BenefitEventKind.CESSACAO, c.death_date, "Óbito do aposentado", act="")
        if source_link and source_link.status == LinkStatus.ATIVO:
            source_link.status, source_link.end_date, source_link.end_reason = \
                LinkStatus.FALECIDO, c.death_date, "Falecimento"
            source_link.save()
    for b in created:
        BenefitEvent.objects.create(institution=c.institution, benefit=b, kind=BenefitEventKind.IMPLANTACAO,
                                    date=b.start_date, justification=f"Implantação — {act}", act=act[:100],
                                    new_values={"valor": str(b.amount), "folha": b.payroll_group.code},
                                    process=c.process)
    _move_done(c, act, len(created))
    return created


def _move_done(c: Concession, act: str, n: int):
    from apps.protocolo.models import Movement, MovementKind

    what = "Revisão aplicada na folha" if c.kind == "REVISAO" else f"Benefício implantado na folha ({n} beneficiário(s))"
    Movement.objects.create(institution=c.institution, process=c.process, kind=MovementKind.DESPACHO,
                            from_sector=c.process.current_sector, occurred_at=timezone.now(),
                            text=f"{what}. {act}. Encaminhar ao setor de COMPREV para envio ao TCE-RJ.",
                            due_date_after=c.process.due_date)
    c.stage, c.implanted_at = Stage.IMPLANTADO, timezone.now()
    c.save()
    _log(c, "implantação", beneficios=n)


# ---------------------------------------------------------------------------- operações sobre benefícios
TRANSITIONS = {
    BenefitEventKind.REVISAO: {BenefitStatus.ATIVO, BenefitStatus.SUSPENSO},
    BenefitEventKind.SUSPENSAO: {BenefitStatus.ATIVO},
    BenefitEventKind.RESTABELECIMENTO: {BenefitStatus.SUSPENSO},
    BenefitEventKind.CESSACAO: {BenefitStatus.ATIVO, BenefitStatus.SUSPENSO},
    BenefitEventKind.REVERSAO: {BenefitStatus.ATIVO, BenefitStatus.SUSPENSO},
}


@transaction.atomic
def event(b: Benefit, kind: str, when: date, justification: str, act: str = "", amount=None, process=None,
          from_concession: bool = False) -> Benefit:
    if kind not in TRANSITIONS:
        raise BusinessRuleError("Operação inválida.")
    if kind == BenefitEventKind.REVISAO and not from_concession:
        raise BusinessRuleError("A revisão de valor exige processo próprio (Concessão › Revisão): parecer jurídico, "
                                "portaria assinada pela Presidência e publicação antes de alterar a folha.")
    if b.status not in TRANSITIONS[kind]:
        raise BusinessRuleError(f"Operação não permitida para benefício {b.get_status_display().lower()}.")
    if not justification or len(justification.strip()) < 10:
        raise BusinessRuleError("Informe a justificativa / fundamento (mínimo de 10 caracteres).")
    if when < b.start_date:
        raise BusinessRuleError("A data de efeito não pode ser anterior ao início do benefício.")
    old = {"situacao": b.status, "valor": str(b.amount)}
    if kind == BenefitEventKind.REVISAO:
        value = _money(amount)
        if value is None or value < 0:
            raise BusinessRuleError("Informe o novo valor (ex.: 5.300,00).")
        b.amount = _q(value)
    elif kind == BenefitEventKind.SUSPENSAO:
        b.status = BenefitStatus.SUSPENSO
    elif kind == BenefitEventKind.RESTABELECIMENTO:
        b.status = BenefitStatus.ATIVO
    else:  # cessação ou reversão
        b.status, b.end_date = BenefitStatus.CESSADO, when
    b.save()
    BenefitEvent.objects.create(institution=b.institution, benefit=b, kind=kind, date=when,
                                justification=justification.strip(), act=act[:100], old_values=old,
                                new_values={"situacao": b.status, "valor": str(b.amount)}, process=process)
    return b


@transaction.atomic
def implant_legacy(legacy) -> Benefit:
    """Implanta na folha um benefício trazido pela importação (base SPREV)."""
    if Benefit.objects.filter(legacy=legacy).exists():
        raise BusinessRuleError("Benefício importado já implantado.")
    if legacy.amount is None or legacy.start_date is None:
        raise BusinessRuleError("Benefício importado sem valor ou data de início — complete os dados antes.")
    raw = legacy.raw or {}
    modality = None
    if legacy.kind == "APOSENTADORIA":
        try:
            modality = int(float(raw.get("CO_TIPO_APOSENTADORIA") or 0)) or None
        except ValueError:
            modality = None
        modality = modality if modality in Modality.values else None
    b = Benefit.objects.create(
        institution=legacy.institution, kind=legacy.kind, modality=modality, beneficiary=legacy.beneficiary,
        instituidor=legacy.instituidor, legacy=legacy,
        payroll_group=_payroll_group(legacy.institution, legacy.segment or "PREVIDENCIARIO"),
        registration=legacy.registration, legal_basis="Benefício concedido no sistema anterior",
        start_date=legacy.start_date, amount=legacy.amount,
        paridade=str(raw.get("IN_PARID_SERV", "")).strip() in ("1", "1.0"))
    BenefitEvent.objects.create(institution=b.institution, benefit=b, kind=BenefitEventKind.IMPLANTACAO,
                                date=b.start_date, justification=f"Implantação de benefício importado (lote {legacy.batch_id}).",
                                new_values={"valor": str(b.amount), "folha": b.payroll_group.code})
    legacy.implanted = True
    legacy.save(update_fields=["implanted", "updated_at"])
    return b


def stage_index(stage: str) -> int:
    return STAGE_ORDER.index(stage) if stage in STAGE_ORDER else -1
