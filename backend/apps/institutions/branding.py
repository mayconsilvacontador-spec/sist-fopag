"""
Identidade visual da instituição: brasão do município contratante e imagem de fundo das telas.

- Envio/remoção: Administração › Instituição (permissão admin.instituicao:editar), registrado na auditoria.
- Leitura pública (sem login), porque o brasão e o fundo também aparecem na tela de login. Só imagens PNG, JPG ou
  WEBP (conferidas pelo conteúdo do arquivo, não pela extensão); SVG não é aceito (pode conter script).
"""
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError

from .models import Institution

KINDS = {"brasao": ("coat_of_arms", "coat_of_arms_type", 2 * 1024 * 1024, "Brasão"),
         "fundo": ("background_image", "background_type", 6 * 1024 * 1024, "Imagem de fundo")}


def sniff(content: bytes) -> tuple[str, str] | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def _kind(kind: str):
    if kind not in KINDS:
        raise Http404
    return KINDS[kind]


class BrandingUploadView(APIView):
    """POST (multipart: file) envia; DELETE remove o brasão ou a imagem de fundo da instituição corrente."""

    module_code = "admin.instituicao"
    action_permissions = {"POST": "editar", "DELETE": "editar"}
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, kind):
        field, type_field, limit, label = _kind(kind)
        upload = request.FILES.get("file")
        if upload is None:
            raise BusinessRuleError("Selecione a imagem.")
        content = upload.read()
        if len(content) > limit:
            raise BusinessRuleError(f"{label}: envie uma imagem de até {limit // (1024 * 1024)} MB.")
        found = sniff(content)
        if found is None:
            raise BusinessRuleError(f"{label}: envie uma imagem PNG, JPG ou WEBP.")
        inst = request.institution
        old = getattr(inst, field)
        if old:
            old.delete(save=False)
        getattr(inst, field).save(f"{inst.short_name.lower()}-{kind}.{found[1]}", ContentFile(content), save=False)
        setattr(inst, type_field, found[0])
        inst.save()
        log_event("UPDATE", module="admin.instituicao", obj=inst, object_repr=f"{label} da instituição atualizado")
        return Response({"ok": True})

    def delete(self, request, kind):
        field, type_field, _, label = _kind(kind)
        inst = request.institution
        f = getattr(inst, field)
        if f:
            f.delete(save=False)
        setattr(inst, type_field, "")
        inst.save()
        log_event("UPDATE", module="admin.instituicao", obj=inst, object_repr=f"{label} da instituição removido")
        return Response(status=204)


def _public_institution(request) -> Institution | None:
    qs = Institution.objects.filter(active=True)
    sigla = (request.query_params.get("inst") or "").strip()
    if sigla:
        return qs.filter(short_name__iexact=sigla).first()
    # Sem sigla (tela de login): a instituição com identidade visual cadastrada (ou a primeira ativa)
    return (qs.exclude(coat_of_arms="").order_by("short_name").first() or qs.order_by("short_name").first())


class PublicBrandingView(APIView):
    """GET branding/ → nome e o que existe de identidade visual (para o login e o menu)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        inst = _public_institution(request)
        if inst is None:
            return Response({"short_name": "", "name": "", "brasao": False, "fundo": False})
        return Response({
            "short_name": inst.short_name, "name": inst.name, "city": inst.city, "uf": inst.uf,
            "brasao": bool(inst.coat_of_arms), "fundo": bool(inst.background_image),
            "intensidade": inst.background_intensity, "versao": int(inst.updated_at.timestamp()),
        })


class PublicBrandingImageView(APIView):
    """GET branding/<brasao|fundo>/ → a imagem."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, kind):
        field, type_field, _, _ = _kind(kind)
        inst = _public_institution(request)
        f = getattr(inst, field) if inst else None
        if not f:
            raise Http404
        resp = FileResponse(f.open("rb"), content_type=getattr(inst, type_field) or "image/png")
        resp["Cache-Control"] = "public, max-age=3600"
        resp["X-Content-Type-Options"] = "nosniff"
        return resp
