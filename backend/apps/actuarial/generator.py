"""
Geração da base de dados para a avaliação atuarial (leiaute padrão SPREV).

Organização do ZIP gerado:

    FUNDO_CAPITALIZACAO/   Plano Previdenciário: massa própria + Compra de Vidas
                           (CO_TIPO_FUNDO = 1, como exige o leiaute oficial)
    FUNDO_REPARTICAO/      Plano Financeiro (CO_TIPO_FUNDO = 2)
    COMPLEMENTAR_COMPRA_VIDAS/
        <arquivos oficiais>        somente as vidas transferidas
        IDENTIFICACAO_VIDAS.csv    CPF/matrícula de cada vida e o lote que a transferiu
        LOTES.csv                  operações de Compra de Vidas
    RESUMO.csv · PENDENCIAS.csv · LEIA-ME.txt

Formato dos arquivos oficiais: CSV separado por ponto e vírgula, decimal com
vírgula, datas dd/mm/aaaa, UTF-8 — conforme orientações do dicionário.
"""
import calendar
import csv
import hashlib
import io
import zipfile
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.institutions.models import LifePurchase, Segment
from apps.institutions.services import active_segments

from . import layouts, sources
from .models import ActuarialBase

CAPITALIZACAO, REPARTICAO = "FUNDO_CAPITALIZACAO", "FUNDO_REPARTICAO"
COMPLEMENTAR = "COMPLEMENTAR_COMPRA_VIDAS"
# CO_TIPO_FUNDO: 1 - capitalização ou sem segregação · 2 - repartição (com segregação)
FUND_OF_SEGMENT = {
    Segment.FINANCEIRO: REPARTICAO,
    Segment.PREVIDENCIARIO: CAPITALIZACAO,
    Segment.COMPRA_VIDAS: CAPITALIZACAO,
}
FUND_CODE = {CAPITALIZACAO: 1, REPARTICAO: 2}
ID_COLUMNS = {
    "servidores": ("SERVIDOR", "ID_SERVIDOR_CPF", "ID_SERVIDOR_MATRICULA"),
    "aposentados": ("APOSENTADO", "ID_APOSENTADO_CPF", "ID_APOSENTADO_MATRICULA"),
    "pensionistas": ("PENSIONISTA", "ID_PENSIONISTA_CPF", "ID_PENSIONISTA_MATRICULA"),
    "dependentes": ("DEPENDENTE", "ID_DEPENDENTE_CPF", "ID_DEPENDENTE"),
}
CIVIL = 1  # CO_COMP_MASSA: RPPS de servidores civis


def _br(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, Decimal):
        return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}".replace(".", ",")
    if isinstance(value, bool):
        return "1" if value else "2"  # padrão do leiaute: 1 - Sim, 2 - Não
    return str(value)


def _csv(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def _common(institution, fund: str, ref: date) -> dict:
    return {
        "NU_ANO": ref.year,
        "NU_MES": ref.month,
        "CO_IBGE": institution.ibge_code or "",
        "NO_ENTE": institution.ente_name or "",
        "SG_UF": institution.uf or "",
        "CO_COMP_MASSA": CIVIL,
        "CO_TIPO_FUNDO": FUND_CODE[fund],
    }


def _segregated(segments) -> bool:
    return Segment.FINANCEIRO in segments


def generate(institution, year: int, month: int, notes: str = "") -> ActuarialBase:
    today = timezone.localdate()
    if not 1 <= month <= 12 or year < 1990 or (year, month) > (today.year, today.month):
        raise BusinessRuleError("Data-base inválida: informe uma competência até o mês atual.")

    ref = date(year, month, calendar.monthrange(year, month)[1])
    segments = active_segments(institution)
    ctx = sources.SourceContext(
        institution=institution, segments=segments, reference_date=ref,
        period_start=date(year - 1, month, 1), period_end=ref,
    )
    if not institution.ibge_code:
        ctx.pendencias.append("Código IBGE do ente não informado (CO_IBGE) — Administração › Instituição.")
    if not institution.ente_name:
        ctx.pendencias.append("Nome do ente não informado (NO_ENTE) — Administração › Instituição.")

    funds = [CAPITALIZACAO, REPARTICAO] if _segregated(segments) else [CAPITALIZACAO]
    lots = list(LifePurchase.objects.filter(institution=institution, active=True).order_by("number"))
    if institution.life_purchase_enabled and not lots:
        ctx.pendencias.append("Compra de Vidas ativada sem lote registrado — Administração › Instituição.")

    files: dict[str, bytes] = {}
    summary: dict = {f: {} for f in funds}
    if institution.life_purchase_enabled:
        summary[COMPLEMENTAR] = {}
    cv_ids = []

    for key, (name, _label, _baixa) in layouts.FILES.items():
        header = layouts.column_names(key)
        rows = sources.fetch(key, ctx)
        for fund in funds:
            common = _common(institution, fund, ref)
            fund_rows = [r for r in rows if FUND_OF_SEGMENT[r["_massa"]] == fund]
            files[f"{fund}/{name}.csv"] = _csv(header, [[_br({**common, **r}.get(c)) for c in header] for r in fund_rows])
            summary[fund][name] = len(fund_rows)
        if institution.life_purchase_enabled:
            common = _common(institution, CAPITALIZACAO, ref)
            cv_rows = [r for r in rows if r["_massa"] == Segment.COMPRA_VIDAS]
            missing_lot = [r for r in cv_rows if not r.get("_lote")]
            if missing_lot:
                ctx.pendencias.append(f"{len(missing_lot)} registro(s) de {name} na Compra de Vidas sem lote vinculado.")
            files[f"{COMPLEMENTAR}/{name}.csv"] = _csv(header, [[_br({**common, **r}.get(c)) for c in header] for r in cv_rows])
            summary[COMPLEMENTAR][name] = len(cv_rows)
            if key in ID_COLUMNS:
                tipo, cpf_col, mat_col = ID_COLUMNS[key]
                for r in cv_rows:
                    lot = r.get("_lote")
                    cv_ids.append([tipo, _br(r.get(cpf_col)), _br(r.get(mat_col)),
                                   lot.number if lot else "", _br(lot.cutoff_date) if lot else "",
                                   lot.legal_act if lot else ""])

    if institution.life_purchase_enabled:
        files[f"{COMPLEMENTAR}/IDENTIFICACAO_VIDAS.csv"] = _csv(
            ["TIPO_SEGURADO", "CPF", "MATRICULA", "NU_LOTE", "DT_CORTE", "ATO_LEGAL"], cv_ids)
        files[f"{COMPLEMENTAR}/LOTES.csv"] = _csv(
            ["NU_LOTE", "DT_CORTE", "DT_INICIO_PAGAMENTO", "ATO_LEGAL", "DT_ATO_LEGAL", "ESTUDO_ATUARIAL",
             "VL_TRANSFERIDO", "QT_VIDAS_INFORMADA", "PLANO_ORIGEM", "PLANO_DESTINO"],
            [[lot.number, _br(lot.cutoff_date), _br(lot.effective_date), lot.legal_act, _br(lot.legal_act_date),
              lot.actuarial_study, _br(lot.transferred_amount), _br(lot.lives_count),
              lot.origin_plan.code, lot.destination_plan.code] for lot in lots])

    files["RESUMO.csv"] = _csv(
        ["PASTA", "ARQUIVO", "REGISTROS"],
        [[folder, name, qty] for folder, items in summary.items() for name, qty in items.items()],
    )
    files["PENDENCIAS.csv"] = _csv(["PENDENCIA"], [[p] for p in ctx.pendencias])
    files["LEIA-ME.txt"] = _readme(institution, ref, ctx, funds).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    payload = buf.getvalue()
    sha = hashlib.sha256(payload).hexdigest()
    file_name = f"base_atuarial_{institution.short_name}_{year}{month:02d}_{timezone.localtime():%Y%m%d_%H%M%S}.zip"

    with transaction.atomic():
        base = ActuarialBase(
            institution=institution, reference_year=year, reference_month=month,
            layout_code=layouts.DEFAULT_LAYOUT, life_purchase_enabled=institution.life_purchase_enabled,
            file_name=file_name, file_sha256=sha, file_size=len(payload),
            summary=summary, pendencias=ctx.pendencias, notes=notes,
        )
        base.file.save(file_name, ContentFile(payload), save=False)
        base.save()
        log_event(
            "EXPORT", module="atuarial.base", obj=base,
            extra={"data_base": f"{month:02d}/{year}", "sha256": sha, "resumo": summary,
                   "pendencias": len(ctx.pendencias)},
        )
    return base


def _readme(institution, ref: date, ctx, funds) -> str:
    lines = [
        "BASE DE DADOS PARA AVALIAÇÃO ATUARIAL",
        f"Instituição: {institution.name} ({institution.short_name})",
        f"Data-base: {ref:%m/%Y}  ·  Baixas de {ctx.period_start:%d/%m/%Y} a {ctx.period_end:%d/%m/%Y}",
        f"Leiaute: {layouts.load_layout()['nome']} ({layouts.DEFAULT_LAYOUT})",
        f"Gerado em: {timezone.localtime():%d/%m/%Y %H:%M}",
        "",
        "ESTRUTURA",
        "  FUNDO_CAPITALIZACAO  Plano Previdenciário (massa própria + Compra de Vidas) — CO_TIPO_FUNDO = 1",
    ]
    if REPARTICAO in funds:
        lines.append("  FUNDO_REPARTICAO     Plano Financeiro — CO_TIPO_FUNDO = 2")
    if institution.life_purchase_enabled:
        lines += [
            "  COMPLEMENTAR_COMPRA_VIDAS",
            "                       Mesmo leiaute oficial, somente as vidas transferidas do Plano Financeiro.",
            "                       Essas vidas TAMBÉM estão em FUNDO_CAPITALIZACAO (não somar os dois).",
            "                       IDENTIFICACAO_VIDAS.csv relaciona cada vida ao lote; LOTES.csv lista as operações.",
        ]
    lines += [
        "",
        "Os arquivos oficiais seguem o leiaute SPREV sem alteração de nomes ou ordem das variáveis.",
        "CSV separado por ponto e vírgula, decimal com vírgula, datas dd/mm/aaaa, codificação UTF-8.",
        "Confira PENDENCIAS.csv antes de enviar ao atuário.",
    ]
    return "\r\n".join(lines) + "\r\n"
