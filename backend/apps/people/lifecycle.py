"""
Vida do servidor: ADMISSÃO (porta de entrada) e CRONOLOGIA (ficha do servidor, da admissão ao óbito/pensão).

A admissão cria, de uma vez: a pessoa no Cadastro Único (ou completa a existente pelo CPF), o vínculo com o cargo,
o vencimento base, os eventos de NOMEAÇÃO e POSSE/EXERCÍCIO no histórico funcional, o endereço e a conta bancária.
A cronologia junta tudo o que o sistema já sabe da pessoa, em ordem de data: nascimento, tempo averbado de outros
regimes, admissões, vida funcional, folhas de ativos, aposentadoria/pensão (concessão, portaria, implantação),
eventos dos benefícios, óbito e pensões deixadas.
"""
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import is_valid_cpf, only_digits


def _d(v, field, required=False):
    if v in (None, ""):
        if required:
            raise BusinessRuleError(f"Informe {field}.")
        return None
    if isinstance(v, date):
        return v
    txt = str(v).strip()[:10]
    try:
        if "/" in txt:  # dd/mm/aaaa
            d, m, y = txt.split("/")
            return date(int(y), int(m), int(d))
        return date.fromisoformat(txt)
    except ValueError:
        raise BusinessRuleError(f"Data inválida em {field}.")


@transaction.atomic
def admit(institution, data: dict, user) -> dict:
    """data: {pessoa:{...}, endereco:{...}?, conta:{...}?, vinculo:{...}}"""
    from decimal import Decimal, InvalidOperation

    from apps.cadastros.models import Bank, Organ, Position
    from apps.employment.models import EmploymentLink, FunctionalEvent

    from .models import Person
    from .services import add_address, add_bank_account

    pd, vd = data.get("pessoa") or {}, data.get("vinculo") or {}
    cpf = only_digits(pd.get("cpf"))
    if not is_valid_cpf(cpf):
        raise BusinessRuleError("CPF inválido.")
    organ = Organ.objects.filter(institution=institution, pk=vd.get("organ")).first()
    position = Position.objects.filter(institution=institution, pk=vd.get("position")).first()
    if organ is None or position is None:
        raise BusinessRuleError("Escolha o órgão e o cargo.")
    registration = str(vd.get("registration") or "").strip()
    if not registration:
        raise BusinessRuleError("Informe a matrícula.")
    if EmploymentLink.objects.filter(institution=institution, organ=organ, registration=registration).exists():
        raise BusinessRuleError(f"Já existe vínculo com a matrícula {registration} neste órgão.")
    nomeacao = _d(vd.get("nomeacao"), "a data da nomeação/admissão", True)
    exercicio = _d(vd.get("exercicio"), "a data de início do exercício") or nomeacao
    servico_publico = _d(vd.get("servico_publico"), "o ingresso no serviço público") or exercicio
    if exercicio < nomeacao:
        raise BusinessRuleError("O exercício não pode começar antes da nomeação.")
    salary = None
    if vd.get("base_salary") not in (None, ""):
        try:
            salary = Decimal(str(vd["base_salary"]).replace(".", "").replace(",", ".") if "," in str(vd["base_salary"])
                             else str(vd["base_salary"]))
        except InvalidOperation:
            raise BusinessRuleError("Vencimento inválido.")

    person = Person.objects.filter(institution=institution, cpf=cpf).first()
    created = person is None
    fields = {k: pd.get(k) for k in ("name", "social_name", "mother_name", "father_name", "rg_number", "rg_issuer",
                                     "rg_uf", "pis_pasep", "education", "email", "mobile", "phone", "voter_id",
                                     "birthplace_city", "birthplace_uf") if pd.get(k)}
    for k in ("sex", "marital_status", "race"):
        if pd.get(k) not in (None, ""):
            fields[k] = int(pd[k])
    if pd.get("rg_date"):
        fields["rg_date"] = _d(pd["rg_date"], "a emissão do RG")
    if created:
        birth = _d(pd.get("birth_date"), "a data de nascimento", True)
        if not fields.get("name") or not fields.get("sex"):
            raise BusinessRuleError("Informe nome e sexo.")
        if (nomeacao - birth).days < 16 * 365:
            raise BusinessRuleError("Data de admissão incompatível com a idade (menos de 16 anos).")
        fields["name"] = fields["name"].upper()
        person = Person.objects.create(institution=institution, cpf=cpf, birth_date=birth, **fields)
        log_event("CREATE", module="cadastros.segurados", obj=person, object_repr=f"{person.name} (admissão)")
    else:
        if person.death_date:
            raise BusinessRuleError("Esta pessoa consta como falecida no Cadastro Único.")
        changed = [k for k, v in fields.items() if not getattr(person, k)]
        for k in changed:
            setattr(person, k, fields[k])
        if changed:
            person.save(update_fields=changed + ["updated_at"])

    link = EmploymentLink.objects.create(
        institution=institution, person=person, organ=organ, position=position, registration=registration[:20],
        link_type=int(vd.get("link_type") or 1), regime=vd.get("regime") or "ESTATUTARIO",
        admission_form=int(vd.get("admission_form") or 3), public_service_start=servico_publico,
        ente_start=exercicio, career_start=exercicio, position_start=exercicio,
        statutory_since=exercicio if (vd.get("regime") or "ESTATUTARIO") == "ESTATUTARIO" else None,
        class_level=str(vd.get("class_level") or "")[:50], base_salary=salary,
        weekly_hours=int(vd["weekly_hours"]) if str(vd.get("weekly_hours") or "").isdigit() else None,
        segment=vd.get("segment") or "PREVIDENCIARIO", complementary_pension=bool(vd.get("complementary_pension")),
        workplace_id=vd.get("workplace") or None, notes=str(vd.get("notes") or ""))
    act = dict(act_type=str(vd.get("act_type") or "PORTARIA")[:30], act_number=str(vd.get("act_number") or "")[:30],
               act_date=_d(vd.get("act_date"), "a data do ato"), publication=str(vd.get("publication") or "")[:120])
    FunctionalEvent.objects.create(institution=institution, link=link, event_type="NOMEACAO", start_date=nomeacao,
                                   description=f"Admissão/nomeação no cargo de {position.name} ({organ.name}).", **act)
    FunctionalEvent.objects.create(institution=institution, link=link, event_type="POSSE", start_date=exercicio,
                                   description="Posse e início do exercício.")
    log_event("CREATE", module="cadastros.vinculos", obj=link,
              object_repr=f"Admissão — {person.name}, matrícula {registration}, {position.name}")

    ed = data.get("endereco") or {}
    cur_addr = person.addresses.filter(valid_to__isnull=True).first()
    same_addr = cur_addr and (cur_addr.street.upper(), cur_addr.number, cur_addr.city.upper()) == (
        str(ed.get("street") or "").upper(), str(ed.get("number") or ""), str(ed.get("city") or "").upper())
    if ed.get("street") and ed.get("city") and not same_addr:
        add_address(person, cep=only_digits(ed.get("cep"))[:8], street=ed["street"][:150], number=str(ed.get("number") or "")[:10],
                    complement=str(ed.get("complement") or "")[:60], district=str(ed.get("district") or "")[:80],
                    city=ed["city"][:120], uf=str(ed.get("uf") or "")[:2].upper(), valid_from=timezone.localdate())
    cd = data.get("conta") or {}
    cur_acc = person.bank_accounts.filter(valid_to__isnull=True).first()
    same_acc = cur_acc and (str(cur_acc.bank_id), cur_acc.branch, cur_acc.account) == (
        str(cd.get("bank")), only_digits(cd.get("branch")), only_digits(cd.get("account")))
    if cd.get("bank") and cd.get("branch") and cd.get("account") and not same_acc:
        bank = Bank.objects.filter(institution=institution, pk=cd["bank"]).first()
        if bank is None:
            raise BusinessRuleError("Banco inválido.")
        add_bank_account(person, bank=bank, branch=only_digits(cd["branch"])[:5], branch_digit=str(cd.get("branch_digit") or "")[:1],
                         account=only_digits(cd["account"])[:15], account_digit=str(cd.get("account_digit") or "")[:2],
                         account_type=cd.get("account_type") or "CORRENTE", valid_from=timezone.localdate())
    return {"pessoa": str(person.pk), "vinculo": str(link.pk), "pessoa_nova": created}


# ================================================================== cronologia
def _ev(when, group, title, detail="", link="", ref=""):
    return {"data": when.isoformat() if when else None, "grupo": group, "titulo": title, "detalhe": detail,
            "link": link, "ref": ref}


def timeline(person) -> list[dict]:
    from apps.concessao.models import Benefit, Concession
    from apps.employment.models import EmploymentLink
    from apps.previdencia.models import Averbacao, Ctc

    from .models import Dependency, Document

    out = [_ev(person.birth_date, "PESSOAL", "Nascimento",
               f"{person.birthplace_city}/{person.birthplace_uf}" if person.birthplace_city else "")]
    for av in Averbacao.objects.filter(person=person, active=True):
        out.append(_ev(av.start_date, "PREVIDENCIA", f"Tempo averbado — {av.get_nature_display()}",
                       f"{av.issuer}: {av.start_date:%d/%m/%Y} a {av.end_date:%d/%m/%Y} ({av.certified_days} dias)"
                       + (f" · CTC {av.certificate_number}" if av.certificate_number else "")))
    for lk in EmploymentLink.objects.filter(person=person).select_related("organ", "position").prefetch_related("events"):
        base = f"{lk.position.name} · {lk.organ.name} · matrícula {lk.registration}"
        has_nom = any(e.event_type == "NOMEACAO" for e in lk.events.all())
        if not has_nom:
            out.append(_ev(lk.ente_start, "FUNCIONAL", "Admissão", base))
        for e in lk.events.all():
            det = e.description + (f" · {e.act_type} {e.act_number}" if e.act_number else "") + \
                (f" · até {e.end_date:%d/%m/%Y}" if e.end_date else "") + (f" · {e.days} dia(s)" if e.days else "")
            out.append(_ev(e.start_date, "FUNCIONAL", e.get_event_type_display(), f"{det} ({lk.registration})"))
        if lk.end_date:
            out.append(_ev(lk.end_date, "FUNCIONAL", f"Fim do vínculo — {lk.get_status_display()}",
                           (lk.end_reason or "") + f" ({lk.registration})"))
    try:
        from apps.pessoal.models import ActivePayslip

        slips = list(ActivePayslip.objects.filter(person=person).select_related("run").order_by("run__year", "run__month"))
        if slips:
            f, la = slips[0], slips[-1]
            out.append(_ev(date(la.run.year, la.run.month, 1), "FOLHA",
                           f"Folha de ativos: {len(slips)} contracheque(s)",
                           f"de {f.run.month:02d}/{f.run.year} a {la.run.month:02d}/{la.run.year} · último líquido R$ {la.net}"))
    except ImportError:
        pass
    for c in Ctc.objects.filter(person=person):
        out.append(_ev(c.created_at.date(), "PREVIDENCIA", f"CTC emitida nº {c.code}", f"Para: {c.destination} · {c.get_status_display()}"))
    for c in Concession.objects.filter(person=person).select_related("process"):
        k = c.get_kind_display()
        out.append(_ev(c.process.opened_date if c.process_id else c.created_at.date(), "BENEFICIO",
                       f"Pedido de {k.lower()} — processo {c.process.code if c.process_id else ''}", f"Situação: {c.get_stage_display()}",
                       link=f"/concessao/processo/{c.pk}"))
        if c.act_date:
            out.append(_ev(c.act_date, "BENEFICIO", f"Portaria {c.act_number} — {k}", c.legal_basis))
        if c.publication_date:
            out.append(_ev(c.publication_date, "BENEFICIO", f"Publicação da {k.lower()}", c.publication_media or ""))
    for b in Benefit.objects.filter(beneficiary=person).select_related("payroll_group"):
        out.append(_ev(b.start_date, "BENEFICIO", f"Início do benefício — {b.get_kind_display()}",
                       f"R$ {b.amount} · folha {b.payroll_group.code} · {b.get_status_display()}"))
        for e in b.events.all():
            out.append(_ev(e.date, "BENEFICIO", f"{e.get_kind_display()} do benefício", e.justification[:200]))
    for lb in person.legacy_benefits.all():
        out.append(_ev(lb.start_date, "BENEFICIO", f"{lb.get_kind_display()} (importada da base atuarial)",
                       f"R$ {lb.amount}" if lb.amount else ""))
    for d in Dependency.objects.filter(holder=person).select_related("dependent"):
        out.append(_ev(d.start_date, "PESSOAL", f"Dependente: {d.dependent.name}", d.get_kind_display()))
    if person.death_date:
        out.append(_ev(person.death_date, "PESSOAL", "Óbito", person.death_certificate or ""))
    for b in Benefit.objects.filter(instituidor=person).select_related("beneficiary"):
        out.append(_ev(b.start_date, "BENEFICIO", f"Pensão deixada para {b.beneficiary.name}",
                       f"R$ {b.amount}" + (f" · cota {b.percent}%" if b.percent else "")))
    for doc in Document.objects.filter(person=person, superseded=False):
        out.append(_ev(doc.created_at.date(), "DOCUMENTO", f"Documento: {doc.get_doc_type_display()}", doc.file_name))
    order = {"PESSOAL": 0, "PREVIDENCIA": 1, "FUNCIONAL": 2, "FOLHA": 3, "BENEFICIO": 4, "DOCUMENTO": 5}
    return sorted(out, key=lambda e: (e["data"] or "9999", order.get(e["grupo"], 9)))


def summary(person) -> dict:
    """Cabeçalho e Ficha de Admissão da Pasta Funcional: situação, vínculo atual, nomeação/posse, endereço, conta,
    óbito e pensões deixadas."""
    from apps.concessao.models import Benefit
    from apps.employment.models import EmploymentLink

    links = list(EmploymentLink.objects.filter(person=person).select_related("organ", "position", "workplace")
                 .prefetch_related("events").order_by("-ente_start"))
    active = next((lk for lk in links if lk.status == "ATIVO"), None)
    main = active or (links[0] if links else None)
    benefits = list(Benefit.objects.filter(beneficiary=person, status="ATIVO"))
    if person.death_date:
        situ = "Falecido(a)"
    elif active:
        situ = "Ativo"
    elif any(b.kind == "APOSENTADORIA" for b in benefits) or person.legacy_benefits.filter(kind="APOSENTADORIA").exists():
        situ = "Aposentado(a)"
    elif benefits or person.legacy_benefits.filter(kind="PENSAO").exists():
        situ = "Pensionista"
    elif links:
        situ = "Ex-servidor(a)"
    else:
        situ = "Sem vínculo"

    def link_info(lk):
        from apps.pessoal.services import scale_for

        amount, origin = scale_for(lk, timezone.localdate())
        ev = {e.event_type: e for e in sorted(lk.events.all(), key=lambda e: e.start_date)}
        nom, pos = ev.get("NOMEACAO"), ev.get("POSSE")
        return {
            "id": str(lk.pk), "matricula": lk.registration, "cargo": lk.position.name, "orgao": lk.organ.name,
            "lotacao": lk.workplace.name if lk.workplace_id else "", "nivel": lk.class_level, "admissao": lk.ente_start,
            "servico_publico": lk.public_service_start, "massa": lk.get_segment_display(), "regime": lk.get_regime_display(),
            "tipo": lk.get_link_type_display(), "forma": lk.get_admission_form_display(), "status": lk.get_status_display(),
            "ativo": lk.status == "ATIVO", "carga_horaria": lk.weekly_hours, "fim": lk.end_date, "motivo_fim": lk.end_reason,
            "vencimento": {"valor": str(amount) if amount is not None else None, "origem": origin},
            "nomeacao": {"data": nom.start_date, "ato": " ".join(x for x in (nom.act_type, nom.act_number) if x),
                         "data_ato": nom.act_date, "publicacao": nom.publication} if nom else None,
            "posse": {"data": pos.start_date} if pos else None,
        }

    addr = person.addresses.filter(valid_to__isnull=True).order_by("-valid_from").first()
    acc = person.bank_accounts.filter(valid_to__isnull=True).select_related("bank").order_by("-valid_from").first()
    pensions = Benefit.objects.filter(instituidor=person).select_related("beneficiary")
    legacy_p = [lb for lb in person.legacy_benefits.model.objects.filter(instituidor=person).select_related("beneficiary")]
    return {
        "situacao": situ, "tem_foto": bool(person.photo),
        "vinculo_ativo": link_info(main) if main else None,
        "outros_vinculos": [link_info(lk) for lk in links if lk is not main],
        "vinculos": len(links),
        "beneficios_ativos": [{"tipo": b.get_kind_display(), "valor": str(b.amount)} for b in benefits],
        "endereco": {"logradouro": addr.street, "numero": addr.number, "complemento": addr.complement,
                     "bairro": addr.district, "cidade": addr.city, "uf": addr.uf, "cep": addr.cep} if addr else None,
        "conta": {"banco": f"{acc.bank.code} - {acc.bank.name}", "agencia": acc.branch + (f"-{acc.branch_digit}" if acc.branch_digit else ""),
                  "conta": acc.account + (f"-{acc.account_digit}" if acc.account_digit else ""),
                  "tipo": acc.get_account_type_display()} if acc else None,
        "obito": {"data": person.death_date, "certidao": person.death_certificate},
        "pensoes": [{"beneficiario": b.beneficiary.name, "inicio": b.start_date, "valor": str(b.amount),
                     "situacao": b.get_status_display()} for b in pensions]
        + [{"beneficiario": lb.beneficiary.name, "inicio": lb.start_date, "valor": str(lb.amount or ""),
            "situacao": "Importada da base atuarial"} for lb in legacy_p],
    }


ABSENCE_TYPES = ("LICENCA", "AFASTAMENTO", "FALTAS", "SUSPENSAO", "DISPONIBILIDADE", "CESSAO", "RETORNO")


def folder_extras(person, keys: set) -> dict:
    """Abas Remuneração, Férias e Afastamentos e Benefícios da Pasta Funcional (cada parte só com a permissão)."""
    from apps.employment.models import FunctionalEvent

    out = {"contracheques": None, "afastamentos": [], "beneficios": None}
    evs = (FunctionalEvent.objects.filter(link__person=person, event_type__in=ABSENCE_TYPES)
           .select_related("link").order_by("-start_date"))
    out["afastamentos"] = [{"tipo": e.get_event_type_display(), "codigo": e.event_type, "inicio": e.start_date,
                            "fim": e.end_date, "dias": e.days, "remunerado": e.with_pay, "conta_tempo": e.counts_as_service,
                            "matricula": e.link.registration, "descricao": e.description,
                            "ato": " ".join(x for x in (e.act_type, e.act_number) if x)} for e in evs]
    if "ativos.folha:visualizar" in keys:
        from apps.pessoal.models import ActivePayslip

        slips = (ActivePayslip.objects.filter(person=person).select_related("run", "run__organ")
                 .order_by("-run__year", "-run__month")[:36])
        out["contracheques"] = [{"id": str(x.pk), "folha": str(x.run_id), "competencia": f"{x.run.month:02d}/{x.run.year}",
                                 "orgao": x.run.organ.name, "matricula": x.registration, "situacao": x.run.get_status_display(),
                                 "proventos": str(x.gross), "descontos": str(x.discounts), "liquido": str(x.net)}
                                for x in slips]
    if "concessao.beneficios:visualizar" in keys or "cadastros.segurados:visualizar" in keys:
        from apps.concessao.models import Benefit, Concession

        out["beneficios"] = {
            "beneficios": [{"tipo": b.get_kind_display(), "inicio": b.start_date, "valor": str(b.amount),
                            "situacao": b.get_status_display(), "fundamento": b.legal_basis,
                            "instituidor": b.instituidor.name if b.instituidor_id else ""}
                           for b in Benefit.objects.filter(beneficiary=person).select_related("instituidor")],
            "importados": [{"tipo": lb.get_kind_display(), "inicio": lb.start_date, "valor": str(lb.amount or ""),
                            "implantado": lb.implanted} for lb in person.legacy_benefits.all()],
            "processos": [{"id": str(c.pk), "tipo": c.get_kind_display(), "etapa": c.get_stage_display(),
                           "processo": c.process.code if c.process_id else "", "aberto": c.process.opened_date if c.process_id else None}
                          for c in Concession.objects.filter(person=person).select_related("process").order_by("-created_at")],
        }
    return out
