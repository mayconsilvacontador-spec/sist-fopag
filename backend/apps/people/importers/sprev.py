"""
Importação de segurados a partir da base de dados da avaliação atuarial
(leiaute padrão SPREV) — formato que todo RPPS já gera, qualquer que seja o
sistema de origem.

Arquivos aceitos (identificados pelo cabeçalho): Servidores, Aposentados,
Pensionistas e Dependentes. CSV (; ou ,) ou Excel. Cabeçalho = nomes das
variáveis SPREV. Colunas extras de nome (NOME, NO_SERVIDOR...) são aproveitadas
quando existirem — o leiaute oficial não traz o nome das pessoas.

O que vira o quê:
- Servidores   -> pessoa + ente/órgão/cargo (criados se não existirem) + vínculo ativo
- Aposentados  -> pessoa + benefício importado (aguarda implantação na Fase 4)
- Pensionistas -> pensionista + instituidor (com óbito) + benefício importado
- Dependentes  -> pessoa + dependência do segurado titular

Regras: pessoa existente (mesmo CPF) nunca é sobrescrita — só campos vazios
são completados; divergências viram aviso. Vínculo já existente (órgão +
matrícula) é ignorado. Cada linha é independente: erro numa linha não impede
as outras.

A validação executa exatamente o mesmo código dentro de uma transação que é
desfeita no final (nada é gravado) — o relatório reflete fielmente o resultado.
"""
from django.utils import timezone
import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.core.validators import is_valid_cpf, only_digits

from .complementar import COMPLEMENT_LABELS, COMPLEMENT_ORDER, ComplementMixin, detect_complement

KINDS = {
    "ID_SERVIDOR_CPF": "servidores",
    "ID_APOSENTADO_CPF": "aposentados",
    "ID_PENSIONISTA_CPF": "pensionistas",
    "ID_DEPENDENTE_CPF": "dependentes",
}
CPF_COLUMN = {kind: col for col, kind in KINDS.items()}
ORDER = ["servidores", "aposentados", "pensionistas", "dependentes"] + COMPLEMENT_ORDER
LABELS = {"servidores": "Servidores", "aposentados": "Aposentados", "pensionistas": "Pensionistas",
          "dependentes": "Dependentes", **COMPLEMENT_LABELS}
NAME_COLUMNS = {
    "servidores": ["NO_SERVIDOR", "NOME_SERVIDOR", "NOME"],
    "aposentados": ["NO_APOSENTADO", "NOME_APOSENTADO", "NOME"],
    "pensionistas": ["NO_PENSIONISTA", "NOME_PENSIONISTA", "NOME"],
    "dependentes": ["NO_DEPENDENTE", "NOME_DEPENDENTE", "NOME"],
}
INVALID_DEP_KINDS = {4, 7, 9}
CHILD_LIKE_KINDS = {3, 4, 6, 7, 8, 9, 10, 11}
MAX_MESSAGES = 2000


class RowError(Exception):
    pass


# --------------------------------------------------------------------------- leitura
def read_table(content: bytes, filename: str) -> list[dict]:
    """Lê CSV ou XLSX e devolve linhas como dict (cabeçalho em maiúsculas)."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows = list(wb.active.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(h or "").strip().upper() for h in rows[0]]
        return [dict(zip(header, r)) for r in rows[1:] if any(v not in (None, "") for v in r)]
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:5000]
    delimiter = max([";", ",", "\t", "|"], key=sample.count)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []
    header = [h.strip().upper() for h in rows[0]]
    return [dict(zip(header, r)) for r in rows[1:] if any(c.strip() for c in r)]


def detect_kind(rows: list[dict]) -> str | None:
    if not rows:
        return None
    keys = set(rows[0].keys())
    if {"CO_SITUACAO", "DT_SITUACAO"} & keys:
        return "baixas"
    for col, kind in KINDS.items():
        if col in keys:
            return kind
    return detect_complement(keys)


# --------------------------------------------------------------------------- conversões
def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _cpf(v) -> str:
    d = only_digits(_s(v).split(".")[0] if isinstance(v, float) else _s(v))
    return d.zfill(11) if d else ""


def _int(v, allowed=None) -> int | None:
    s = _s(v)
    if not s:
        return None
    try:
        n = int(float(s.replace(",", ".")))
    except ValueError:
        raise RowError(f"valor numérico inválido: {s!r}")
    if allowed is not None and n not in allowed:
        raise RowError(f"código {n} fora da tabela")
    return n


def _date(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _s(v)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d%m%Y", "%Y%m%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    raise RowError(f"data inválida: {s!r}")


def _dec(v) -> Decimal | None:
    s = _s(v).replace("R$", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise RowError(f"valor monetário inválido: {s!r}")


def _get(row, *names):
    for n in names:
        if n in row and _s(row[n]):
            return row[n]
    return None


# --------------------------------------------------------------------------- importador
@dataclass
class Report:
    arquivos: list = field(default_factory=list)
    erros: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    resumo: dict = field(default_factory=lambda: {
        "pessoas_novas": 0, "pessoas_completadas": 0, "pessoas_sem_nome": 0, "entes_criados": 0,
        "orgaos_criados": 0, "cargos_criados": 0, "vinculos": 0, "vinculos_existentes": 0,
        "beneficios": 0, "dependencias": 0,
    })

    def as_dict(self):
        return {"arquivos": self.arquivos, "erros": self.erros[:MAX_MESSAGES], "avisos": self.avisos[:MAX_MESSAGES],
                "total_erros": len(self.erros), "total_avisos": len(self.avisos), "resumo": self.resumo}


class SprevImporter(ComplementMixin):
    def __init__(self, institution, batch, source_system: str):
        self.inst, self.batch, self.source = institution, batch, source_system
        self.report = Report()
        self._ctx = {}

    # ---- API
    def run(self, tables: list[tuple[str, list[dict]]], apply: bool) -> dict:
        """tables: [(nome do arquivo, linhas)]. apply=False -> valida e desfaz tudo."""
        from apps.institutions.services import active_segments

        self.segments = set(active_segments(self.inst))
        by_kind = {}
        for name, rows in tables:
            kind = detect_kind(rows)
            if kind is None:
                self.report.arquivos.append({"nome": name, "tipo": "Não reconhecido", "linhas": len(rows),
                                             "validas": 0, "erros": 0})
                self.report.erros.append({"arquivo": name, "linha": "-", "cpf": "",
                                          "mensagem": "Cabeçalho não reconhecido: use o leiaute SPREV (Servidores, "
                                                      "Aposentados, Pensionistas, Dependentes) ou um dos arquivos "
                                                      "complementares do SIST (complemento, endereços, contas, "
                                                      "averbações, histórico funcional)."})
                continue
            if kind == "baixas":
                self.report.arquivos.append({"nome": name, "tipo": "Baixas (ignorado)", "linhas": len(rows),
                                             "validas": 0, "erros": 0})
                self.report.avisos.append({"arquivo": name, "linha": "-", "cpf": "",
                                           "mensagem": "Arquivos de baixas não são importados (são histórico)."})
                continue
            by_kind.setdefault(kind, []).append((name, rows))

        with transaction.atomic():
            for kind in ORDER:
                for name, rows in by_kind.get(kind, []):
                    self._run_file(kind, name, rows)
            if not apply:
                transaction.set_rollback(True)
        return self.report.as_dict()

    def _run_file(self, kind, name, rows):
        handler = getattr(self, f"_row_{kind}")
        ok = errors = 0
        for i, row in enumerate(rows, start=2):  # linha 1 = cabeçalho
            cpf = ""
            try:
                with transaction.atomic():
                    cpf = handler(row, name, i) or ""
                ok += 1
            except RowError as exc:
                errors += 1
                self._msg("erros", name, i, cpf or _cpf(row.get(CPF_COLUMN.get(kind, "CPF"))), str(exc))
            except Exception as exc:  # erro inesperado numa linha não derruba o lote
                errors += 1
                self._msg("erros", name, i, cpf, f"erro ao gravar: {exc.__class__.__name__}: {exc}")
        self.report.arquivos.append({"nome": name, "tipo": LABELS[kind], "linhas": len(rows), "validas": ok,
                                     "erros": errors})

    def _msg(self, level, arquivo, linha, cpf, mensagem):
        getattr(self.report, level).append({"arquivo": arquivo, "linha": linha,
                                            "cpf": f"***.{cpf[3:6]}.{cpf[6:9]}-**" if len(cpf) == 11 else "",
                                            "mensagem": mensagem})

    # ---- pessoas
    def _person(self, row, kind, name, line, *, cpf_col, sex_col=None, birth_col=None, marital_col=None,
                pis_col=None, invalid=False, death=None, name_cols=None):
        from apps.people.models import Person

        cpf = _cpf(row.get(cpf_col))
        if not cpf:
            raise RowError(f"{cpf_col} não informado")
        if not is_valid_cpf(cpf):
            raise RowError(f"CPF inválido ({cpf_col})")
        sex = _int(row.get(sex_col), {1, 2}) if sex_col else None
        birth = _date(row.get(birth_col)) if birth_col else None
        marital = _int(row.get(marital_col), {1, 2, 3, 4, 5, 6, 9}) if marital_col else None
        pis = only_digits(_s(row.get(pis_col))) if pis_col else ""
        pis = pis if len(pis) == 11 else ""
        pname = _s(_get(row, *(name_cols or NAME_COLUMNS[kind])))[:150]

        person = Person.objects.filter(institution=self.inst, cpf=cpf).first()
        if person is None:
            if birth is None:
                raise RowError(f"{birth_col} não informada (obrigatória para nova pessoa)")
            if sex is None:
                raise RowError(f"{sex_col} não informado (obrigatório para nova pessoa)")
            if death and death < birth:
                raise RowError("data do óbito anterior ao nascimento")
            person = Person.objects.create(
                institution=self.inst, cpf=cpf, name=pname, birth_date=birth, sex=sex, marital_status=marital,
                pis_pasep=pis, is_invalid=invalid, death_date=death,
                notes=f"Importado de: {self.source}.",
            )
            self.report.resumo["pessoas_novas"] += 1
            if not pname:
                self.report.resumo["pessoas_sem_nome"] += 1
            return person

        changed = []
        for attr, value in (("name", pname), ("pis_pasep", pis), ("marital_status", marital), ("death_date", death)):
            if value and not getattr(person, attr):
                setattr(person, attr, value)
                changed.append(attr)
        if invalid and not person.is_invalid:
            person.is_invalid = True
            changed.append("is_invalid")
        if birth and person.birth_date != birth:
            self._msg("avisos", name, line, cpf, "data de nascimento diverge do cadastro (mantida a atual)")
        if sex and person.sex != sex:
            self._msg("avisos", name, line, cpf, "sexo diverge do cadastro (mantido o atual)")
        if changed:
            person.save()
            self.report.resumo["pessoas_completadas"] += 1
        return person

    def _segment(self, row):
        fundo = _int(row.get("CO_TIPO_FUNDO"), {1, 2, 3})
        segment = "FINANCEIRO" if fundo == 2 else "PREVIDENCIARIO"
        if segment not in self.segments:
            raise RowError("CO_TIPO_FUNDO = 2 (repartição), mas a instituição não tem Plano Financeiro ativo")
        return segment

    # ---- estrutura (ente, órgão, cargo)
    def _organ(self, row, cnpj_col):
        from apps.cadastros.models import Ente, Organ

        ente_name = _s(row.get("NO_ENTE"))[:150] or self.inst.ente_name or "Ente não informado"
        key = ("ente", ente_name.upper())
        ente = self._ctx.get(key)
        if ente is None:
            ente = Ente.objects.filter(institution=self.inst, name__iexact=ente_name).first()
            if ente is None:
                uf = _s(row.get("SG_UF")).upper()[:2]
                ente = Ente.objects.create(institution=self.inst, name=ente_name,
                                           ibge_code=only_digits(_s(row.get("CO_IBGE")))[:7], uf=uf)
                self.report.resumo["entes_criados"] += 1
            self._ctx[key] = ente

        cnpj = only_digits(_s(row.get(cnpj_col)))
        oname = _s(row.get("NO_ORGAO"))[:150]
        if not oname and not cnpj:
            raise RowError("órgão não informado (NO_ORGAO / CNPJ)")
        key = ("organ", cnpj or oname.upper())
        organ = self._ctx.get(key)
        if organ is None:
            qs = Organ.objects.filter(institution=self.inst)
            organ = (qs.filter(cnpj=cnpj).first() if cnpj else None) or (
                qs.filter(name__iexact=oname).first() if oname else None)
            if organ is None:
                organ = Organ.objects.create(
                    institution=self.inst, ente=ente, name=oname or f"Órgão CNPJ {cnpj}",
                    cnpj=cnpj if len(cnpj) == 14 else "",
                    poder=_int(row.get("CO_PODER"), {1, 2, 3, 4, 5, 6}) or 1,
                    tipo_poder=_int(row.get("CO_TIPO_PODER"), {1, 2}) or 1,
                )
                self.report.resumo["orgaos_criados"] += 1
            self._ctx[key] = organ
        return organ

    def _position(self, row):
        from apps.cadastros.models import Position

        name = _s(row.get("NO_CARGO"))[:150]
        if not name:
            raise RowError("NO_CARGO não informado")
        key = ("pos", name.upper())
        pos = self._ctx.get(key)
        if pos is None:
            pos = Position.objects.filter(institution=self.inst, name__iexact=name).first()
            if pos is None:
                pos = Position.objects.create(
                    institution=self.inst, name=name, career=_s(row.get("NO_CARREIRA"))[:150],
                    cargo_type=_int(row.get("CO_TIPO_CARGO"), set(range(1, 9))) or 7,
                )
                self.report.resumo["cargos_criados"] += 1
            self._ctx[key] = pos
        return pos

    # ---- linhas
    def _row_servidores(self, row, name, line):
        from apps.employment.models import EmploymentLink

        person = self._person(row, "servidores", name, line, cpf_col="ID_SERVIDOR_CPF", sex_col="CO_SEXO_SERVIDOR",
                              birth_col="DT_NASC_SERVIDOR", marital_col="CO_EST_CIVIL_SERVIDOR",
                              pis_col="ID_SERVIDOR_PIS_PASEP")
        registration = only_digits(_s(row.get("ID_SERVIDOR_MATRICULA")).split(".")[0]) or _s(row.get("ID_SERVIDOR_MATRICULA"))
        if not registration:
            raise RowError("ID_SERVIDOR_MATRICULA não informada")
        organ = self._organ(row, "NU_CNPJ_ORGAO")
        position = self._position(row)
        if EmploymentLink.objects.filter(institution=self.inst, organ=organ, registration=registration).exists():
            self.report.resumo["vinculos_existentes"] += 1
            self._msg("avisos", name, line, person.cpf, f"vínculo {registration} já existe no órgão — ignorado")
            return person.cpf

        ps = _date(row.get("DT_ING_SERV_PUB"))
        es = _date(row.get("DT_ING_ENTE")) or ps
        cs = _date(row.get("DT_ING_CARREIRA"))
        pos_start = _date(row.get("DT_ING_CARGO")) or es
        if not ps:
            raise RowError("DT_ING_SERV_PUB não informada")
        if ps <= person.birth_date:
            raise RowError("ingresso no serviço público anterior ao nascimento")
        if es < ps:
            raise RowError("DT_ING_ENTE anterior a DT_ING_SERV_PUB")
        if pos_start < es:
            raise RowError("DT_ING_CARGO anterior a DT_ING_ENTE")
        if cs and not (es <= cs <= pos_start):
            self._msg("avisos", name, line, person.cpf, "DT_ING_CARREIRA fora do intervalo ente/cargo — não importada")
            cs = None
        abono = _int(row.get("IN_ABONO_PERMANENCIA"), {1, 2})
        eligibility = _int(row.get("CO_CRITERIO_ELEGIBILIDADE"), {1, 2, 3, 4, 5, 8})
        EmploymentLink.objects.create(
            institution=self.inst, person=person, organ=organ, position=position, registration=registration[:20],
            link_type=_int(row.get("CO_TIPO_VINCULO"), {1, 2, 3, 4}) or 1,
            public_service_start=ps, ente_start=es, career_start=cs, position_start=pos_start,
            situation=_int(row.get("CO_SITUACAO_FUNCIONAL"), set(range(1, 12))) or 1,
            eligibility=eligibility if eligibility in (1, 2, 3, 4, 5) else 1,
            segment=self._segment(row),
            permanence_bonus_since=_date(row.get("DT_INICIO_ABONO")) if abono == 1 else None,
            complementary_pension=_int(row.get("IN_PREV_COMP"), {1, 2}) == 1,
            # vencimento base = base de cálculo informada na base atuarial (a conferir com a tabela de vencimentos)
            base_salary=_dec(row.get("VL_BASE_CALCULO")) or _dec(row.get("VL_REMUNERACAO")),
            notes=f"Importado de: {self.source} (lote {self.batch.pk}).",
        )
        self.report.resumo["vinculos"] += 1
        return person.cpf

    def _benefit(self, kind, row, beneficiary, instituidor, registration, start, amount):
        from apps.people.models import LegacyBenefit

        LegacyBenefit.objects.create(
            institution=self.inst, batch=self.batch, kind=kind, beneficiary=beneficiary, instituidor=instituidor,
            registration=registration[:30], segment=self._segment(row), start_date=start, amount=amount,
            raw={k: (v.isoformat() if isinstance(v, (date, datetime)) else _s(v)) for k, v in row.items()},
        )
        self.report.resumo["beneficios"] += 1

    def _row_aposentados(self, row, name, line):
        person = self._person(row, "aposentados", name, line, cpf_col="ID_APOSENTADO_CPF",
                              sex_col="CO_SEXO_APOSENTADO", birth_col="DT_NASC_APOSENTADO",
                              marital_col="CO_EST_CIVIL_APOSENTADO", pis_col="ID_APOSENT_PIS_PASEP",
                              invalid=_int(row.get("CO_CONDICAO_APOSENTADO"), {1, 2}) == 2)
        start = _date(row.get("DT_INICIO_APOSENTADORIA"))
        amount = _dec(row.get("VL_APOSENTADORIA"))
        if amount is None:
            self._msg("avisos", name, line, person.cpf, "VL_APOSENTADORIA não informado")
        self._benefit("APOSENTADORIA", row, person, None, _s(row.get("ID_APOSENTADO_MATRICULA")), start, amount)
        return person.cpf

    def _row_pensionistas(self, row, name, line):
        death = _date(row.get("DT_OBITO_INSTITUIDOR"))
        instituidor = self._person(row, "pensionistas", name, line, cpf_col="ID_INSTITUIDOR_CPF",
                                   sex_col="CO_SEXO_INSTITUIDOR", birth_col="DT_NASC_INSTITUIDOR",
                                   pis_col="ID_INSTITUIDOR_PIS_PASEP", death=death,
                                   name_cols=["NO_INSTITUIDOR", "NOME_INSTITUIDOR"])
        if not death:
            self._msg("avisos", name, line, instituidor.cpf, "DT_OBITO_INSTITUIDOR não informada")
        person = self._person(row, "pensionistas", name, line, cpf_col="ID_PENSIONISTA_CPF",
                              sex_col="CO_SEXO_PENSIONISTA", birth_col="DT_NASC_PENSIONISTA",
                              invalid=_int(row.get("CO_CONDICAO"), {1, 2}) == 2)
        self._benefit("PENSAO", row, person, instituidor, _s(row.get("ID_INSTITUIDOR_MATRICULA")),
                      _date(row.get("DT_INICIO_PENSAO")), _dec(row.get("VL_BENEF_PENSAO")))
        return person.cpf

    def _row_dependentes(self, row, name, line):
        from apps.people.models import Dependency, Person
        from apps.people.services import validate_dependency

        holder_cpf = _cpf(row.get("ID_SEGURADO_CPF"))
        holder = Person.objects.filter(institution=self.inst, cpf=holder_cpf).first() if holder_cpf else None
        if holder is None:
            raise RowError("segurado titular (ID_SEGURADO_CPF) não está no cadastro — importe antes o "
                           "arquivo de Servidores/Aposentados")
        kind = _int(row.get("CO_TIPO_DEPENDECIA"), {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 99})
        if kind is None:
            raise RowError("CO_TIPO_DEPENDECIA não informado")
        invalid = _int(row.get("CO_CONDICAO_DEPENDENTE"), {1, 2}) == 2 or kind in INVALID_DEP_KINDS
        dep = self._person(row, "dependentes", name, line, cpf_col="ID_DEPENDENTE_CPF", sex_col="CO_SEXO_DEPENDENTE",
                           birth_col="DT_NASC_DEPENDENTE", invalid=invalid)
        if Dependency.objects.filter(holder=holder, dependent=dep, end_date__isnull=True).exists():
            self._msg("avisos", name, line, dep.cpf, "dependência já cadastrada — ignorada")
            return dep.cpf
        if kind in CHILD_LIKE_KINDS:
            start, note = dep.birth_date, "Início da dependência = nascimento do dependente."
        else:
            ref = date(_int(row.get("NU_ANO")) or timezone.localdate().year, _int(row.get("NU_MES"), set(range(1, 13))) or 1, 1)
            start = max(ref, dep.birth_date)
            note = "Início da dependência PRESUMIDO (data-base da base atuarial) — confira com a documentação."
            self._msg("avisos", name, line, dep.cpf, "início da dependência presumido pela data-base — conferir")
        try:
            validate_dependency(holder, dep, kind, start)
        except Exception as exc:
            raise RowError(str(getattr(exc, "message", exc)))
        Dependency.objects.create(institution=self.inst, holder=holder, dependent=dep, kind=kind, start_date=start,
                                  notes=f"Importado de: {self.source}. {note}")
        self.report.resumo["dependencias"] += 1
        return dep.cpf
