"""Brasão e imagem de fundo da instituição (identidade visual)."""
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_envio_leitura_publica_e_remocao(institution, master, consulta, client_for):
    m = client_for(master)
    # Só imagem de verdade (conferida pelo conteúdo); SVG/texto recusados
    r = m.post("/api/v1/institution/current/branding/brasao/",
               {"file": SimpleUploadedFile("b.svg", b"<svg onload=alert(1)>", content_type="image/svg+xml")},
               format="multipart")
    assert r.status_code == 409
    # Perfil de consulta não altera a identidade visual
    assert client_for(consulta).post("/api/v1/institution/current/branding/brasao/",
                                     {"file": SimpleUploadedFile("b.png", PNG, content_type="image/png")},
                                     format="multipart").status_code == 403
    r = m.post("/api/v1/institution/current/branding/brasao/",
               {"file": SimpleUploadedFile("b.png", PNG, content_type="image/png")}, format="multipart")
    assert r.status_code == 200

    anon = APIClient()  # tela de login: sem sessão
    info = anon.get(f"/api/v1/branding/?inst={institution.short_name}").json()
    assert info["brasao"] is True and info["fundo"] is False
    img = anon.get(f"/api/v1/branding/brasao/?inst={institution.short_name}")
    assert img.status_code == 200 and img["Content-Type"] == "image/png"
    assert b"".join(img.streaming_content) == PNG
    assert anon.get(f"/api/v1/branding/fundo/?inst={institution.short_name}").status_code == 404

    assert m.patch("/api/v1/institution/current/", {"background_intensity": 80}, format="json").status_code == 400
    assert m.patch("/api/v1/institution/current/", {"background_intensity": 30}, format="json").status_code == 200
    assert m.delete("/api/v1/institution/current/branding/brasao/").status_code == 204
    assert anon.get(f"/api/v1/branding/?inst={institution.short_name}").json()["brasao"] is False
