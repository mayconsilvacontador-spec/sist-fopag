"""
Ficha FATIMA — dados da concessão organizados nos Passos do módulo Deliberação 260 do eTCERJ
(Manual Parte II — Aposentadoria, versão 2023), para transcrição no sistema do TCE-RJ.
O FATIMA só importa por arquivo os Salários de Contribuição (SalContr.txt); os demais dados são digitados.
"""
from apps.core.validators import format_cpf

from .models import BenefitKind, Modality

# Documentos do Passo 7 (Anexo II da Deliberação 260) e quando são exigidos
DOCS = [
    ("II.01", "Ato de concessão e de fixação de proventos (arquivo único)", lambda c: True),
    ("II.02", "Publicação do(s) ato(s)", lambda c: True),
    ("II.03", "Requerimento de inativação (com opção pela regra)",
     lambda c: c.modality not in (Modality.COMPULSORIA, Modality.INCAPACIDADE)),
    ("II.3", "Certidão de tempo de serviço/contribuição do RPPS de origem", lambda c: True),
    ("II.04.1", "Certidões das averbações (INSS / outros RPPS)", lambda c: c.person.averbacoes.filter(active=True).exists()),
    ("II.05", "Laudo médico oficial (junta médica, CID, integral/proporcional)",
     lambda c: c.modality == Modality.INCAPACIDADE),
    ("II.06", "Identidade e CPF do servidor (mesmo arquivo)", lambda c: True),
    ("II.07", "Declaração de acumulação ou não de cargos/proventos", lambda c: True),
    ("II.08", "Comprovante de pagamento da remuneração do mês anterior à inativação", lambda c: True),
    ("II.09", "Comprovante de pagamento dos proventos do mês posterior", lambda c: True),
    ("II.10", "Demonstrativo do cálculo da média das contribuições", lambda c: not c.integralidade),
    ("II.11", "Memória de cálculo dos proventos", lambda c: True),
    ("II.14", "Histórico da vida funcional", lambda c: True),
    ("II.15", "Declaração de efetivo exercício em funções de magistério", lambda c: c.modality == Modality.PROFESSOR),
    ("Judicial", "Íntegra da decisão judicial", lambda c: c.judicial),
]


def ficha(c) -> dict:
    from apps.previdencia.services import time_report

    p, link = c.person, c.link
    tempo = time_report(p, c.validity_date) if c.validity_date else None
    passos = {
        "1_informacoes_iniciais": {
            "servidor": {
                "CPF": format_cpf(p.cpf), "Nome": p.name, "Data de nascimento": p.birth_date.isoformat(),
                "Sexo": p.get_sex_display(), "Órgão": link.organ.name if link else "",
                "Código SIGFIS do órgão": link.organ.sigfis_code if link else "",
                "Matrícula": link.registration if link else "",
                "Cargo inicial": (link.initial_position or link.position).name if link else "",
                "Carreira": link.position.career if link else "",
                "Data de ingresso (cargo de referência)": link.position_start.isoformat() if link else "",
                "Forma de admissão": link.get_admission_form_display() if link else "",
                "Último cargo (se houve enquadramento)": link.position.name if link and link.initial_position else "",
            },
            "aposentadoria": {
                "Nº do processo": c.process.code, "Fundamentação constitucional": c.legal_basis,
                "Modalidade": c.get_modality_display() if c.modality else "",
                "Data do requerimento": c.request_date.isoformat() if c.request_date else "",
                "Nº do ato concessório": c.act_number, "Data de emissão": c.act_date.isoformat() if c.act_date else "",
                "Data de publicação": c.publication_date.isoformat() if c.publication_date else "",
                "Meio de publicação": c.publication_media, "Natureza do ato": c.get_act_nature_display(),
                "Legislação local": c.local_legal_basis,
                "Data de validade": c.validity_date.isoformat() if c.validity_date else "",
                "Classificação da data de validade": c.get_validity_class_display() if c.validity_class else "",
                "Fundamentação legal da data de validade": c.validity_legal_basis,
                "Decorre de decisão judicial": "Sim — " + c.judicial_process if c.judicial else "Não",
                "Causa da incapacidade": c.get_invalidity_cause_display() if c.invalidity_cause else "",
                "CID": c.cid, "Data do laudo médico": c.medical_report_date.isoformat() if c.medical_report_date else "",
            },
        },
        "2_tempo_de_contribuicao": tempo,
        "3_ultima_remuneracao": {
            "competencia": c.calculation.get("competencia_ultima_remuneracao", ""),
            "parcelas": [{"Parcela": x.name, "Integra a remuneração de referência": "Sim" if x.in_reference else "Não",
                          "Percentual": str(x.percent or ""), "Valor": str(x.amount), "Fundamentação": x.legal_basis,
                          "Verba de correlação": x.correlation} for x in c.parcels.filter(kind="REMUNERACAO")],
        },
        "4_salario_de_contribuicao": {
            "media": c.calculation.get("media100") or c.calculation.get("media80") or "",
            "competencias": c.calculation.get("competencias", 0),
            "observacao": "Importe o arquivo SalContr.txt (gerado no Histórico Contributivo) no FATIMA.",
        },
        "5_proventos": {
            "parcelas": [{"Parcela": x.name, "Percentual": str(x.percent or ""),
                          "Fator de proporcionalidade": str(x.proportionality or ""), "Valor": str(x.amount),
                          "Fundamentação": x.legal_basis, "Verba de correlação": x.correlation}
                         for x in c.parcels.filter(kind="PROVENTO")],
            "total": str(c.total or ""), "forma_de_calculo": c.calculation.get("forma", ""),
        },
        "6_acumulacao": {"observacao": "Informe as acumulações declaradas pelo servidor ou marque “Não há acumulação”."},
        "7_documentos": [{"item": code, "documento": desc} for code, desc, need in DOCS if need(c)],
    }
    return {"tipo": c.get_kind_display(), "pensao": c.kind == BenefitKind.PENSAO, "passos": passos,
            "enquadramento": c.analysis.get("regra"), "avisos": c.calculation.get("avisos", [])}
