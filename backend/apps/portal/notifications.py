"""
Avisos ao segurado: aparecem no sininho do Portal e, se houver celular cadastrado, viram mensagem para o celular.

Envio ao celular: só com provedor contratado (SMS ou WhatsApp Business) é automático. Enquanto não houver, as
mensagens ficam "aguardando envio" na tela Portal do Segurado › Mensagens, com o botão que abre o WhatsApp com o texto
pronto; quem envia confirma. O sistema nunca marca como enviada sem confirmação (regra do projeto).
Parâmetro `portal.mensagens_celular` (padrão: ligado) desliga a geração das mensagens.
"""
from urllib.parse import quote

from apps.core.validators import only_digits

from .models import MessageStatus, OutboundMessage, PortalNotification

PARAM = "portal.mensagens_celular"


def _enabled(institution) -> bool:
    from apps.institutions.services import get_parameter

    v = get_parameter(institution, PARAM, default=True)
    return str(v).lower() not in ("false", "0", "nao", "não")


def mobile_of(person) -> str:
    """Celular com DDD (10 ou 11 dígitos); vazio se não houver um válido."""
    for raw in (person.mobile, person.phone):
        d = only_digits(raw or "")
        if d.startswith("55") and len(d) in (12, 13):
            d = d[2:]
        if len(d) == 11 and d[2] == "9":
            return d
    return ""


def whatsapp_link(phone: str, text: str) -> str:
    return f"https://wa.me/55{phone}?text={quote(text)}"


def notify(person, key: str, title: str, message: str, *, level: str = "INFO", tab: str = "", sms: bool = True):
    """Cria o aviso uma única vez por chave. Devolve (aviso, criado)."""
    n, created = PortalNotification.objects.get_or_create(
        person=person, key=key[:120],
        defaults={"institution_id": person.institution_id, "level": level, "title": title[:150], "message": message,
                  "tab": tab})
    if created and sms and _enabled(person.institution):
        phone = mobile_of(person)
        if phone:
            sigla = person.institution.short_name
            text = f"{sigla}: {title}. {message} Dúvidas: acesse o Portal do Segurado ou procure o {sigla}."
            OutboundMessage.objects.create(institution_id=person.institution_id, person=person, notification=n,
                                           phone=phone, text=text[:600], status=MessageStatus.PENDENTE)
    return n, created
