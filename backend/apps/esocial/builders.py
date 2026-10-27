"""
Montagem dos XMLs dos eventos do eSocial RPPS.

A ordem dos elementos segue o leiaute S-1.3. Os campos obrigatórios ausentes viram PENDÊNCIAS (o evento não
pode ser exportado enquanto houver pendência). Quando os XSDs oficiais forem copiados para
backend/apps/esocial/xsd/ o XML também é validado contra o esquema (ver validation.py).

Códigos de tabelas do eSocial (Tabelas 03, 07, 25, 26 e incidências das rubricas) vêm do cadastro: o SIST
apenas sugere valores, que devem ser conferidos com o leiaute oficial vigente.
"""
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from apps.core.validators import is_valid_cpf, only_digits

ROOTS = {
    "S-1010": "evtTabRubrica", "S-1207": "evtBenPrRP", "S-1210": "evtPgtos", "S-1299": "evtFechaEvPer",
    "S-2400": "evtCdBenefIn", "S-2410": "evtCdBenIn", "S-2420": "evtCdBenTerm",
}
PLAN_BY_SEGMENT = {"FINANCEIRO": "2", "PREVIDENCIARIO": "1", "COMPRA_VIDAS": "1"}  # tpPlanRP
SEX = {1: "F", 2: "M"}  # cadastro (SPREV) -> eSocial
# Tabela 07 (tipos de dependente) — conferir com o leiaute vigente
DEP_TYPE = {1: "01", 2: "02", 3: "03", 4: "03", 5: "09", 6: "03", 7: "03", 8: "06", 9: "06", 10: "10", 11: "06",
            12: "12", 99: "99"}


@dataclass
class Ctx:
    institution: object
    version: str
    environment: int
    nr_insc: str
    pend: list = field(default_factory=list)

    @classmethod
    def load(cls, institution) -> "Ctx":
        from apps.institutions.services import get_parameter

        nr = only_digits(str(get_parameter(institution, "esocial.nr_insc") or institution.cnpj or ""))
        c = cls(institution, str(get_parameter(institution, "esocial.versao") or "S_01_03_00"),
                int(get_parameter(institution, "esocial.ambiente") or 2), nr)
        return c

    def fresh(self) -> "Ctx":
        return Ctx(self.institution, self.version, self.environment, self.nr_insc)


def d(v) -> str:
    return v.isoformat() if isinstance(v, (date, datetime)) else str(v or "")


def money(v) -> str:
    return f"{Decimal(v):.2f}"


class Node:
    """Atalhos para montar o XML registrando pendências de campos obrigatórios."""

    def __init__(self, ctx: Ctx, el: ET.Element):
        self.ctx, self.el = ctx, el

    def child(self, tag) -> "Node":
        return Node(self.ctx, ET.SubElement(self.el, tag))

    def req(self, tag, value, label):
        if value in (None, ""):
            self.ctx.pend.append(f"{label} não informado(a).")
            return
        ET.SubElement(self.el, tag).text = str(value)

    def opt(self, tag, value):
        if value not in (None, ""):
            ET.SubElement(self.el, tag).text = str(value)


def _root(ctx: Ctx, event_type: str, event_id: str) -> tuple[ET.Element, Node]:
    name = ROOTS[event_type]
    root = ET.Element("eSocial", xmlns=f"http://www.esocial.gov.br/schema/evt/{name}/v_{ctx.version}")
    evt = ET.SubElement(root, name, Id=event_id)
    return root, Node(ctx, evt)


def _ide_evento(n: Node, retif_receipt: str | None, *, retif=True, apur: tuple[str, str] | None = None,
                per_apur: str | None = None):
    ide = n.child("ideEvento")
    if retif:
        ide.req("indRetif", "2" if retif_receipt else "1", "Indicador de retificação")
        ide.opt("nrRecibo", retif_receipt)
    if apur:
        ide.req("indApuracao", apur[0], "Indicador de apuração")
        ide.req("perApur", apur[1], "Período de apuração")
    elif per_apur:
        ide.req("perApur", per_apur, "Período de apuração")
    ide.req("tpAmb", n.ctx.environment, "Ambiente")
    ide.req("procEmi", "1", "Processo de emissão")
    ide.req("verProc", "SIST-FOPAG-1.0", "Versão do processo")


def _ide_empregador(n: Node):
    e = n.child("ideEmpregador")
    e.req("tpInsc", "1", "Tipo de inscrição")
    if len(n.ctx.nr_insc) != 14:
        n.ctx.pend.append("CNPJ da instituição não cadastrado (Administração › Instituição ou parâmetro esocial.nr_insc).")
    e.req("nrInsc", n.ctx.nr_insc, "CNPJ do empregador")


def _cpf(n: Node, tag: str, cpf: str, who: str):
    if not is_valid_cpf(cpf or ""):
        n.ctx.pend.append(f"CPF inválido: {who}.")
    n.req(tag, cpf, f"CPF de {who}")


def to_string(root: ET.Element) -> str:
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


# ------------------------------------------------------------------ S-2400 cadastro do beneficiário
def s2400(ctx: Ctx, event_id: str, person, retif_receipt=None) -> str:
    from apps.people.models import Address, Dependency

    root, evt = _root(ctx, "S-2400", event_id)
    _ide_evento(evt, retif_receipt)
    _ide_empregador(evt)
    b = evt.child("beneficiario")
    _cpf(b, "cpfBenef", person.cpf, person.name or "beneficiário")
    b.req("nmBenefic", person.name, "Nome do beneficiário")
    b.req("dtNascto", d(person.birth_date), "Data de nascimento")
    first = person.benefits.order_by("start_date").first()
    b.req("dtInicio", d(first.start_date) if first else "", "Início do primeiro benefício")
    b.req("sexo", SEX.get(person.sex), "Sexo")
    b.req("racaCor", person.race or 6, "Raça/cor")
    incap = person.is_invalid or person.has_disability
    b.req("incFisMen", "S" if incap else "N", "Incapacidade física ou mental")
    if incap:
        b.opt("dtIncFisMen", d(person.invalidity_date))
    today = timezone.localdate()
    addr = (Address.objects.filter(person=person, valid_from__lte=today)
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gte=today)).order_by("-valid_from").first())
    end = b.child("endereco").child("brasil")
    if addr is None:
        ctx.pend.append("Endereço vigente não cadastrado.")
    else:
        end.req("dscLograd", addr.street, "Logradouro")
        end.req("nrLograd", addr.number or "S/N", "Número")
        end.opt("complemento", addr.complement)
        end.opt("bairro", addr.district)
        end.req("cep", only_digits(addr.cep), "CEP")
        end.req("codMunic", addr.city_ibge, "Código IBGE do município do endereço")
        end.req("uf", addr.uf, "UF do endereço")
    deps = (Dependency.objects.filter(holder=person).filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
            .select_related("dependent"))
    for dep in deps:
        p = dep.dependent
        dn = b.child("dependente")
        dn.req("tpDep", DEP_TYPE.get(dep.kind, "99"), "Tipo de dependente")
        dn.req("nmDep", p.name, f"Nome do dependente ({p.cpf})")
        dn.req("dtNascto", d(p.birth_date), f"Nascimento do dependente {p.name}")
        dn.opt("cpfDep", p.cpf)
        dn.opt("sexoDep", SEX.get(p.sex))
        dn.req("depIRRF", "S" if dep.tax_dependent else "N", "Dependente para IR")
        dn.req("incFisMen", "S" if (p.is_invalid or p.has_disability) else "N", "Incapacidade do dependente")
    return to_string(root)


# ------------------------------------------------------------------ S-2410 início do benefício
def s2410(ctx: Ctx, event_id: str, benefit, retif_receipt=None, cad_ini: bool = False) -> str:
    root, evt = _root(ctx, "S-2410", event_id)
    _ide_evento(evt, retif_receipt)
    _ide_empregador(evt)
    ben = evt.child("beneficiario")
    _cpf(ben, "cpfBenef", benefit.beneficiary.cpf, benefit.beneficiary.name or "beneficiário")
    ben.opt("matricula", benefit.registration)
    info = evt.child("infoBenInicio")
    info.req("cadIni", "S" if cad_ini else "N", "Cadastramento inicial")
    info.req("nrBeneficio", benefit.esocial_nr, "Número do benefício")
    info.req("dtIniBeneficio", d(benefit.start_date), "Início do benefício")
    pub = benefit.concession.publication_date if benefit.concession_id else None
    info.opt("dtPublic", d(pub) if pub else "")
    dados = info.child("dadosBeneficio")
    if benefit.esocial_tp_beneficio and len(benefit.esocial_tp_beneficio) != 4:
        ctx.pend.append("Tipo de benefício (Tabela 25) deve ter 4 dígitos.")
    dados.req("tpBeneficio", benefit.esocial_tp_beneficio,
              "Tipo de benefício do eSocial (Tabela 25) — informe em Folha › Beneficiários")
    dados.req("tpPlanRP", PLAN_BY_SEGMENT.get(benefit.payroll_group.segment), "Plano de segregação")
    dados.opt("dsc", (benefit.legal_basis or "")[:255])
    if benefit.concession_id and benefit.concession.judicial:
        dados.opt("indDecJud", "S")
    if benefit.kind == "PENSAO":
        pm = dados.child("infoPenMorte")
        pm.req("tpPenMorte", "2" if benefit.end_date else "1", "Tipo da pensão")
        inst = pm.child("instPenMorte")
        ip = benefit.instituidor
        _cpf(inst, "cpfInst", ip.cpf if ip else "", "instituidor")
        inst.req("dtInst", d(ip.death_date) if ip and ip.death_date else "", "Data do óbito do instituidor")
    return to_string(root)


# ------------------------------------------------------------------ S-2420 término
def s2420(ctx: Ctx, event_id: str, benefit, retif_receipt=None) -> str:
    root, evt = _root(ctx, "S-2420", event_id)
    _ide_evento(evt, retif_receipt)
    _ide_empregador(evt)
    ide = evt.child("ideBeneficio")
    _cpf(ide, "cpfBenef", benefit.beneficiary.cpf, benefit.beneficiary.name or "beneficiário")
    ide.req("nrBeneficio", benefit.esocial_nr, "Número do benefício")
    term = evt.child("infoBenTermino")
    term.req("dtTermBeneficio", d(benefit.end_date), "Data de término")
    term.req("mtvTermino", benefit.esocial_mtv_termino,
             "Motivo do término (Tabela 26) — informe em Folha › Beneficiários")
    return to_string(root)


# ------------------------------------------------------------------ S-1010 rubrica
TP_RUBR = {"PROVENTO": "1", "DESCONTO": "2", "INFORMATIVA": "3"}


def s1010(ctx: Ctx, event_id: str, rubric, retif_receipt=None) -> str:
    root, evt = _root(ctx, "S-1010", event_id)
    _ide_evento(evt, None, retif=False)
    _ide_empregador(evt)
    inc = evt.child("infoRubrica").child("inclusao")
    ide = inc.child("ideRubrica")
    ide.req("codRubr", rubric.code, "Código da rubrica")
    ide.req("ideTabRubr", "SIST", "Tabela de rubricas")
    ide.req("iniValid", rubric.valid_from.strftime("%Y-%m"), "Início da validade")
    if rubric.valid_to:
        ide.opt("fimValid", rubric.valid_to.strftime("%Y-%m"))
    dados = inc.child("dadosRubrica")
    dados.req("dscRubr", rubric.name, "Descrição da rubrica")
    dados.req("natRubr", rubric.esocial_nature, f"Natureza da rubrica {rubric.code} (Tabela 03) — Folha › Rubricas")
    dados.req("tpRubr", TP_RUBR[rubric.kind], "Tipo da rubrica")
    dados.req("codIncCP", rubric.esocial_inc_cp or "00", "Incidência CP")
    dados.req("codIncIRRF", rubric.esocial_inc_irrf, f"Incidência IRRF da rubrica {rubric.code}")
    dados.req("codIncFGTS", "00", "Incidência FGTS")
    dados.req("codIncCPRP", rubric.esocial_inc_cprp, f"Incidência RPPS da rubrica {rubric.code}")
    dados.req("tetoRemun", "N", "Teto remuneratório")
    return to_string(root)


# ------------------------------------------------------------------ S-1207 benefícios (folha)
def period_of(run) -> tuple[str, str]:
    c = run.competence
    return ("2", str(c.year)) if run.kind == "DECIMO" else ("1", f"{c.year}-{c.month:02d}")


def dm_dev_id(run, entry) -> str:
    c = run.competence
    return f"{'D' if run.kind == 'DECIMO' else 'M'}{c.year}{c.month:02d}{entry.benefit.esocial_nr}"[:30]


def s1207(ctx: Ctx, event_id: str, run, person, retif_receipt=None) -> str:
    root, evt = _root(ctx, "S-1207", event_id)
    _ide_evento(evt, retif_receipt, apur=period_of(run))
    _ide_empregador(evt)
    ib = evt.child("ideBenef")
    _cpf(ib, "cpfBenef", person.cpf, person.name or "beneficiário")
    for e in run.entries.filter(beneficiary=person).select_related("benefit").prefetch_related("items__rubric"):
        dm = evt.child("dmDev")
        dm.req("ideDmDev", dm_dev_id(run, e) if e.benefit.esocial_nr else "", "Identificador do demonstrativo")
        dm.req("nrBeneficio", e.benefit.esocial_nr, f"Número do benefício de {person.name} (gere o S-2410)")
        if any(i.rubric.calc == "IRRF_RRA" for i in e.items.all()):
            dm.opt("indRRA", "S")
        est = dm.child("infoPerApur").child("ideEstab")
        est.req("tpInsc", "1", "Tipo de inscrição do estabelecimento")
        est.req("nrInsc", ctx.nr_insc, "CNPJ do estabelecimento")
        for it in e.items.all():
            ir = est.child("itensRemun")
            ir.req("codRubr", it.code, "Código da rubrica")
            ir.req("ideTabRubr", "SIST", "Tabela de rubricas")
            ir.req("vrRubr", money(it.amount), "Valor da rubrica")
            ir.req("indApurIR", "0", "Indicador de apuração do IR")
    return to_string(root)


# ------------------------------------------------------------------ S-1210 pagamentos
def s1210(ctx: Ctx, event_id: str, run, person, retif_receipt=None) -> str:
    root, evt = _root(ctx, "S-1210", event_id)
    pay = run.payment_date
    _ide_evento(evt, retif_receipt, per_apur=pay.strftime("%Y-%m") if pay else "")
    _ide_empregador(evt)
    ib = evt.child("ideBenef")
    _cpf(ib, "cpfBenef", person.cpf, person.name or "beneficiário")
    for e in run.entries.filter(beneficiary=person).select_related("benefit"):
        if e.net <= 0:
            continue
        pg = ib.child("infoPgto")
        pg.req("dtPgto", d(pay), "Data do pagamento (registre o pagamento da folha)")
        pg.req("tpPgto", "5", "Tipo de pagamento")
        pg.req("perRef", period_of(run)[1], "Período de referência")
        pg.req("ideDmDev", dm_dev_id(run, e) if e.benefit.esocial_nr else "", "Identificador do demonstrativo")
        pg.req("vrLiq", money(e.net), "Valor líquido")
    return to_string(root)


# ------------------------------------------------------------------ S-1299 fechamento
def s1299(ctx: Ctx, event_id: str, period: str, has_remun: bool, has_pgtos: bool) -> str:
    root, evt = _root(ctx, "S-1299", event_id)
    apur = ("2", period) if len(period) == 4 else ("1", period)
    _ide_evento(evt, None, retif=False, apur=apur)
    _ide_empregador(evt)
    f = evt.child("infoFech")
    f.req("evtRemun", "S" if has_remun else "N", "Houve remuneração")
    f.req("evtPgtos", "S" if has_pgtos else "N", "Houve pagamentos")
    f.req("evtComProd", "N", "Comercialização de produção")
    f.req("evtContratAvNP", "N", "Contratação de avulsos")
    f.req("evtInfoComplPer", "N", "Informações complementares")
    return to_string(root)
