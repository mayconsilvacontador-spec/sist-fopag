"""
Leitura inteligente de processos.
configuracao/            GET situação · POST {api_key?, model?, enabled?, privacy_ack?} (admin.configuracoes:editar)
configuracao/testar/     testa a chave com uma chamada mínima
leituras/                lista · POST multipart (titulo, arquivos[]) cria a leitura
leituras/<id>/           documentos lidos, campos, conferências e andamento
leituras/<id>/ler/       lê o próximo arquivo da fila (a tela chama até terminar)
leituras/<id>/campo/     {campo, valor?, confirmar?, ignorar?} · confirmar-alta/ · aplicar/ · descartar/
leituras/<id>/arquivo/<arquivo>/   PDF original (para conferir a página) · arquivo/<arquivo>/reler/
"""
from django.http import FileResponse, HttpResponse
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import has_perm
from apps.audit.services import log_event
from apps.core.exceptions import BusinessRuleError
from apps.core.views import InstitutionScopedMixin

from . import reader, services
from .models import ENGINES, MODELS, JobStatus, ReadingJob

CONFIG_PERM = "admin.configuracoes:editar"


def _settings_data(s, can_config: bool):
    return {"motor": s.engine, "motores": [{"value": v, "label": lbl} for v, lbl in ENGINES],
            "pronto": s.engine == "LOCAL" or s.enabled, "ativo": s.enabled, "chave_cadastrada": bool(s.key_hint), "chave_final": s.key_hint, "modelo": s.model,
            "modelos": [{"value": v, "label": lbl} for v, lbl in MODELS], "ciencia_privacidade": s.privacy_ack,
            "ultimo_teste": s.last_test_at, "resultado_teste": s.last_test_result, "pode_configurar": can_config}


class SettingsView(InstitutionScopedMixin, APIView):
    module_code = "concessao.leitura"
    action_permissions = {"GET": "visualizar", "POST": "visualizar"}

    def get(self, request):
        s = services.settings_for(self.get_institution())
        return Response(_settings_data(s, has_perm(request, CONFIG_PERM)))

    def post(self, request):
        if not has_perm(request, CONFIG_PERM):
            raise PermissionDenied("Só quem configura o sistema pode alterar a leitura inteligente.")
        d = request.data

        def flag(k):
            return None if k not in d else str(d[k]).lower() in ("1", "true", "sim", "on")

        s = services.save_settings(self.get_institution(), api_key=d.get("api_key") or None,
                                   model=d.get("model") or None, enabled=flag("enabled"),
                                   privacy_ack=flag("privacy_ack"), engine=d.get("engine") or None)
        return Response(_settings_data(s, True))


class SettingsTestView(InstitutionScopedMixin, APIView):
    module_code = "concessao.leitura"
    action_permissions = {"POST": "visualizar"}

    def post(self, request):
        if not has_perm(request, CONFIG_PERM):
            raise PermissionDenied("Só quem configura o sistema pode testar a chave.")
        return Response({"resultado": services.test_settings(self.get_institution())})


class JobSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    person_name = serializers.CharField(source="person.name", read_only=True, default="")
    andamento = serializers.SerializerMethodField()

    class Meta:
        model = ReadingJob
        fields = ["id", "title", "engine", "status", "status_display", "person", "person_name", "created_at",
                  "created_by_name", "applied_at", "andamento", "concession"]

    def get_andamento(self, o):
        return services.progress(o)


class JobViewSet(InstitutionScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    module_code = "concessao.leitura"
    serializer_class = JobSerializer
    queryset = ReadingJob.objects.select_related("created_by", "person")
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    action_permissions = {"create": "incluir", "ler": "incluir", "campo": "editar", "confirmar_alta": "editar",
                          "linha": "editar", "pagina": "visualizar",
                          "aplicar": "editar", "descartar": "editar", "arquivo": "visualizar", "reler": "incluir",
                          "juntar": "editar", "arquivos": "incluir", "pessoa": "editar", "implantacao": "visualizar",
                          "implantar": "editar"}

    def create(self, request, *args, **kwargs):
        job = services.create_job(self.get_institution(), request.data.get("titulo", ""),
                                  request.FILES.getlist("arquivos"), request.user)
        return Response(JobSerializer(job).data, status=201)

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        files = [{"id": str(f.pk), "nome": f.file_name, "tamanho": f.file_size, "situacao": f.status,
                  "erro": f.error, "documentos": f.result.get("documentos", []), "lido_em": f.read_at,
                  "paginas": f.pages_total, "paginas_lidas": f.pages_done}
                 for f in job.files.all()]
        return Response({**JobSerializer(job).data, "arquivos": files, "conferencias": job.checks,
                         "aplicado": job.applied_summary, "tipos": reader.DOC_TYPES})

    @action(detail=True, methods=["post"])
    def ler(self, request, pk=None):
        return Response(services.read_next(self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def campo(self, request, pk=None):
        d = request.data
        c = services.review_field(self.get_object(), str(d.get("campo", "")),
                                  value=d.get("valor") if "valor" in d else None,
                                  confirm=d.get("confirmar") if "confirmar" in d else None,
                                  ignore=d.get("ignorar") if "ignorar" in d else None)
        return Response(c)

    @action(detail=True, methods=["post"])
    def linha(self, request, pk=None):
        d = request.data
        return Response(services.review_row(self.get_object(), str(d.get("documento", "")), int(d.get("indice", -1)),
                                            str(d.get("coluna", "")), d.get("valor")))

    @action(detail=True, methods=["get"], url_path=r"arquivo/(?P<file_id>[0-9a-f-]+)/pagina/(?P<page>\d+)")
    def pagina(self, request, pk=None, file_id=None, page=None):
        """Imagem da página com o dado destacado (?caixa=x0,y0,x1,y1, coordenadas do PDF)."""
        import pymupdf

        f = self._file(file_id)
        with f.file.open("rb") as fh:
            doc = pymupdf.open(stream=fh.read(), filetype="pdf")
        n = int(page) - 1
        if not 0 <= n < doc.page_count:
            raise BusinessRuleError("Página inexistente.")
        pg = doc[n]
        clip = pg.rect
        try:
            box = [float(v) for v in request.query_params.get("caixa", "").split(",")] if request.query_params.get("caixa") else None
        except ValueError:
            box = None
        if box and len(box) == 4:
            r = pymupdf.Rect(*box)
            pad = max(4.0, pg.rect.width * 0.006)
            pg.draw_rect(r + (-pad, -pad, pad, pad), color=(0.86, 0.15, 0.15), width=max(2.0, pg.rect.width * 0.003))
            h = pg.rect.height * 0.22  # recorte: faixa da página em volta do dado
            clip = pymupdf.Rect(pg.rect.x0, max(pg.rect.y0, r.y0 - h), pg.rect.x1, min(pg.rect.y1, r.y1 + h))
        zoom = 1400 / pg.rect.width
        png = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip).tobytes("png")
        return HttpResponse(png, content_type="image/png")

    @action(detail=True, methods=["post"], url_path="confirmar-alta")
    def confirmar_alta(self, request, pk=None):
        return Response({"confirmados": services.confirm_high(self.get_object())})

    @action(detail=True, methods=["post"])
    def aplicar(self, request, pk=None):
        from apps.cadastros.models import Organ

        inst, d = self.get_institution(), request.data
        organ = Organ.objects.filter(institution=inst, pk=d["orgao"]).first() if d.get("orgao") else None
        res = services.apply(self.get_object(), request.user, organ=organ, segment=d.get("massa") or "",
                             sex=d.get("sexo") or "", ctc_use=d.get("ctc") or {})
        return Response(res)

    @action(detail=True, methods=["post"])
    def descartar(self, request, pk=None):
        job = self.get_object()
        if job.status == JobStatus.APLICADO:
            raise BusinessRuleError("Leitura já aplicada ao cadastro não pode ser descartada.")
        job.status = JobStatus.DESCARTADO
        job.save(update_fields=["status", "updated_at"])
        log_event("UPDATE", module=services.MODULE, obj=job, object_repr=f"Leitura descartada — {job.title}")
        return Response(JobSerializer(job).data)

    def _file(self, file_id):
        f = self.get_object().files.filter(pk=file_id).first()
        if f is None:
            raise BusinessRuleError("Arquivo não encontrado.")
        return f

    @action(detail=True, methods=["get"], url_path=r"arquivo/(?P<file_id>[0-9a-f-]+)")
    def arquivo(self, request, pk=None, file_id=None):
        f = self._file(file_id)
        resp = FileResponse(f.file.open("rb"), content_type="application/pdf")
        resp["Content-Disposition"] = "inline; filename=documento.pdf"
        return resp

    @action(detail=True, methods=["post"], url_path=r"arquivo/(?P<file_id>[0-9a-f-]+)/reler")
    def reler(self, request, pk=None, file_id=None):
        f = self._file(file_id)
        services.retry_file(f)
        return Response(services.progress(f.job))

    # ------------------------------------------------------------ processo digitalizado (implantacao.py)
    @action(detail=True, methods=["post"])
    def juntar(self, request, pk=None):
        """{leituras: [ids]} — leva os arquivos das outras leituras para esta."""
        from .implantacao import merge

        ids = request.data.get("leituras") or []
        sources = list(self.get_queryset().filter(pk__in=ids))
        job = merge(self.get_object(), sources, request.user)
        return Response(JobSerializer(job).data)

    @action(detail=True, methods=["post"])
    def arquivos(self, request, pk=None):
        from .implantacao import add_files

        job = add_files(self.get_object(), request.FILES.getlist("arquivos"))
        return Response(JobSerializer(job).data)

    @action(detail=True, methods=["post"])
    def pessoa(self, request, pk=None):
        """{pessoa: id | null} — escolhe a pessoa quando os documentos não trazem CPF."""
        from apps.people.models import Person

        from .implantacao import set_person

        pid = request.data.get("pessoa")
        person = Person.objects.filter(institution=self.get_institution(), pk=pid).first() if pid else None
        if pid and person is None:
            raise BusinessRuleError("Pessoa não encontrada.")
        return Response(JobSerializer(set_person(self.get_object(), person)).data)

    @action(detail=True, methods=["get"])
    def implantacao(self, request, pk=None):
        from .implantacao import prefill

        job = self.get_object()
        if not job.person_id:
            raise BusinessRuleError("Aplique a leitura à Pasta do Servidor primeiro.")
        return Response(prefill(job))

    @action(detail=True, methods=["post"])
    def implantar(self, request, pk=None):
        """Implanta na folha a aposentadoria já concedida (exige permissão de implantação e a senha)."""
        from apps.accounts.permissions import has_perm
        from apps.concessao.workflow import confirm_password

        from .implantacao import implant

        if not has_perm(request, "concessao.implantacao:aprovar"):
            raise PermissionDenied("Seu perfil não pode implantar benefícios na folha.")
        confirm_password(request.user, request.data.get("password", ""))
        return Response(implant(request, self.get_object(), request.data), status=201)
