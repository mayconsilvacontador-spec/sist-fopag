"""
Importação COMPLEMENTAR (leiaute SIST) — dados que a base atuarial SPREV não traz. Os arquivos entram na mesma tela
e no mesmo lote da importação SPREV (validar → confirmar), reconhecidos pelo cabeçalho:

  PESSOAS_COMPLEMENTO  CPF;NOME_MAE;NOME_PAI;RG;RG_ORGAO;RG_UF;RG_DATA;NATURALIDADE;NATURALIDADE_UF;
                       NACIONALIDADE;ESCOLARIDADE;RACA_COR;EMAIL;CELULAR;TELEFONE;TITULO_ELEITOR
  ENDERECOS            CPF;CEP;LOGRADOURO;NUMERO;COMPLEMENTO;BAIRRO;CIDADE;UF;CODIGO_IBGE;INICIO
  CONTAS_BANCARIAS     CPF;BANCO;NOME_BANCO;AGENCIA;AGENCIA_DV;CONTA;CONTA_DV;TIPO_CONTA;INICIO
  AVERBACOES (CTC)     CPF;NATUREZA_TEMPO;ORGAO_EMISSOR;CNPJ_EMISSOR;NUMERO_CTC;DATA_CTC;INICIO;FIM;DIAS_LIQUIDOS;
                       MAGISTERIO;ATIVIDADE_ESPECIAL;ACRESCIMO_CONVERSAO;ATO_AVERBACAO;DATA_ATO;COMPREV;OBSERVACOES
  HISTORICO_FUNCIONAL  CPF;MATRICULA;TIPO_EVENTO;INICIO;FIM;DIAS;REMUNERADO;CONTRIBUIU;CONTA_TEMPO;NATUREZA_ATO;
                       NUMERO_ATO;DATA_ATO;PUBLICACAO;DESCRICAO

Regras: a pessoa (e, no histórico, o vínculo) já tem de existir — importe antes os arquivos SPREV (vão no mesmo lote).
Nada é sobrescrito: campos já preenchidos ficam como estão (divergência vira aviso); endereço e conta entram com
vigência (o anterior é encerrado); averbação/evento repetido é ignorado.
"""
from apps.core.validators import is_valid_cnpj, only_digits

# Tabela padrão de SERVIDORES do SIST (uma linha = uma admissão completa; modelo em imports/modelo-servidores/)
SERVIDORES_COLUMNS = [
    ("CPF", "Obrigatório. Só números ou com pontos e traço."),
    ("NOME", "Obrigatório para servidor novo."),
    ("DATA_NASCIMENTO", "Obrigatório para servidor novo. dd/mm/aaaa."),
    ("SEXO", "Obrigatório para servidor novo. F ou M."),
    ("ESTADO_CIVIL", "1 Solteiro, 2 Casado, 3 Viúvo, 4 Separado/divorciado, 5 União estável, 9 Outros."),
    ("NOME_MAE", ""), ("NOME_PAI", ""), ("RG", ""), ("RG_ORGAO", ""), ("PIS_PASEP", "11 números."),
    ("ESCOLARIDADE", ""), ("EMAIL", ""), ("CELULAR", ""),
    ("ORGAO", "Obrigatório. Nome do órgão (igual ao cadastro) ou CNPJ. Se não existir, é criado."),
    ("CARGO", "Obrigatório. Se não existir, é criado."),
    ("MATRICULA", "Obrigatório. Única no órgão."),
    ("CLASSE_NIVEL", "Classe / nível / referência."),
    ("VENCIMENTO_BASE", "Ex.: 3500,00. Em branco = usa a Tabela de vencimentos do cargo."),
    ("CARGA_HORARIA", "Horas semanais. Ex.: 40."),
    ("REGIME", "ESTATUTARIO ou CELETISTA (padrão ESTATUTARIO)."),
    ("FORMA_ADMISSAO", "1 Contrato temporário, 2 Prazo indeterminado, 3 Concurso público (padrão), 4 Nomeação direta."),
    ("MASSA", "PREVIDENCIARIO (padrão) ou FINANCEIRO."),
    ("DATA_NOMEACAO", "Obrigatório. dd/mm/aaaa."),
    ("DATA_POSSE", "Início do exercício. Em branco = data da nomeação."),
    ("INGRESSO_SERVICO_PUBLICO", "Em branco = data da posse."),
    ("PORTARIA_NOMEACAO", "Número do ato."), ("DATA_PORTARIA", "dd/mm/aaaa."), ("PUBLICACAO", "D.O. / data."),
    ("CEP", ""), ("LOGRADOURO", ""), ("NUMERO", ""), ("COMPLEMENTO", ""), ("BAIRRO", ""), ("CIDADE", ""),
    ("UF", "Sigla."),
    ("BANCO", "Código do banco (ex.: 001). Precisa estar em Cadastros › Bancos."),
    ("AGENCIA", ""), ("CONTA", ""), ("CONTA_DV", ""), ("TIPO_CONTA", "CORRENTE (padrão), POUPANCA ou SALARIO."),
]

COMPLEMENT_KINDS = [  # (colunas que identificam o arquivo, tipo)
    ({"CPF", "MATRICULA", "DATA_NOMEACAO", "CARGO"}, "admissoes"),
    ({"CPF", "NOME_MAE"}, "complemento"),
    ({"CPF", "LOGRADOURO"}, "enderecos"),
    ({"CPF", "BANCO", "CONTA"}, "contas"),
    ({"CPF", "NATUREZA_TEMPO", "DIAS_LIQUIDOS"}, "averbacoes"),
    ({"MATRICULA", "TIPO_EVENTO"}, "historico"),
]
COMPLEMENT_ORDER = ["admissoes", "complemento", "enderecos", "contas", "averbacoes", "historico"]
COMPLEMENT_LABELS = {"admissoes": "Servidores (tabela padrão SIST)", "complemento": "Dados pessoais (complemento)", "enderecos": "Endereços",
                     "contas": "Contas bancárias", "averbacoes": "Averbações (CTC)",
                     "historico": "Histórico funcional"}
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())


def detect_complement(keys: set) -> str | None:
    for cols, kind in COMPLEMENT_KINDS:
        if cols <= keys:
            return kind
    return None


class ComplementMixin:
    """Métodos _row_<tipo> usados pelo SprevImporter para os arquivos complementares."""

    def _existing_person(self, row):
        from apps.people.models import Person

        from .sprev import RowError, _cpf

        cpf = _cpf(row.get("CPF"))
        if not cpf:
            raise RowError("CPF não informado")
        p = Person.objects.filter(institution=self.inst, cpf=cpf).first()
        if p is None:
            raise RowError("pessoa não está no cadastro — inclua o arquivo SPREV (servidores, aposentados, "
                           "pensionistas ou dependentes) no mesmo lote ou importe-o antes")
        return p

    def _count(self, key):
        self.report.resumo[key] = self.report.resumo.get(key, 0) + 1

    def _yes(self, v) -> bool:
        from .sprev import _s

        return _s(v).upper() in ("S", "SIM", "1", "X", "TRUE")

    # ---------------------------------------------------------------- servidores (tabela padrão)
    def _row_admissoes(self, row, name, line):
        from apps.cadastros.models import Bank
        from apps.core.exceptions import BusinessRuleError
        from apps.employment.models import EmploymentLink
        from apps.people.lifecycle import admit

        from .sprev import RowError, _cpf, _date, _dec, _s

        cpf = _cpf(row.get("CPF"))
        if not cpf:
            raise RowError("CPF não informado")
        org = _s(row.get("ORGAO"))
        digits = only_digits(org)
        is_cnpj = len(digits) == 14
        organ = self._organ({"NO_ORGAO": "" if is_cnpj else org, "CNPJ": digits if is_cnpj else ""}, "CNPJ")
        position = self._position({"NO_CARGO": _s(row.get("CARGO"))})
        registration = _s(row.get("MATRICULA"))
        if registration.endswith(".0"):  # número lido do Excel
            registration = registration[:-2]
        if registration and EmploymentLink.objects.filter(institution=self.inst, organ=organ,
                                                          registration=registration).exists():
            self._count("vinculos_existentes")
            self._msg("avisos", name, line, cpf, f"matrícula {registration} já existe no órgão — ignorada")
            return cpf

        def d(col):
            v = _date(row.get(col))
            if _s(row.get(col)) and v is None:
                raise RowError(f"{col} inválida")
            return v.isoformat() if v else ""

        sex = {"F": 1, "M": 2, "1": 1, "2": 2}.get(_s(row.get("SEXO")).upper()[:1], "")
        venc = _dec(row.get("VENCIMENTO_BASE"))
        bank = ""
        if _s(row.get("BANCO")):
            code = only_digits(_s(row.get("BANCO"))).zfill(3)
            b = Bank.objects.filter(institution=self.inst, code=code).first()
            if b is None:
                raise RowError(f"banco {code} não cadastrado em Cadastros › Bancos")
            bank = str(b.pk)
        regime = _s(row.get("REGIME")).upper() or "ESTATUTARIO"
        massa = _s(row.get("MASSA")).upper() or "PREVIDENCIARIO"
        if massa not in self.segments:
            raise RowError(f"MASSA {massa} não está ativa nesta instituição")
        email = _s(row.get("EMAIL"))[:254]
        if email and "@" not in email:
            email = ""
            self._msg("avisos", name, line, cpf, "EMAIL inválido — não importado")
        hours = only_digits(_s(row.get("CARGA_HORARIA")).split(",")[0].split(".")[0])
        payload = {
            "pessoa": {"cpf": cpf, "name": _s(row.get("NOME")), "birth_date": d("DATA_NASCIMENTO"), "sex": sex,
                       "marital_status": only_digits(_s(row.get("ESTADO_CIVIL")))[:1],
                       "mother_name": _s(row.get("NOME_MAE")).upper()[:150],
                       "father_name": _s(row.get("NOME_PAI")).upper()[:150],
                       "rg_number": _s(row.get("RG"))[:20], "rg_issuer": _s(row.get("RG_ORGAO"))[:20],
                       "pis_pasep": only_digits(_s(row.get("PIS_PASEP")))[:11],
                       "education": _s(row.get("ESCOLARIDADE"))[:60], "email": email,
                       "mobile": _s(row.get("CELULAR"))[:20]},
            "vinculo": {"organ": str(organ.pk), "position": str(position.pk), "registration": registration,
                        "class_level": _s(row.get("CLASSE_NIVEL")), "base_salary": str(venc) if venc else "",
                        "weekly_hours": hours,
                        "regime": regime if regime in ("ESTATUTARIO", "CELETISTA") else "ESTATUTARIO",
                        "admission_form": only_digits(_s(row.get("FORMA_ADMISSAO")))[:1] or 3, "segment": massa,
                        "nomeacao": d("DATA_NOMEACAO"), "exercicio": d("DATA_POSSE"),
                        "servico_publico": d("INGRESSO_SERVICO_PUBLICO"),
                        "act_number": _s(row.get("PORTARIA_NOMEACAO")), "act_date": d("DATA_PORTARIA"),
                        "publication": _s(row.get("PUBLICACAO")),
                        "notes": f"Importado de: {self.source} (lote {self.batch.pk})."},
            "endereco": {"cep": _s(row.get("CEP")), "street": _s(row.get("LOGRADOURO")), "number": _s(row.get("NUMERO")),
                         "complement": _s(row.get("COMPLEMENTO")), "district": _s(row.get("BAIRRO")),
                         "city": _s(row.get("CIDADE")), "uf": _s(row.get("UF"))},
            "conta": {"bank": bank, "branch": _s(row.get("AGENCIA")), "account": _s(row.get("CONTA")),
                      "account_digit": _s(row.get("CONTA_DV")),
                      "account_type": _s(row.get("TIPO_CONTA")).upper() or "CORRENTE"},
        }
        try:
            res = admit(self.inst, payload, None)
        except BusinessRuleError as exc:
            raise RowError(str(getattr(exc, "detail", exc)))
        self._count("pessoas_novas" if res["pessoa_nova"] else "pessoas_completadas")
        self._count("vinculos")
        return cpf

    # ---------------------------------------------------------------- dados pessoais
    def _row_complemento(self, row, name, line):
        from .sprev import RowError, _date, _int, _s

        p = self._existing_person(row)
        uf = _s(row.get("RG_UF")).upper()
        nat_uf = _s(row.get("NATURALIDADE_UF")).upper()
        for u, col in ((uf, "RG_UF"), (nat_uf, "NATURALIDADE_UF")):
            if u and u not in UFS:
                raise RowError(f"{col} inválida: {u}")
        email = _s(row.get("EMAIL"))
        if email and "@" not in email:
            raise RowError("EMAIL inválido")
        data = {
            "mother_name": _s(row.get("NOME_MAE")).upper()[:150], "father_name": _s(row.get("NOME_PAI")).upper()[:150],
            "rg_number": _s(row.get("RG"))[:20], "rg_issuer": _s(row.get("RG_ORGAO")).upper()[:20], "rg_uf": uf,
            "rg_date": _date(row.get("RG_DATA")), "birthplace_city": _s(row.get("NATURALIDADE"))[:120],
            "birthplace_uf": nat_uf, "education": _s(row.get("ESCOLARIDADE"))[:60],
            "race": _int(row.get("RACA_COR"), {1, 2, 3, 4, 5, 6}), "email": email[:254],
            "mobile": _s(row.get("CELULAR"))[:20], "phone": _s(row.get("TELEFONE"))[:20],
            "voter_id": only_digits(_s(row.get("TITULO_ELEITOR")))[:12],
        }
        if _s(row.get("NACIONALIDADE")):
            data["nationality"] = _s(row.get("NACIONALIDADE"))[:60]
        changed = []
        for attr, value in data.items():
            if value in (None, ""):
                continue
            cur = getattr(p, attr)
            if cur in (None, "") or (attr == "nationality" and cur == "Brasileira"):
                setattr(p, attr, value)
                changed.append(attr)
            elif str(cur).upper() != str(value).upper():
                self._msg("avisos", name, line, p.cpf, f"{p._meta.get_field(attr).verbose_name} diverge do Cadastro "
                                                       "Único (mantido o atual)")
        if p.rg_date and p.rg_date < p.birth_date:
            raise RowError("RG_DATA anterior ao nascimento")
        if changed:
            p.save(update_fields=changed + ["updated_at"])
            self._count("pessoas_complementadas")
        return p.cpf

    # ---------------------------------------------------------------- endereço (com vigência)
    def _row_enderecos(self, row, name, line):
        from django.utils import timezone

        from apps.people.models import Address
        from apps.people.services import add_address

        from .sprev import RowError, _date, _s

        p = self._existing_person(row)
        street, city = _s(row.get("LOGRADOURO"))[:150], _s(row.get("CIDADE"))[:120]
        if not street or not city:
            raise RowError("LOGRADOURO e CIDADE são obrigatórios")
        uf = _s(row.get("UF")).upper()
        if uf and uf not in UFS:
            raise RowError(f"UF inválida: {uf}")
        cep = only_digits(_s(row.get("CEP")))
        if cep and len(cep) != 8:
            raise RowError("CEP deve ter 8 dígitos")
        ibge = only_digits(_s(row.get("CODIGO_IBGE")))
        if ibge and len(ibge) != 7:
            raise RowError("CODIGO_IBGE deve ter 7 dígitos")
        start = _date(row.get("INICIO")) or timezone.localdate()
        cur = Address.objects.filter(person=p, valid_to__isnull=True).first()
        if cur and cur.street.upper() == street.upper() and (cur.number or "") == _s(row.get("NUMERO"))[:10] \
                and cur.city.upper() == city.upper():
            self._msg("avisos", name, line, p.cpf, "endereço igual ao atual — ignorado")
            return p.cpf
        if cur and start <= cur.valid_from:
            raise RowError(f"INICIO deve ser posterior ao início do endereço atual ({cur.valid_from:%d/%m/%Y})")
        add_address(p, cep=cep, street=street, number=_s(row.get("NUMERO"))[:10],
                    complement=_s(row.get("COMPLEMENTO"))[:60], district=_s(row.get("BAIRRO"))[:80], city=city,
                    city_ibge=ibge, uf=uf, valid_from=start)
        self._count("enderecos")
        return p.cpf

    # ---------------------------------------------------------------- conta bancária (com vigência)
    def _row_contas(self, row, name, line):
        from django.utils import timezone

        from apps.cadastros.models import Bank
        from apps.people.models import BankAccount
        from apps.people.services import add_bank_account

        from .sprev import RowError, _date, _s

        p = self._existing_person(row)
        code = only_digits(_s(row.get("BANCO"))).zfill(3)[-3:]
        if not code.strip("0"):
            raise RowError("BANCO (código de 3 dígitos) não informado")
        bank = Bank.objects.filter(institution=self.inst, code=code).first()
        if bank is None:
            bank = Bank.objects.create(institution=self.inst, code=code,
                                       name=(_s(row.get("NOME_BANCO")) or f"Banco {code}")[:120])
            self._count("bancos_criados")
        branch, account = only_digits(_s(row.get("AGENCIA")))[:5], only_digits(_s(row.get("CONTA")))[:15]
        if not branch or not account:
            raise RowError("AGENCIA e CONTA são obrigatórios")
        kind = (_s(row.get("TIPO_CONTA")) or "CORRENTE").upper()
        if kind not in ("CORRENTE", "POUPANCA", "SALARIO"):
            raise RowError("TIPO_CONTA deve ser CORRENTE, POUPANCA ou SALARIO")
        start = _date(row.get("INICIO")) or timezone.localdate()
        cur = BankAccount.objects.filter(person=p, valid_to__isnull=True).first()
        if cur and cur.bank_id == bank.pk and cur.branch == branch and cur.account == account:
            self._msg("avisos", name, line, p.cpf, "conta igual à atual — ignorada")
            return p.cpf
        if cur and start <= cur.valid_from:
            raise RowError(f"INICIO deve ser posterior ao início da conta atual ({cur.valid_from:%d/%m/%Y})")
        add_bank_account(p, bank=bank, branch=branch, branch_digit=_s(row.get("AGENCIA_DV"))[:1], account=account,
                         account_digit=_s(row.get("CONTA_DV"))[:2], account_type=kind, valid_from=start)
        self._count("contas_bancarias")
        return p.cpf

    # ---------------------------------------------------------------- averbações (CTC de outros regimes/órgãos)
    def _row_averbacoes(self, row, name, line):
        from apps.previdencia.models import Averbacao, TimeNature

        from .sprev import RowError, _date, _int, _s

        p = self._existing_person(row)
        nature = only_digits(_s(row.get("NATUREZA_TEMPO"))).zfill(2)
        if nature not in TimeNature.values:
            raise RowError("NATUREZA_TEMPO inválida (01 INSS privado, 02 INSS órgão público, 03 outro RPPS, "
                           "04 Forças Armadas, 05 RPPS de origem)")
        start, end = _date(row.get("INICIO")), _date(row.get("FIM"))
        if not start or not end:
            raise RowError("INICIO e FIM do período certificado são obrigatórios")
        if end < start:
            raise RowError("FIM anterior ao INICIO")
        if start < p.birth_date:
            raise RowError("período anterior ao nascimento")
        days = _int(row.get("DIAS_LIQUIDOS"))
        if not days or days <= 0:
            raise RowError("DIAS_LIQUIDOS deve ser maior que zero")
        if days > (end - start).days + 1:
            raise RowError(f"DIAS_LIQUIDOS ({days}) maior que o período ({(end - start).days + 1} dias)")
        issuer = _s(row.get("ORGAO_EMISSOR"))[:150]
        if not issuer:
            raise RowError("ORGAO_EMISSOR não informado")
        cnpj = only_digits(_s(row.get("CNPJ_EMISSOR")))
        if cnpj and not is_valid_cnpj(cnpj):
            raise RowError("CNPJ_EMISSOR inválido")
        number = _s(row.get("NUMERO_CTC"))[:40]
        if Averbacao.objects.filter(person=p, start_date=start, end_date=end, active=True).exists():
            self._msg("avisos", name, line, p.cpf, "averbação do mesmo período já cadastrada — ignorada")
            return p.cpf
        extra = _int(row.get("ACRESCIMO_CONVERSAO")) or 0
        if extra and start.year >= 2020:
            raise RowError("conversão de tempo especial só para períodos até 12/11/2019")
        Averbacao.objects.create(
            institution=self.inst, person=p, nature=nature, issuer=issuer, issuer_cnpj=cnpj,
            certificate_number=number, certificate_date=_date(row.get("DATA_CTC")), start_date=start, end_date=end,
            certified_days=days, magisterio=self._yes(row.get("MAGISTERIO")),
            special_activity=self._yes(row.get("ATIVIDADE_ESPECIAL")), conversion_extra_days=extra,
            act_number=_s(row.get("ATO_AVERBACAO"))[:40], act_date=_date(row.get("DATA_ATO")),
            comprev=_s(row.get("COMPREV")).upper() not in ("N", "NAO", "NÃO", "0"),
            notes=(_s(row.get("OBSERVACOES")) + f" Importado de: {self.source}.").strip())
        self._count("averbacoes")
        return p.cpf

    # ---------------------------------------------------------------- histórico funcional (eventos do vínculo)
    def _row_historico(self, row, name, line):
        from apps.employment.models import EmploymentLink, EventType, FunctionalEvent

        from .sprev import RowError, _cpf, _date, _int, _s

        registration = only_digits(_s(row.get("MATRICULA")).split(".")[0]) or _s(row.get("MATRICULA"))
        links = EmploymentLink.objects.filter(institution=self.inst, registration=registration)
        cpf = _cpf(row.get("CPF"))
        if cpf:
            links = links.filter(person__cpf=cpf)
        link = links.first()
        if link is None:
            raise RowError(f"vínculo com matrícula {registration} não encontrado — importe antes os servidores")
        kind = _s(row.get("TIPO_EVENTO")).upper()
        if kind not in EventType.values:
            raise RowError(f"TIPO_EVENTO inválido ({', '.join(EventType.values)})")
        start, end = _date(row.get("INICIO")), _date(row.get("FIM"))
        if not start:
            raise RowError("INICIO não informado")
        if end and end < start:
            raise RowError("FIM anterior ao INICIO")
        if start < link.public_service_start:
            raise RowError("evento anterior ao ingresso no serviço público")
        days = _int(row.get("DIAS"))
        if kind == "FALTAS" and not days:
            raise RowError("FALTAS exige DIAS (total de dias no período)")
        counts = _s(row.get("CONTA_TEMPO"))
        counts_as_service = (kind not in ("FALTAS", "SUSPENSAO")) if not counts else self._yes(counts)
        if FunctionalEvent.objects.filter(link=link, event_type=kind, start_date=start).exists():
            self._msg("avisos", name, line, link.person.cpf, f"evento {kind} de {start:%d/%m/%Y} já existe — ignorado")
            return link.person.cpf
        FunctionalEvent.objects.create(
            institution=self.inst, link=link, event_type=kind, start_date=start, end_date=end, days=days,
            with_pay=self._yes(row.get("REMUNERADO")) if _s(row.get("REMUNERADO")) else kind not in ("FALTAS", "SUSPENSAO"),
            contributed=self._yes(row.get("CONTRIBUIU")) if _s(row.get("CONTRIBUIU")) else counts_as_service,
            counts_as_service=counts_as_service, act_type=_s(row.get("NATUREZA_ATO"))[:30],
            act_number=_s(row.get("NUMERO_ATO"))[:30], act_date=_date(row.get("DATA_ATO")),
            publication=_s(row.get("PUBLICACAO"))[:120],
            description=_s(row.get("DESCRICAO")) or EventType(kind).label)
        self._count("eventos_funcionais")
        return link.person.cpf
