"""Fila de leitura, conferências automáticas entre documentos e aplicação dos dados conferidos ao cadastro."""
import hashlib
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.audit.services import log_event
from apps.core import secrets
from apps.core.exceptions import BusinessRuleError
from apps.core.validators import is_valid_cpf, only_digits

from . import reader
from .models import AiSettings, FileStatus, JobStatus, ReadingFile, ReadingJob

MODULE = "concessao.leitura"
MAX_FILES = 40


# ================================================================== configuração
def settings_for(institution) -> AiSettings:
    s, _ = AiSettings.objects.get_or_create(institution=institution)
    return s


@transaction.atomic
def save_settings(institution, *, api_key: str | None, model: str | None, enabled: bool | None,
                  privacy_ack: bool | None, engine: str | None = None) -> AiSettings:
    s = settings_for(institution)
    if engine:
        if engine not in ("LOCAL", "ANTHROPIC"):
            raise BusinessRuleError("Motor de leitura inválido.")
        s.engine = engine
    if model:
        if model not in dict(reader.PRICES):
            raise BusinessRuleError("Modelo inválido.")
        s.model = model
    if api_key:
        # Sem regra fixa de formato: quem diz se a chave vale é a própria Anthropic (chamada mínima de teste)
        key = "".join(api_key.split())  # tira espaços e quebras de linha que vêm junto ao copiar
        if len(key) < 20:
            raise BusinessRuleError("Chave muito curta: copie a chave inteira (em console.anthropic.com › API Keys).")
        if key.startswith("sk-ant-admin"):
            raise BusinessRuleError("Esta é uma chave de ADMINISTRAÇÃO (Admin API key), que não lê documentos. "
                                    "Crie uma chave comum em console.anthropic.com › API Keys.")
        try:
            result = reader.test_key(key, s.model)
        except BusinessRuleError as e:
            raise BusinessRuleError(f"A Anthropic recusou a chave: {e}")
        s.api_key, s.key_hint = secrets.encrypt(key), key[-4:]
        s.last_test_at, s.last_test_result = timezone.now(), result[:300]
    if privacy_ack is not None:
        s.privacy_ack = privacy_ack
    if enabled is not None:
        if enabled and not (s.key_hint and s.privacy_ack):
            raise BusinessRuleError("Para ativar, cadastre a chave de API e confirme a ciência sobre os dados pessoais.")
        s.enabled = enabled
    if s.engine == "ANTHROPIC" and not s.enabled:
        raise BusinessRuleError("Para usar a inteligência artificial, cadastre a chave, confirme a ciência e ative-a. "
                                "Sem isso, use a leitura local gratuita.")
    s.save()
    log_event("UPDATE", module="admin.configuracoes", obj=s, object_repr="Leitura inteligente — configuração",
              extra={"motor": s.engine, "modelo": s.model, "ativo": s.enabled, "chave_final": s.key_hint})
    return s


def _key(s: AiSettings) -> str:
    if not s.key_hint:
        raise BusinessRuleError("Cadastre a chave de API da leitura inteligente.")
    return secrets.decrypt(s.api_key)


def test_settings(institution) -> str:
    s = settings_for(institution)
    try:
        msg = reader.test_key(_key(s), s.model)
    except BusinessRuleError as e:
        msg = f"Falhou: {e}"
    s.last_test_at, s.last_test_result = timezone.now(), str(msg)[:300]
    s.save(update_fields=["last_test_at", "last_test_result", "updated_at"])
    return s.last_test_result


# ================================================================== fila de leitura
@transaction.atomic
def create_job(institution, title: str, files, user) -> ReadingJob:
    s = settings_for(institution)
    if s.engine == "ANTHROPIC" and not s.enabled:
        raise BusinessRuleError("A leitura por inteligência artificial não está ativa. Configure-a ou use a leitura local.")
    if not files:
        raise BusinessRuleError("Envie os PDFs do processo.")
    if len(files) > MAX_FILES:
        raise BusinessRuleError(f"Envie no máximo {MAX_FILES} arquivos por leitura.")
    job = ReadingJob.objects.create(institution=institution, title=(title or "Processo")[:200], engine=s.engine)
    for i, f in enumerate(sorted(files, key=lambda x: x.name or "")):
        data = f.read()
        if not data.startswith(b"%PDF"):
            raise BusinessRuleError(f"{f.name}: não é um PDF válido.")
        if len(data) > reader.MAX_BYTES:
            raise BusinessRuleError(f"{f.name}: acima de 30 MB, divida o arquivo.")
        rf = ReadingFile(institution=institution, job=job, file_name=(f.name or "documento.pdf")[:255],
                         file_size=len(data), sha256=hashlib.sha256(data).hexdigest(), order=i)
        rf.file.save(f"{rf.sha256[:16]}.pdf", ContentFile(data), save=False)
        rf.save()
    log_event("CREATE", module=MODULE, obj=job, object_repr=f"Leitura inteligente — {job.title}",
              extra={"arquivos": len(files)})
    return job


def _decorate(rf: ReadingFile, data: dict) -> dict:
    """Numera documentos e campos e prepara a conferência (valor original guardado, confirmação pendente)."""
    for di, d in enumerate(data.get("documentos", [])):
        d["id"] = f"{rf.pk}:{di}"
        d["tipo_display"] = reader.DOC_TYPES.get(d["tipo"], d["tipo"])
        for ci, c in enumerate(d.get("campos", [])):
            c.update(id=f"{rf.pk}:{di}:{ci}", original=c["valor"], confirmado=False, ignorado=False,
                     rotulo=c.get("rotulo") or reader.FIELDS.get(c["chave"], c["chave"]))
    return data


LOCAL_PAGES_PER_CALL = 2  # OCR leva 10–35 s por página: poucas páginas por chamada, a tela mostra o andamento


def _read_local(rf: ReadingFile):
    """Leitura local: OCR de algumas páginas por chamada; ao terminar o arquivo, extrai os dados."""
    import pymupdf

    from . import ocr

    with rf.file.open("rb") as fh:
        doc = pymupdf.open(stream=fh.read(), filetype="pdf")
    if not rf.pages_total:
        rf.pages_total = doc.page_count
    pages = rf.result.get("_paginas", [])
    for n in range(rf.pages_done, min(rf.pages_done + LOCAL_PAGES_PER_CALL, doc.page_count)):
        lines, used = ocr.page_lines(doc[n])
        pages.append({"n": n + 1, "linhas": lines, "ocr": used,
                      "tamanho": [round(doc[n].rect.width, 1), round(doc[n].rect.height, 1)]})
        rf.pages_done = n + 1
    rf.result = {"_paginas": pages}
    if rf.pages_done >= rf.pages_total:
        data = ocr.extract(rf.file_name, pages)
        data["tamanhos"] = {str(p["n"]): p["tamanho"] for p in pages}
        rf.result, rf.status, rf.error = _decorate(rf, data), FileStatus.LIDO, ""
        rf.model, rf.read_at = "ocr-local", timezone.now()


def read_next(job: ReadingJob, user) -> dict:
    """Lê o próximo pedaço da fila (um arquivo com IA, ou algumas páginas com OCR local)."""
    if job.status != JobStatus.LENDO:
        raise BusinessRuleError("Esta leitura já terminou.")
    rf = job.files.filter(status=FileStatus.PENDENTE).first()
    if rf is not None and job.engine == "LOCAL":
        try:
            _read_local(rf)
        except BusinessRuleError as e:
            rf.status, rf.error = FileStatus.ERRO, str(e)
        except Exception as e:  # PDF corrompido, protegido por senha etc.
            rf.status, rf.error = FileStatus.ERRO, f"Não foi possível ler o PDF: {type(e).__name__}"
        rf.save()
    elif rf is not None:
        s = settings_for(job.institution)
        try:
            with rf.file.open("rb") as fh:
                data, inp, out = reader.read_pdf(_key(s), s.model, fh.read(), rf.file_name)
            rf.result, rf.status, rf.error = _decorate(rf, data), FileStatus.LIDO, ""
            rf.model, rf.input_tokens, rf.output_tokens, rf.read_at = s.model, inp, out, timezone.now()
        except BusinessRuleError as e:
            rf.status, rf.error = FileStatus.ERRO, str(e)
        rf.save()
    if not job.files.filter(status=FileStatus.PENDENTE).exists():
        job.status, job.checks = JobStatus.CONFERENCIA, run_checks(job)
        job.save(update_fields=["status", "checks", "updated_at"])
    return progress(job)


def retry_file(rf: ReadingFile):
    if rf.job.status not in (JobStatus.LENDO, JobStatus.CONFERENCIA) or rf.status == FileStatus.PENDENTE:
        raise BusinessRuleError("Este arquivo não pode ser lido de novo agora (leitura aplicada ou já na fila).")
    rf.status, rf.error, rf.pages_done, rf.result = FileStatus.PENDENTE, "", 0, {}
    rf.save(update_fields=["status", "error", "pages_done", "result", "updated_at"])
    job = rf.job
    job.status = JobStatus.LENDO
    job.save(update_fields=["status", "updated_at"])


def progress(job: ReadingJob) -> dict:
    files = list(job.files.all())
    done = sum(1 for f in files if f.status != FileStatus.PENDENTE)
    inp, out = sum(f.input_tokens for f in files), sum(f.output_tokens for f in files)
    model = next((f.model for f in files if f.model), settings_for(job.institution).model)
    return {"total": len(files), "lidos": done, "erros": sum(1 for f in files if f.status == FileStatus.ERRO),
            "situacao": job.status, "tokens_entrada": inp, "tokens_saida": out, "motor": job.engine,
            "paginas": sum(f.pages_total for f in files), "paginas_lidas": sum(f.pages_done for f in files),
            "custo_estimado_usd": 0.0 if job.engine == "LOCAL" else reader.cost_usd(model, inp, out)}


@transaction.atomic
def review_row(job: ReadingJob, doc_id: str, index: int, column: str, value) -> dict:
    """Correção de uma célula da tabela de frequência da CTC (o OCR erra números pequenos)."""
    if job.status != JobStatus.CONFERENCIA:
        raise BusinessRuleError("A leitura não está em conferência.")
    if column not in ("bruto", "faltas", "licencas", "suspensoes", "outras", "liquido"):
        raise BusinessRuleError("Coluna inválida.")
    file_id, di = doc_id.split(":")
    rf = job.files.get(pk=file_id)
    rows = rf.result["documentos"][int(di)]["frequencia"]
    if not 0 <= index < len(rows):
        raise BusinessRuleError("Linha inválida.")
    try:
        rows[index][column] = int(str(value).strip() or 0)
    except ValueError:
        raise BusinessRuleError("Informe um número de dias.")
    rows[index]["corrigido"] = True
    rf.save(update_fields=["result", "updated_at"])
    job.checks = run_checks(job)
    job.save(update_fields=["checks", "updated_at"])
    return rows[index]


# ================================================================== conferência pela equipe
def _find_field(job: ReadingJob, field_id: str):
    file_id, di, ci = field_id.split(":")
    rf = job.files.get(pk=file_id)
    return rf, rf.result["documentos"][int(di)]["campos"][int(ci)]


@transaction.atomic
def review_field(job: ReadingJob, field_id: str, *, value: str | None = None, confirm: bool | None = None,
                 ignore: bool | None = None):
    if job.status != JobStatus.CONFERENCIA:
        raise BusinessRuleError("A leitura não está em conferência.")
    rf, c = _find_field(job, field_id)
    if value is not None:
        c["valor"] = value.strip()
        c["confirmado"] = True
    if confirm is not None:
        c["confirmado"] = confirm
    if ignore is not None:
        c["ignorado"] = ignore
    rf.save(update_fields=["result", "updated_at"])
    job.checks = run_checks(job)
    job.save(update_fields=["checks", "updated_at"])
    return c


@transaction.atomic
def confirm_high(job: ReadingJob) -> int:
    n = 0
    for rf in job.files.filter(status=FileStatus.LIDO):
        for d in rf.result.get("documentos", []):
            for c in d.get("campos", []):
                if c["confianca"] == "alta" and not c["confirmado"] and not c["ignorado"]:
                    c["confirmado"], n = True, n + 1
        rf.save(update_fields=["result", "updated_at"])
    job.checks = run_checks(job)
    job.save(update_fields=["checks", "updated_at"])
    return n


# ================================================================== conferências automáticas
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def _int(v) -> int:
    try:
        return int(re.sub(r"[^\d-]", "", str(v)) or 0)
    except ValueError:
        return 0


def _money(v) -> Decimal | None:
    """Aceita 1234.56, 1234,56 e 1.234,56 (formato brasileiro dos contracheques)."""
    if v in (None, ""):
        return None
    txt = str(v).replace("R$", "").replace(" ", "").strip()
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return Decimal(txt)
    except InvalidOperation:
        return None


def _date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def documents(job: ReadingJob):
    for rf in job.files.filter(status=FileStatus.LIDO).order_by("order"):
        for d in rf.result.get("documentos", []):
            yield rf, d


def _fields(job, key):
    for rf, d in documents(job):
        for c in d.get("campos", []):
            if c["chave"] == key and not c["ignorado"] and c["valor"]:
                yield rf, d, c


def _ref(rf, d, c=None):
    return {"arquivo": rf.file_name, "arquivo_id": str(rf.pk), "documento": d["tipo_display"],
            "pagina": c["pagina"] if c else d["pagina_inicial"], "campo": c["id"] if c else None}


def run_checks(job: ReadingJob) -> list[dict]:
    out = []

    def add(level, title, detail="", refs=None):
        out.append({"nivel": level, "titulo": title, "detalhe": detail, "refs": refs or []})

    # 1. Mesma pessoa em todos os documentos
    for key, label, norm, level in (("pessoa.cpf", "CPF", only_digits, "erro"),
                                    ("pessoa.data_nascimento", "data de nascimento", str, "erro"),
                                    ("pessoa.nome", "nome", _norm, "aviso"),
                                    ("vinculo.data_admissao", "data de admissão", str, "aviso"),
                                    ("vinculo.matricula", "matrícula", only_digits, "aviso")):
        vals = {}
        for rf, d, c in _fields(job, key):
            vals.setdefault(norm(c["valor"]), []).append(_ref(rf, d, c))
        if len(vals) > 1:
            add(level, f"{label[:1].upper() + label[1:]} diferente entre documentos",
                " × ".join(sorted(vals)) + (" (pode ser código diferente da matrícula)" if key == "vinculo.matricula" else ""),
                [r for refs in vals.values() for r in refs])
        elif len(vals) == 1:
            add("ok", f"{label[:1].upper() + label[1:]} igual em {len(next(iter(vals.values())))} documento(s)")
    for rf, d, c in _fields(job, "pessoa.cpf"):
        if not is_valid_cpf(only_digits(c["valor"])):
            add("erro", "CPF com dígito verificador inválido", c["valor"], [_ref(rf, d, c)])
            break

    # 2. CTC: cada ano (bruto − deduções = líquido) e soma = total declarado
    for rf, d in documents(job):
        if d["tipo"] != "CTC" or not d.get("frequencia"):
            continue
        bad = [r for r in d["frequencia"] if r["bruto"] is not None and r["liquido"] is not None and
               r["bruto"] - sum(r[k] or 0 for k in ("faltas", "licencas", "suspensoes", "outras")) != r["liquido"]]
        for r in bad:
            add("erro", f"CTC: conta errada em {r['periodo']}", f"bruto {r['bruto']} − deduções ≠ líquido {r['liquido']}",
                [{**_ref(rf, d), "pagina": r["pagina"]}])
        soma = sum(r["liquido"] or 0 for r in d["frequencia"])
        total = next((c for c in d["campos"] if c["chave"] == "ctc.total_liquido_dias" and not c["ignorado"]), None)
        if total and _int(total["valor"]) != soma:
            add("erro", "CTC: soma dos anos diferente do total da certidão",
                f"soma {soma} dias × total declarado {total['valor']}", [_ref(rf, d, total)])
        elif not bad:
            add("ok", f"CTC conferida: {len(d['frequencia'])} período(s), {soma} dias líquidos")

        sus = [r for r in d["frequencia"] if r.get("suspeito") and not r.get("corrigido")]
        if sus:
            add("aviso", f"CTC: {len(sus)} período(s) com leitura duvidosa ajustados pelo sistema",
                "Confira com a página: " + ", ".join(r["periodo"] for r in sus) + " (linhas em amarelo).",
                [{**_ref(rf, d), "pagina": r["pagina"]} for r in sus])

    # 3. Contracheque / memória de cálculo: rubricas somam o total
    for rf, d in documents(job):
        if d["tipo"] not in ("CONTRACHEQUE", "MEMORIA_CALCULO") or not d.get("rubricas"):
            continue
        prov = sum((_money(r["valor"]) or 0 for r in d["rubricas"] if r["natureza"] == "provento"), Decimal(0))
        desc = sum((_money(r["valor"]) or 0 for r in d["rubricas"] if r["natureza"] == "desconto"), Decimal(0))
        key = "contracheque.total_proventos" if d["tipo"] == "CONTRACHEQUE" else "calculo.valor_total"
        total = next((c for c in d["campos"] if c["chave"] == key and not c["ignorado"]), None)
        name = d["tipo_display"]
        if total and _money(total["valor"]) is not None and _money(total["valor"]) != prov:
            add("erro", f"{name}: proventos não somam o total", f"soma {prov} × total {total['valor']}", [_ref(rf, d, total)])
        elif total:
            add("ok", f"{name}: total de proventos confere ({prov})")
        tdesc = next((c for c in d["campos"] if c["chave"] == "contracheque.total_descontos"), None)
        if tdesc and _money(tdesc["valor"]) is not None and _money(tdesc["valor"]) != desc:
            add("erro", f"{name}: descontos não somam o total", f"soma {desc} × total {tdesc['valor']}", [_ref(rf, d, tdesc)])

        liq = next((c for c in d["campos"] if c["chave"] == "contracheque.liquido" and not c["ignorado"]), None)
        tprov = next((c for c in d["campos"] if c["chave"] == "contracheque.total_proventos" and not c["ignorado"]), None)
        if liq and tprov and tdesc and None not in (_money(liq["valor"]), _money(tprov["valor"]), _money(tdesc["valor"])):
            if _money(tprov["valor"]) - _money(tdesc["valor"]) != _money(liq["valor"]):
                add("erro", f"{name}: proventos − descontos não dá o líquido",
                    f"{tprov['valor']} − {tdesc['valor']} ≠ {liq['valor']}", [_ref(rf, d, liq)])

    # 4. Documentos esperados
    tipos = {d["tipo"] for _, d in documents(job)}
    is_pension = bool(tipos & {"CERTIDAO_OBITO"})
    needed = (["CERTIDAO_OBITO", "RG_CPF", "REQUERIMENTO"] if is_pension else
              ["RG_CPF", "REQUERIMENTO", "CONTRACHEQUE"])
    for t in needed:
        if t not in tipos:
            add("aviso", f"Documento não encontrado: {reader.DOC_TYPES[t]}")
    if not is_pension and not tipos & {"CTC", "HISTORICO_FUNCIONAL"}:
        add("aviso", "Sem CTC nem histórico funcional: o tempo de serviço não pôde ser lido")

    # 5. Comparação com o cadastro
    from apps.people.models import Person

    cpf = next((only_digits(c["valor"]) for _, _, c in _fields(job, "pessoa.cpf")), "")
    p = Person.objects.filter(institution=job.institution, cpf=cpf).first() if cpf else None
    if job.person_id and p and p.pk != job.person_id:
        add("erro", "O CPF dos documentos é de outra pessoa", f"escolhida: {job.person.name} × documentos: {p.name}")
    elif job.person_id and not cpf:
        add("ok", f"Pessoa escolhida pela equipe: {job.person.name} (os documentos não trazem CPF).")
    elif not cpf:
        add("aviso", "Nenhum CPF nos documentos: escolha a pessoa (ou junte esta leitura à do processo) antes de aplicar.")
    if p:
        nasc = next((c["valor"] for _, _, c in _fields(job, "pessoa.data_nascimento")), "")
        if nasc and p.birth_date and str(p.birth_date) != nasc[:10]:
            add("erro", "Data de nascimento diferente do cadastro", f"cadastro {p.birth_date:%d/%m/%Y} × documento {nasc}")
        add("ok", f"Pessoa já cadastrada: {p.name}. Só os campos vazios serão completados.")
    elif cpf:
        add("aviso", "Pessoa ainda não cadastrada: será incluída em Servidores ao aplicar.")

    pend = sum(1 for _, d in documents(job) for c in d["campos"] if not c["confirmado"] and not c["ignorado"])
    if pend:
        add("aviso", f"{pend} dado(s) ainda não conferido(s)", "Confirme, corrija ou ignore cada dado antes de aplicar.")
    order = {"erro": 0, "aviso": 1, "ok": 2}
    return sorted(out, key=lambda x: order[x["nivel"]])


# ================================================================== aplicação ao cadastro
DOC_MAP = {"RG_CPF": "IDENTIDADE", "CTC": "CTC", "ATO": "ATO", "PUBLICACAO": "ATO", "CERTIDAO_OBITO": "CERT_OBITO",
           "CERTIDAO_CASAMENTO": "CERT_CASAMENTO", "CERTIDAO_NASCIMENTO": "CERT_NASC",
           "COMPROVANTE_RESIDENCIA": "RESIDENCIA", "LAUDO_MEDICO": "LAUDO", "HISTORICO_FUNCIONAL": "FICHA_FUNC",
           "CONTRACHEQUE": "CONTRACHEQUE", "FICHA_FINANCEIRA": "CONTRACHEQUE", "DECLARACAO_ACUMULACAO": "DECL_ACUMUL",
           "MEMORIA_CALCULO": "ATO"}
MARITAL = {"SOLTEIRO": 1, "SOLTEIRA": 1, "CASADO": 2, "CASADA": 2, "VIUVO": 3, "VIUVA": 3, "SEPARADO": 4,
           "SEPARADA": 4, "DIVORCIADO": 5, "DIVORCIADA": 5, "UNIAO ESTAVEL": 6}


def _value(job, key):
    """Primeiro valor CONFERIDO do campo (confirmado ou corrigido)."""
    return next((c["valor"] for _, _, c in _fields(job, key) if c["confirmado"]), "")


@transaction.atomic
def apply(job: ReadingJob, user, *, organ=None, segment: str = "", sex: str = "", ctc_use: dict | None = None) -> dict:
    from apps.cadastros.models import Position
    from apps.employment.models import EmploymentLink, EventType, FunctionalEvent
    from apps.people.models import Person
    from apps.people.services import upload_document
    from apps.previdencia.models import Averbacao

    job = ReadingJob.objects.select_for_update().get(pk=job.pk)
    if job.status != JobStatus.CONFERENCIA:
        raise BusinessRuleError("Só leituras em conferência podem ser aplicadas.")
    pend = [c for _, d in documents(job) for c in d["campos"] if not c["confirmado"] and not c["ignorado"]]
    if pend:
        raise BusinessRuleError(f"Ainda há {len(pend)} dado(s) sem conferência. Confirme, corrija ou ignore cada um.")
    if any(ch["nivel"] == "erro" for ch in run_checks(job)):
        raise BusinessRuleError("Há divergências marcadas como erro. Corrija os dados (ou ignore o dado errado) antes.")
    cpf = only_digits(_value(job, "pessoa.cpf"))
    if not is_valid_cpf(cpf):
        if job.person_id is None:
            raise BusinessRuleError("Os documentos não trazem um CPF válido: escolha a pessoa nesta leitura "
                                    "(ou junte-a à leitura do processo que tem o documento de identidade).")
        cpf = job.person.cpf
    elif job.person_id and job.person.cpf != cpf:
        raise BusinessRuleError("O CPF dos documentos é de outra pessoa que a escolhida nesta leitura.")
    summary = {"pessoa": [], "vinculo": [], "averbacoes": [], "frequencia": [], "documentos": [], "divergencias": []}

    # ---- pessoa (completa só o que está vazio; divergências ficam listadas, nunca sobrescritas)
    data = {
        "name": _value(job, "pessoa.nome").upper()[:150], "birth_date": _date(_value(job, "pessoa.data_nascimento")),
        "mother_name": _value(job, "pessoa.nome_mae").upper()[:150], "father_name": _value(job, "pessoa.nome_pai").upper()[:150],
        "rg_number": only_digits(_value(job, "pessoa.rg_numero"))[:20] or _value(job, "pessoa.rg_numero")[:20],
        "rg_issuer": _value(job, "pessoa.rg_orgao")[:20], "rg_uf": _value(job, "pessoa.rg_uf")[:2].upper(),
        "rg_date": _date(_value(job, "pessoa.rg_data")), "pis_pasep": only_digits(_value(job, "pessoa.pis_pasep"))[:11],
        "education": _value(job, "pessoa.escolaridade")[:60],
        "marital_status": MARITAL.get(_norm(_value(job, "pessoa.estado_civil")).replace("(A)", "").strip()),
    }
    sx = (sex or _value(job, "pessoa.sexo")).upper()[:1]
    data["sex"] = {"F": 1, "M": 2}.get(sx)
    person = Person.objects.filter(institution=job.institution, cpf=cpf).first()
    if person is None:
        if not data["name"] or not data["birth_date"] or not data["sex"]:
            raise BusinessRuleError("Para incluir a pessoa são necessários nome, data de nascimento e sexo "
                                    "(informe o sexo se não constar dos documentos).")
        person = Person.objects.create(institution=job.institution, cpf=cpf,
                                       **{k: v for k, v in data.items() if v not in (None, "")})
        log_event("CREATE", module="cadastro.pessoas", obj=person, object_repr=f"{person.name} (leitura inteligente)")
        summary["pessoa"].append("Pessoa incluída no cadastro (Servidores)")
    else:
        changed = []
        for k, v in data.items():
            if v in (None, ""):
                continue
            cur = getattr(person, k)
            if cur in (None, ""):
                setattr(person, k, v)
                changed.append(k)
            elif str(cur).upper() != str(v).upper():
                summary["divergencias"].append(f"{Person._meta.get_field(k).verbose_name}: cadastro '{cur}' × documento '{v}'")
        if changed:
            person.save(update_fields=changed + ["updated_at"])
            log_event("UPDATE", module="cadastro.pessoas", obj=person,
                      object_repr=f"{person.name} — completado pela leitura inteligente", extra={"campos": changed})
            summary["pessoa"].append(f"Completados: {', '.join(Person._meta.get_field(k).verbose_name for k in changed)}")
        else:
            summary["pessoa"].append("Cadastro já completo — nada alterado")

    # ---- vínculo
    reg = only_digits(_value(job, "vinculo.matricula")) or _value(job, "vinculo.matricula")
    adm = _date(_value(job, "vinculo.data_admissao"))
    link = EmploymentLink.objects.filter(person=person, registration=reg).first() if reg else None
    if link is None and organ is not None and reg and adm and _value(job, "vinculo.cargo"):
        cargo = _value(job, "vinculo.cargo").upper()[:150]
        pos = Position.objects.filter(institution=job.institution, name__iexact=cargo).first() or \
            Position.objects.create(institution=job.institution, name=cargo)
        link = EmploymentLink.objects.create(
            institution=job.institution, person=person, organ=organ, position=pos, registration=reg[:20],
            public_service_start=adm, ente_start=adm, position_start=adm, career_start=adm,
            class_level=_value(job, "vinculo.carreira_nivel")[:50], segment=segment or "PREVIDENCIARIO",
            notes="Incluído pela leitura inteligente do processo (dados conferidos pela equipe).")
        log_event("CREATE", module="cadastro.vinculos", obj=link, object_repr=f"Vínculo {reg} — {person.name}")
        summary["vinculo"].append(f"Vínculo incluído: matrícula {reg}, {cargo}, admissão {adm:%d/%m/%Y}")
    elif link is not None:
        summary["vinculo"].append(f"Vínculo matrícula {reg} já existia — mantido")
    else:
        summary["vinculo"].append("Vínculo não incluído (escolha o órgão e confira matrícula, cargo e admissão)")

    # ---- CTCs: averbação (outro órgão/regime) ou frequência do próprio vínculo
    ctc_use = ctc_use or {}
    for rf, d in documents(job):
        if d["tipo"] != "CTC":
            continue
        use = ctc_use.get(d["id"], "IGNORAR")
        get = {c["chave"]: c["valor"] for c in d["campos"] if c["confirmado"] and not c["ignorado"]}
        if use == "AVERBACAO":
            ini, fim = _date(get.get("ctc.periodo_inicio")), _date(get.get("ctc.periodo_fim"))
            dias = _int(get.get("ctc.total_liquido_dias")) or sum(r["liquido"] or 0 for r in d["frequencia"])
            if not (ini and fim and dias):
                raise BusinessRuleError(f"CTC ({rf.file_name}): confira início, fim e total líquido para averbar.")
            num = get.get("ctc.numero", "")[:40]
            if num and Averbacao.objects.filter(person=person, certificate_number=num, active=True).exists():
                summary["averbacoes"].append(f"CTC {num} já averbada — mantida")
                continue
            av = Averbacao.objects.create(
                institution=job.institution, person=person,
                nature="01" if get.get("ctc.regime_origem", "").upper() == "RGPS" else "03",
                issuer=get.get("ctc.orgao_emissor", "Órgão emissor")[:150],
                issuer_cnpj=only_digits(get.get("ctc.cnpj_emissor", ""))[:14], certificate_number=num,
                certificate_date=_date(get.get("ctc.data_emissao")), start_date=ini, end_date=fim, certified_days=dias,
                notes="Incluída pela leitura inteligente (dados conferidos pela equipe).")
            log_event("CREATE", module="previdenciaria.averbacoes", obj=av, object_repr=f"Averbação {av.issuer}")
            summary["averbacoes"].append(f"Averbação: {av.issuer}, {ini:%d/%m/%Y} a {fim:%d/%m/%Y}, {dias} dias")
        elif use == "VINCULO":
            if link is None:
                raise BusinessRuleError("Para usar a CTC como frequência do vínculo, o vínculo precisa existir.")
            n = 0
            for r in d["frequencia"]:
                ded = sum(r[k] or 0 for k in ("faltas", "licencas", "suspensoes", "outras"))
                year = re.findall(r"(?:19|20)\d{2}", r["periodo"]) or re.findall(r"/(\d{2})\b", r["periodo"])
                if not ded or not year:
                    continue
                y = int(year[-1]) if len(year[-1]) == 4 else 2000 + int(year[-1])
                FunctionalEvent.objects.create(
                    institution=job.institution, link=link, event_type=EventType.FALTAS, start_date=date(y, 1, 1),
                    end_date=date(y, 12, 31), days=ded, with_pay=False, contributed=False, counts_as_service=False,
                    description=f"Deduções da CTC ({r['periodo']}): faltas {r['faltas'] or 0}, licenças "
                                f"{r['licencas'] or 0}, suspensões {r['suspensoes'] or 0}, outras {r['outras'] or 0}")
                n += ded
            summary["frequencia"].append(f"Deduções da CTC lançadas no vínculo: {n} dia(s)")

    # ---- arquivos no cadastro (documentos versionados)
    for rf in job.files.filter(status=FileStatus.LIDO):
        # o documento principal do arquivo (o primeiro reconhecido) define a pasta; o resto vai em "Outros"
        doc_type = next((DOC_MAP[d["tipo"]] for d in rf.result.get("documentos", []) if d["tipo"] in DOC_MAP), None)
        with rf.file.open("rb") as fh:
            up = ContentFile(fh.read(), name=rf.file_name if rf.file_name.lower().endswith(".pdf") else f"{rf.file_name}.pdf")
        up.content_type = "application/pdf"
        try:
            upload_document(person, doc_type or "OUTROS", up, description=f"Processo — {rf.file_name}"[:255])
            summary["documentos"].append(rf.file_name)
        except BusinessRuleError as e:
            summary["documentos"].append(f"{rf.file_name}: {e}")

    job.status, job.person, job.applied_at, job.applied_summary = JobStatus.APLICADO, person, timezone.now(), summary
    job.save(update_fields=["status", "person", "applied_at", "applied_summary", "updated_at"])
    log_event("UPDATE", module=MODULE, obj=job, object_repr=f"Leitura aplicada ao cadastro — {person.name}",
              extra={k: len(v) for k, v in summary.items()})
    return summary
