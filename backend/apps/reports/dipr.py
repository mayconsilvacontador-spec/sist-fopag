"""
Relatórios para o DIPR (Demonstrativo de Informações Previdenciárias e Repasses): folha ANALÍTICA segregada por ÓRGÃO
e RESUMO por órgão × plano × categoria, com remuneração bruta, base de cálculo, contribuições, nº de segurados e de
dependentes.

Fontes da competência (sem duplicar):
- ATIVOS: contracheques da Folha de Ativos do SIST (folha não ABERTA); quando o órgão não roda a folha no SIST, a
  ficha financeira IMPORTADA (`pessoal.FinancialLine`) — bruto = proventos; base = linha de base, senão soma dos
  proventos "entra na base RPPS", senão desconto ÷ alíquota (cálculo inverso, marcado "estimada").
- APOSENTADOS e PENSIONISTAS: contracheques da folha de benefícios (folha não ABERTA); órgão = o do vínculo que
  originou a concessão.
Patronal dos ativos = a da folha do SIST ou base × `arrecadacao.aliquota_patronal` da competência.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from apps.institutions.services import get_parameter

from .registry import col, report, result

ZERO = Decimal("0")
COMP = {"key": "competencia", "label": "Competência", "type": "competencia", "default": "mes_anterior"}
KIND = {"key": "tipo_folha", "label": "Folha", "type": "select", "default": "MENSAL",
        "options": [["MENSAL", "Mensal"], ["DECIMO", "13º salário"]]}
PLANO = {"key": "plano", "label": "Plano", "type": "select", "default": "",
         "options": [["", "Todos"], ["FINANCEIRO", "Financeiro"], ["PREVIDENCIARIO", "Previdenciário"],
                     ["COMPRA_VIDAS", "Compra de Vidas"]]}
CAT = {"key": "categoria", "label": "Segurados", "type": "select", "default": "",
       "options": [["", "Todos"], ["ATIVO", "Ativos"], ["APOSENTADO", "Aposentados"], ["PENSIONISTA", "Pensionistas"]]}
CAT_LABEL = {"ATIVO": "Ativo", "APOSENTADO": "Aposentado", "PENSIONISTA": "Pensionista"}
SEG_LABEL = {"FINANCEIRO": "Financeiro", "PREVIDENCIARIO": "Previdenciário", "COMPRA_VIDAS": "Compra de Vidas"}


def _comp(p) -> date:
    from apps.core.exceptions import BusinessRuleError

    v = (p.get("competencia") or "").strip()
    try:
        y, m = v.split("-")
        return date(int(y), int(m), 1)
    except ValueError:
        raise BusinessRuleError("Informe a competência (AAAA-MM).")


def _rate(inst, key, comp, cache):
    if (key, comp) not in cache:
        v = get_parameter(inst, key, comp)
        cache[(key, comp)] = Decimal(str(v)) if v not in (None, "") else None
    return cache[(key, comp)]


def _dependents(inst, people, comp):
    from apps.people.models import Dependency

    nxt = date(comp.year + comp.month // 12, comp.month % 12 + 1, 1)
    out = defaultdict(int)
    qs = (Dependency.objects.filter(institution=inst, holder_id__in=people, start_date__lt=nxt)
          .exclude(end_date__lt=comp).values_list("holder_id", flat=True))
    for h in qs:
        out[h] += 1
    return out


def collect(inst, comp: date, kind: str = "MENSAL") -> list[dict]:
    from apps.folha.models import PayrollEntry, PayrollItem
    from apps.pessoal.models import ActivePayslip, ActivePayslipItem, FinancialLine

    cache, rows = {}, []
    # ---- ativos pela Folha de Ativos do SIST
    covered = set()
    if kind == "MENSAL":
        slips = (ActivePayslip.objects.filter(institution=inst, run__year=comp.year, run__month=comp.month)
                 .exclude(run__status="ABERTA").select_related("run__organ", "person"))
        contrib = defaultdict(lambda: ZERO)
        for it in ActivePayslipItem.objects.filter(payslip__in=slips, rubric__calc="CONTRIB_RPPS").values("payslip_id", "amount"):
            contrib[it["payslip_id"]] += it["amount"]
        for s in slips:
            covered.add((s.person_id, s.registration))
            rows.append({"orgao": s.run.organ.short_name or s.run.organ.name, "massa": s.segment, "categoria": "ATIVO",
                         "matricula": s.registration, "nome": s.person.name, "person_id": s.person_id,
                         "bruto": s.gross, "base": s.rpps_base, "contribuicao": contrib[s.pk],
                         "patronal": s.employer_contribution, "origem": "Folha do SIST"})
    # ---- ativos pela ficha financeira importada (órgãos que não rodam a folha no SIST)
    acc = {}
    lines = (FinancialLine.objects.filter(institution=inst, competence=comp, payroll_kind=kind)
             .select_related("person", "link__organ"))
    for ln in lines:
        k = (ln.person_id, ln.registration)
        if k in covered:
            continue
        a = acc.setdefault(k, {"ln": ln, "bruto": ZERO, "base": None, "incide": None, "desc": ZERO})
        if ln.nature == "PROVENTO":
            a["bruto"] += ln.amount
        if ln.category == "BASE_RPPS":
            a["base"] = (a["base"] or ZERO) + ln.amount
        elif ln.category == "INCIDE_RPPS":
            a["incide"] = (a["incide"] or ZERO) + ln.amount
        elif ln.category == "CONTRIB_RPPS":
            a["desc"] += ln.amount
    for (pid, reg), a in acc.items():
        ln = a["ln"]
        rate = _rate(inst, "folha.aliquota_segurado", comp, cache)
        prate = _rate(inst, "arrecadacao.aliquota_patronal", comp, cache)
        base, origem = a["base"], "Ficha importada"
        if base is None and a["incide"] is not None:
            base = a["incide"]
        if base is None:
            base = (a["desc"] / rate).quantize(Decimal("0.01")) if a["desc"] and rate else ZERO
            origem = "Ficha importada (base estimada pelo desconto)"
        link = ln.link
        rows.append({"orgao": (link.organ.short_name or link.organ.name) if link else "SEM VÍNCULO IDENTIFICADO",
                     "massa": link.segment if link else "", "categoria": "ATIVO", "matricula": reg,
                     "nome": ln.person.name, "person_id": pid, "bruto": a["bruto"], "base": base,
                     "contribuicao": a["desc"], "patronal": (base * prate).quantize(Decimal("0.01")) if prate else None,
                     "origem": origem})
    # ---- aposentados e pensionistas (folha de benefícios)
    entries = (PayrollEntry.objects.filter(institution=inst, run__competence__year=comp.year,
                                           run__competence__month=comp.month, run__kind=kind)
               .exclude(run__status="ABERTA")
               .select_related("run__payroll_group", "beneficiary", "benefit__concession__link__organ"))
    contrib = defaultdict(lambda: ZERO)
    for it in PayrollItem.objects.filter(entry__in=entries, rubric__calc__in=["CONTRIB_RPPS", "CONTRIB_13"]).values("entry_id", "amount"):
        contrib[it["entry_id"]] += it["amount"]
    for e in entries:
        b = e.benefit
        link = b.concession.link if b.concession_id and b.concession.link_id else None
        rows.append({"orgao": (link.organ.short_name or link.organ.name) if link else "SEM ÓRGÃO DE ORIGEM",
                     "massa": e.run.payroll_group.segment,
                     "categoria": "PENSIONISTA" if b.kind == "PENSAO" else "APOSENTADO",
                     "matricula": link.registration if link else "", "nome": e.beneficiary.name,
                     "person_id": e.beneficiary_id, "bruto": e.gross, "base": e.rpps_base,
                     "contribuicao": contrib[e.pk], "patronal": None, "origem": "Folha de benefícios"})
    deps = _dependents(inst, {r["person_id"] for r in rows}, comp)
    seen = set()
    for r in rows:  # dependentes contados uma vez por pessoa (quem acumula dois vínculos não conta em dobro)
        r["dependentes"] = 0 if r["person_id"] in seen else deps.get(r["person_id"], 0)
        seen.add(r["person_id"])
    return rows


def _filter(rows, p):
    if p.get("plano"):
        rows = [r for r in rows if r["massa"] == p["plano"]]
    if p.get("categoria"):
        rows = [r for r in rows if r["categoria"] == p["categoria"]]
    return rows


def _sum(rows, key):
    return sum((r[key] or ZERO for r in rows), ZERO)


def _totals(rows) -> dict:
    return {"bruto": _sum(rows, "bruto"), "base": _sum(rows, "base"), "contribuicao": _sum(rows, "contribuicao"),
            "patronal": _sum(rows, "patronal"), "dependentes": sum(r["dependentes"] for r in rows),
            "segurados": len({r["person_id"] for r in rows})}


def _br(v) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _notes(rows, label) -> list[str]:
    t = _totals(rows)
    by_cat = defaultdict(set)
    for r in rows:
        by_cat[r["categoria"]].add(r["person_id"])
    notes = [f"Competência {label} — Remuneração bruta {_br(t['bruto'])} · Base de cálculo {_br(t['base'])} · "
             f"Contribuição dos segurados {_br(t['contribuicao'])} · Patronal {_br(t['patronal'])}",
             "Segurados: " + " · ".join(f"{CAT_LABEL[c]}s {len(by_cat[c])}" for c in CAT_LABEL if by_cat[c])
             + f" · Total {t['segurados']} · Dependentes {t['dependentes']}"]
    est = sum(1 for r in rows if "estimada" in r["origem"])
    if est:
        notes.append(f"{est} linha(s) com base estimada pelo desconto (desconto ÷ alíquota): classifique na ficha "
                     "financeira os proventos que entram na base para conferir.")
    if any(r["patronal"] is None and r["categoria"] == "ATIVO" for r in rows):
        notes.append("Há competência sem alíquota patronal cadastrada (Arrecadação › Alíquotas).")
    return notes


@report("dipr-analitico", "relatorios.folha", "Folha analítica por órgão (DIPR)",
        "Cada segurado da competência, agrupado por órgão, com remuneração bruta, base de cálculo, contribuições e "
        "dependentes; subtotal por órgão e totais gerais para preencher o DIPR.",
        [COMP, KIND, PLANO, CAT], landscape=True, also=("relatorios.financeiros",))
def dipr_analitico(inst, p):
    comp = _comp(p)
    rows = _filter(collect(inst, comp, p.get("tipo_folha") or "MENSAL"), p)
    rows.sort(key=lambda r: (r["orgao"], r["categoria"], r["nome"]))
    out = []
    by_org = defaultdict(list)
    for r in rows:
        by_org[r["orgao"]].append(r)
    for org, rs in by_org.items():
        for r in rs:
            out.append({**r, "massa": SEG_LABEL.get(r["massa"], r["massa"]), "categoria": CAT_LABEL[r["categoria"]]})
        t = _totals(rs)
        out.append({"orgao": org, "nome": f"SUBTOTAL — {t['segurados']} segurado(s)", "_subtotal": True,
                    **{k: t[k] for k in ("bruto", "base", "contribuicao", "patronal", "dependentes")}})
    for r in out:
        r.pop("person_id", None)
    t = _totals(rows)
    return result([col("orgao", "Órgão"), col("massa", "Plano"), col("categoria", "Categoria"),
                   col("matricula", "Matrícula"), col("nome", "Nome"), col("bruto", "Remuneração bruta", "money"),
                   col("base", "Base de cálculo", "money"), col("contribuicao", "Contribuição do segurado", "money"),
                   col("patronal", "Patronal", "money"), col("dependentes", "Dependentes", "int"),
                   col("origem", "Origem")],
                  out, {"nome": f"{t['segurados']} segurado(s) em {len(by_org)} órgão(s)",
                        **{k: t[k] for k in ("bruto", "base", "contribuicao", "patronal", "dependentes")}},
                  _notes(rows, f"{comp:%m/%Y}"))


@report("dipr-resumo", "relatorios.folha", "Resumo por órgão e plano (DIPR)",
        "Por órgão, plano e categoria: nº de segurados e dependentes, remuneração bruta, base de cálculo e contribuições "
        "da competência — os números do DIPR.", [COMP, KIND, PLANO, CAT], also=("relatorios.financeiros",))
def dipr_resumo(inst, p):
    comp = _comp(p)
    rows = _filter(collect(inst, comp, p.get("tipo_folha") or "MENSAL"), p)
    groups = defaultdict(list)
    for r in rows:
        groups[(r["orgao"], r["massa"], r["categoria"])].append(r)
    out = []
    for (org, seg, cat), rs in sorted(groups.items()):
        t = _totals(rs)
        out.append({"orgao": org, "massa": SEG_LABEL.get(seg, seg), "categoria": CAT_LABEL[cat],
                    "segurados": t["segurados"], **{k: t[k] for k in ("dependentes", "bruto", "base", "contribuicao", "patronal")}})
    t = _totals(rows)
    return result([col("orgao", "Órgão"), col("massa", "Plano"), col("categoria", "Categoria"),
                   col("segurados", "Segurados", "int"), col("dependentes", "Dependentes", "int"),
                   col("bruto", "Remuneração bruta", "money"), col("base", "Base de cálculo", "money"),
                   col("contribuicao", "Contribuição do segurado", "money"), col("patronal", "Patronal", "money")],
                  out, {"orgao": "Total", **{k: t[k] for k in ("segurados", "dependentes", "bruto", "base", "contribuicao", "patronal")}},
                  _notes(rows, f"{comp:%m/%Y}"))
