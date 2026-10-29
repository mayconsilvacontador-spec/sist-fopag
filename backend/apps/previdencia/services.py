"""Serviços da gestão previdenciária: simulação, importação de salários, fatores, SalContr.txt e CTC."""
import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.validators import format_cpf, only_digits

from .calculo import Averages, estimate
from .models import ContributionRegime, ContributionSalary, CorrectionFactor, Ctc, RetirementRule, TimeNature
from .rules import RuleEvaluator, age_years
from .tempo import DAYS_YEAR, PersonTime, ymd

GROUP_ORDER = {"PERMANENTE": 0, "TRANSICAO": 1, "DIREITO_ADQUIRIDO": 2, "COMPULSORIA": 3}


def is_teacher(pt: PersonTime) -> bool:
    return any(p.magisterio for p in pt.periods)


# ---------------------------------------------------------------------------- simulação
def simulate(person, on: date | None = None) -> dict:
    today = on or timezone.localdate()
    pt = PersonTime(person)
    ev = RuleEvaluator(person, pt, today)
    avg = Averages(person, today, pt)
    teacher = is_teacher(pt)
    rules = RetirementRule.objects.filter(institution=person.institution, active=True)
    out = []
    for rule in rules:
        if rule.for_teacher and not teacher:
            continue
        r = ev.evaluate(rule)
        # Mesmo critério da concessão: média até a data da simulação (equivale à abertura do processo hoje);
        # tempo na data da simulação ou, se a regra ainda não foi cumprida, na data em que será.
        est = (estimate(rule, ev, avg, max(r.eligible_date, today), eligible=r.eligible_date)
               if r.eligible_date else None)
        out.append({
            "codigo": rule.code, "nome": rule.name, "fundamento": rule.legal_basis, "grupo": rule.group,
            "professor": rule.for_teacher, "situacao": r.status, "data_elegibilidade": r.eligible_date,
            "data_referencia": r.reference_date,
            "requisitos": [{"chave": q.key, "descricao": q.label, "exigido": q.required, "atual": q.achieved,
                            "cumprido": q.met} for q in r.requirements],
            "observacoes": r.notes + ([rule.notes] if rule.notes else []),
            "proventos": rule.proventos, "paridade": rule.paridade, "estimativa": est,
            "abono": rule.gives_permanence_bonus,
        })
    out.sort(key=lambda x: (x["situacao"] not in ("CUMPRIDA", "CUMPRIRA"), x["data_elegibilidade"] or date.max,
                            GROUP_ORDER.get(x["grupo"], 9)))
    voluntary = [x for x in out if x["abono"] and x["data_elegibilidade"]]
    abono = min((x["data_elegibilidade"] for x in voluntary), default=None)
    s = pt.summary(today)
    warnings = list(pt.warnings) + avg.warnings + avg.pendencias
    if pt.link and pt.link.position.cargo_type == 6:
        warnings.append("Guarda Municipal: confira na legislação do RPPS se há idade mínima própria (atividade de risco) — "
                        "as regras gerais foram aplicadas.")
    if pt.link is None:
        warnings.append("Sem vínculo estatutário no cadastro — cadastre o vínculo para simular.")
    return {
        "data_referencia": today,
        "idade": age_years(person.birth_date, today),
        "professor": teacher,
        "ingresso_servico_publico": pt.public_service_start,
        "ingresso_ente": pt.municipal_effective_start,
        "tempo": {
            "contribuicao": s.contribuicao, "contribuicao_texto": ymd(s.contribuicao),
            "servico_publico": s.servico_publico, "servico_publico_texto": ymd(s.servico_publico),
            "magisterio": s.magisterio, "magisterio_texto": ymd(s.magisterio),
            "especial": s.especial, "carreira": s.carreira, "cargo": s.cargo, "cargo_texto": ymd(s.cargo),
            "carreira_texto": ymd(s.carreira), "conversao": s.conversao,
        },
        "medias": {"media80": str(avg.media80) if avg.media80 else None,
                   "media100": str(avg.media100) if avg.media100 else None, "meses": avg.months,
                   "ultima_remuneracao_rpps": str(avg.last_rpps) if avg.last_rpps else None},
        "abono_permanencia": {"data": abono,
                              "ja_tem_direito": bool(abono and abono <= today and pt.link and pt.link.status == "ATIVO")},
        "regras": out,
        "avisos": warnings,
    }


def time_report(person, on: date | None = None) -> dict:
    on = on or timezone.localdate()
    pt = PersonTime(person)
    s = pt.summary(on)
    return {
        "data_referencia": on, "periodos": pt.detail(on), "avisos": pt.warnings,
        "totais": {k: {"dias": getattr(s, k), "texto": ymd(getattr(s, k))}
                   for k in ("contribuicao", "servico_publico", "magisterio", "especial", "carreira", "cargo")},
    }


# ---------------------------------------------------------------------------- salários de contribuição
def _parse_comp(v: str) -> date:
    s = (v or "").strip()
    for fmt in ("%m/%Y", "%m%Y", "%Y-%m", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d.replace(day=1)
        except ValueError:
            continue
    raise ValueError(f"competência inválida: {s!r}")


def _parse_money(v: str) -> Decimal:
    s = (v or "").strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"valor inválido: {v!r}")


def _rows(content: bytes):
    text = None
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    delimiter = max([";", ",", "\t"], key=text[:2000].count)
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


@transaction.atomic
def import_salaries(person, content: bytes) -> dict:
    """
    CSV: competencia;valor[;regime][;vinculo]  (cabeçalho opcional; regime RPPS/RGPS, padrão RPPS).
    Competência repetida (mesmo regime e vínculo) é atualizada.
    """
    rows = _rows(content)
    created = updated = 0
    errors = []
    for i, row in enumerate(rows, start=1):
        if not row or not "".join(row).strip():
            continue
        if i == 1 and not any(ch.isdigit() for ch in row[0]):
            continue  # cabeçalho
        try:
            comp = _parse_comp(row[0])
            if comp < date(1994, 7, 1):
                raise ValueError("competência anterior a 07/1994")
            amount = _parse_money(row[1])
            regime = (row[2].strip().upper() if len(row) > 2 and row[2].strip() else "RPPS")
            if regime not in ContributionRegime.values:
                raise ValueError("regime deve ser RPPS ou RGPS")
            label = row[3].strip()[:150] if len(row) > 3 else ""
            _, c = ContributionSalary.objects.update_or_create(
                person=person, competence=comp, regime=regime, source_label=label,
                defaults={"institution": person.institution, "amount": amount, "origin": "IMPORTACAO"},
            )
            created += int(c)
            updated += int(not c)
        except (ValueError, IndexError) as exc:
            errors.append({"linha": i, "mensagem": str(exc)})
    return {"incluidos": created, "atualizados": updated, "erros": errors}


@transaction.atomic
def import_factors(institution, table_month: date, content: bytes) -> dict:
    """CSV: competencia;fator — tabela de atualização de um mês."""
    rows = _rows(content)
    table_month = table_month.replace(day=1)
    n, errors = 0, []
    for i, row in enumerate(rows, start=1):
        if not row or not "".join(row).strip():
            continue
        if i == 1 and not any(ch.isdigit() for ch in row[0]):
            continue
        try:
            comp = _parse_comp(row[0])
            factor = Decimal(row[1].strip().replace(".", "").replace(",", ".")) if "," in row[1] else Decimal(row[1].strip())
            if factor <= 0:
                raise ValueError("fator deve ser positivo")
            CorrectionFactor.objects.update_or_create(institution=institution, table_month=table_month,
                                                      competence=comp, defaults={"factor": factor})
            n += 1
        except (ValueError, IndexError, InvalidOperation) as exc:
            errors.append({"linha": i, "mensagem": str(exc)})
    return {"fatores": n, "erros": errors}


# ---------------------------------------------------------------------------- Deliberação 260 — SalContr.txt
def salcontr_txt(person, *, unidade_gestora: str, orgao: str, matricula: str, processo: str, tipo_ato: int = 1) -> str:
    """
    Arquivo SalContr.txt (leiaute de importação da Deliberação TCE-RJ 260/2013, versão 2014) — o único
    arquivo que o FATIMA importa. Posições: UG 1-4 (N), Órgão 5-8 (N), Matrícula 9-18 (AN), Tipo do ato 19
    (N), Processo 20-39 (AN), Mês/Ano 40-45 (mmaaaa), Regime 46 (1 RPPS, 2 RGPS), Salário 47-62 (V, 2 casas,
    sem separador). Numérico: alinhado à direita com brancos; AN: à esquerda com brancos; V: zeros à esquerda.
    """
    ug, org = only_digits(unidade_gestora), only_digits(orgao)
    if not (ug and org and len(ug) <= 4 and len(org) <= 4):
        raise BusinessRuleError("Informe os códigos SIGFIS da unidade gestora e do órgão (até 4 dígitos).")
    if not matricula or not processo:
        raise BusinessRuleError("Informe a matrícula e o número do processo de origem.")
    monthly = defaultdict(lambda: defaultdict(Decimal))
    for s in ContributionSalary.objects.filter(person=person, competence__gte=date(1994, 7, 1)):
        monthly[s.competence][s.regime] += s.amount
    if not monthly:
        raise BusinessRuleError("O segurado não tem salários de contribuição cadastrados.")
    lines = []
    for comp in sorted(monthly):
        for regime, value in sorted(monthly[comp].items()):
            cents = int((value * 100).to_integral_value())
            line = (ug.rjust(4) + org.rjust(4) + matricula[:10].ljust(10) + str(tipo_ato)[:1]
                    + processo[:20].ljust(20) + comp.strftime("%m%Y") + ("1" if regime == "RPPS" else "2")
                    + str(cents).rjust(16, "0"))
            assert len(line) == 62
            lines.append(line)
    return "\r\n".join(lines) + "\r\n"


# ---------------------------------------------------------------------------- CTC
def _year_frequency(pt: PersonTime, start: date, end: date) -> list[dict]:
    """Frequência anual (dias brutos, deduções, líquidos) dos períodos do RPPS de origem no intervalo."""
    rows = []
    for y in range(start.year, end.year + 1):
        ys, ye = max(date(y, 1, 1), start), min(date(y, 12, 31), end)
        gross = ded = 0
        for p in pt.periods:
            if p.nature != TimeNature.RPPS_ORIGEM:
                continue
            ps, pe = max(p.start, ys), min(p.end or ye, ye)
            if ps > pe:
                continue
            gross += (pe - ps).days + 1
            for ds, de, days in p.deductions:
                de = de or ds
                lo, hi = max(ds, ps), min(de, pe)
                if days is not None and ps <= ds <= pe:
                    ded += days
                elif days is None and lo <= hi:
                    ded += (hi - lo).days + 1
        if gross:
            rows.append({"ano": y, "dias_brutos": gross, "deducoes": ded, "dias_liquidos": gross - ded})
    return rows


@transaction.atomic
def issue_ctc(person, *, destination: str, purpose: str, period_start: date, period_end: date, process=None,
              issuer_name: str = "") -> Ctc:
    from apps.employment.models import EmploymentLink, LinkStatus, Regime

    links = list(EmploymentLink.objects.filter(person=person, regime=Regime.ESTATUTARIO).select_related("organ", "position"))
    if not links:
        raise BusinessRuleError("O segurado não tem vínculo estatutário para certificar.")
    if any(lk.status == LinkStatus.ATIVO for lk in links):
        raise BusinessRuleError("A CTC é emitida para ex-servidor: encerre o vínculo (exoneração/vacância) antes.")
    if any(lk.status in (LinkStatus.APOSENTADO,) for lk in links):
        raise BusinessRuleError("Tempo já utilizado em aposentadoria neste RPPS não pode ser certificado.")
    if period_end < period_start:
        raise BusinessRuleError("Período inválido.")
    overlap = Ctc.objects.select_for_update().filter(person=person, status="EMITIDA",
                                                     period_start__lte=period_end, period_end__gte=period_start)
    if overlap.exists():
        raise BusinessRuleError(f"Já existe CTC emitida para parte deste período (nº {overlap.first().code}).")

    pt = PersonTime(person, reference_link=links[-1])
    freq = _year_frequency(pt, period_start, period_end)
    if not freq:
        raise BusinessRuleError("Não há tempo de contribuição no RPPS de origem dentro do período informado.")
    gross = sum(r["dias_brutos"] for r in freq)
    ded = sum(r["deducoes"] for r in freq)
    net = gross - ded
    salaries = [
        {"competencia": s.competence.strftime("%m/%Y"), "valor": str(s.amount)}
        for s in ContributionSalary.objects.filter(person=person, regime="RPPS",
                                                    competence__gte=max(period_start.replace(day=1), date(1994, 7, 1)),
                                                    competence__lte=period_end).order_by("competence")
    ]
    inst = person.institution
    year = timezone.localdate().year
    number = (Ctc.objects.select_for_update().filter(institution=inst, year=year).aggregate(m=Max("number"))["m"] or 0) + 1
    snapshot = {
        "instituicao": {"nome": inst.name, "sigla": inst.short_name, "cnpj": inst.cnpj or "", "cidade": inst.city,
                        "uf": inst.uf, "ente": inst.ente_name},
        "segurado": {"nome": person.name, "cpf": format_cpf(person.cpf), "pis_pasep": person.pis_pasep,
                     "rg": f"{person.rg_number} {person.rg_issuer}/{person.rg_uf}".strip(" /"),
                     "nascimento": person.birth_date.isoformat(), "sexo": person.get_sex_display(),
                     "mae": person.mother_name, "pai": person.father_name},
        "vinculos": [{"matricula": lk.registration, "orgao": lk.organ.name, "cargo": lk.position.name,
                      "admissao": lk.position_start.isoformat(),
                      "exoneracao": lk.end_date.isoformat() if lk.end_date else None,
                      "motivo": lk.end_reason} for lk in links],
        "periodo": {"inicio": period_start.isoformat(), "fim": period_end.isoformat()},
        "frequencia_anual": freq,
        "totais": {"dias_brutos": gross, "deducoes": ded, "dias_liquidos": net, "liquido_texto": ymd(net),
                   "anos_decimais": str((Decimal(net) / DAYS_YEAR).quantize(Decimal("0.0001")))},
        "remuneracoes": salaries,
        "destino": destination, "finalidade": purpose,
        "emitida_em": timezone.now().isoformat(), "emitida_por": issuer_name,
        "observacoes": [
            "Certidão emitida nos termos da Portaria MTP nº 1.467/2022, vedada a contagem de tempo concomitante.",
            "Os períodos certificados não foram utilizados para concessão de benefício neste regime.",
        ],
    }
    sha = hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return Ctc.objects.create(institution=inst, number=number, year=year, person=person, destination=destination,
                              purpose=purpose, period_start=period_start, period_end=period_end, snapshot=snapshot,
                              sha256=sha, process=process)


@transaction.atomic
def import_salaries_batch(institution, content: bytes) -> dict:
    """
    Lote de vários segurados (ex.: arquivo do RH da Prefeitura).
    CSV: cpf;competencia;valor[;regime][;vinculo]  (cabeçalho opcional). CPF com ou sem máscara.
    Linhas de CPF ainda não cadastrado são recusadas e listadas; as demais são importadas.
    Competência repetida (mesmo segurado, regime e vínculo) é atualizada. Gravação em blocos (arquivos grandes).
    """
    from apps.core.validators import only_digits
    from apps.people.models import Person

    rows = _rows(content)
    parsed, errors, unknown, cpfs = {}, [], set(), set()
    for i, row in enumerate(rows, start=1):
        if not row or not "".join(row).strip():
            continue
        if i == 1 and not any(ch.isdigit() for ch in row[0]):
            continue  # cabeçalho
        try:
            cpf = only_digits(row[0])
            if len(cpf) != 11:
                raise ValueError("CPF inválido")
            comp = _parse_comp(row[1])
            if comp < date(1994, 7, 1):
                raise ValueError("competência anterior a 07/1994")
            amount = _parse_money(row[2])
            regime = (row[3].strip().upper() if len(row) > 3 and row[3].strip() else "RPPS")
            if regime not in ContributionRegime.values:
                raise ValueError("regime deve ser RPPS ou RGPS")
            label = row[4].strip()[:150] if len(row) > 4 else ""
            parsed[(cpf, comp, regime, label)] = (i, amount)
            cpfs.add(cpf)
        except (ValueError, IndexError) as exc:
            if len(errors) < 200:
                errors.append({"linha": i, "mensagem": str(exc)})
    people = {p.cpf: p for p in Person.objects.filter(institution=institution, cpf__in=cpfs)}
    existing = {(s.person_id, s.competence, s.regime, s.source_label): s
                for s in ContributionSalary.objects.filter(person__in=people.values())}
    new, changed, touched = [], [], set()
    for (cpf, comp, regime, label), (line, amount) in parsed.items():
        person = people.get(cpf)
        if person is None:
            if cpf not in unknown and len(errors) < 200:
                errors.append({"linha": line, "mensagem": f"CPF {cpf} não cadastrado"})
            unknown.add(cpf)
            continue
        touched.add(cpf)
        obj = existing.get((person.pk, comp, regime, label))
        if obj is None:
            new.append(ContributionSalary(institution=institution, person=person, competence=comp, regime=regime,
                                          source_label=label, amount=amount, origin="IMPORTACAO"))
        elif obj.amount != amount:
            obj.amount, obj.origin = amount, "IMPORTACAO"
            changed.append(obj)
    ContributionSalary.objects.bulk_create(new, batch_size=2000)
    ContributionSalary.objects.bulk_update(changed, ["amount", "origin"], batch_size=2000)
    return {"segurados": len(touched), "incluidos": len(new), "atualizados": len(changed),
            "cpfs_nao_cadastrados": len(unknown), "erros": errors}