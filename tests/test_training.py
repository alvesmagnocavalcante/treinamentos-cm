import json
import re

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client

from app.models import Aula, Documento, Setor, Treinamento

pytestmark = pytest.mark.django_db


@pytest.fixture
def training():
    sector = Setor.objects.create(nome="Recepção")
    return Treinamento.objects.create(setor=sector, titulo="Early Check-in")


def test_authentication_required(client, training):
    assert client.get("/").status_code == 302
    assert client.get(f"/treinamentos/{training.pk}").status_code == 302
    assert client.get("/documentos/1/arquivo").status_code == 302
    response = client.post(f"/treinamentos/{training.pk}/perguntar", data=json.dumps({"pergunta":"Teste"}), content_type="application/json")
    assert response.status_code == 401
    assert client.get("/conta/entrar/").status_code == 200


def test_employee_pages_and_admin_access(employee_client, training):
    page = employee_client.get(f"/treinamentos/{training.pk}")
    assert page.status_code == 200
    assert "Early Check-in" in page.content.decode()
    assert 'href="/admin' not in page.content.decode()
    assert "csrfmiddlewaretoken" in page.content.decode()
    assert employee_client.get("/admin/").status_code == 302
    assert employee_client.get(f"/admin/treinamentos/{training.pk}/documentos").status_code == 302


def test_admin_registered_models_and_forms(staff_client):
    response = staff_client.get("/admin/")
    assert response.status_code == 200
    assert "Treinamentos" in response.content.decode()
    assert staff_client.post("/admin/app/setor/add/", {"nome":"Recepção","descricao":"","_save":"Salvar"}).status_code == 302
    assert Setor.objects.get().nome == "Recepção"
    for model in ("setor","treinamento","aula","documento"):
        assert staff_client.get(f"/admin/app/{model}/").status_code == 200


def test_multiple_lessons_keep_training_rag_scope(employee_client, training):
    first = Aula.objects.create(treinamento=training, titulo="Introdução", ordem=1, conteudo="Explicação da primeira aula.")
    second = Aula.objects.create(treinamento=training, titulo="Disponibilidade", ordem=2, video_url="https://drive.google.com/file/d/video-two/view")
    hidden = Aula.objects.create(treinamento=training, titulo="Rascunho confidencial", ordem=3, ativo=False)
    page = employee_client.get(f"/treinamentos/{training.pk}")
    assert page.status_code == 200
    assert "Explicação da primeira aula." in page.content.decode()
    assert "Aulas do treinamento" in page.content.decode()
    assert hidden.titulo not in page.content.decode()
    page = employee_client.get(f"/treinamentos/{training.pk}?aula={second.pk}")
    assert f'src="/aulas/{second.pk}/video"' in page.content.decode()
    assert "Explicação da primeira aula." not in page.content.decode()
    assert employee_client.get(f"/treinamentos/{training.pk}?aula={hidden.pk}").status_code == 404
    assert employee_client.get(f"/treinamentos/{training.pk}?aula=bad").status_code == 404
    other = Treinamento.objects.create(setor=training.setor, titulo="Outro")
    foreign = Aula.objects.create(treinamento=other, titulo="Outra", ordem=1)
    assert employee_client.get(f"/treinamentos/{training.pk}?aula={foreign.pk}").status_code == 404
    result = employee_client.post(f"/treinamentos/{training.pk}/perguntar", {"pergunta":"Como proceder?"}, content_type="application/json")
    assert result.status_code == 409
    assert "indexação" in result.json()["detail"]


def test_inactive_and_missing_training(employee_client, training):
    training.ativo = False
    training.save()
    assert "Early Check-in" not in employee_client.get("/").content.decode()
    assert employee_client.get(f"/treinamentos/{training.pk}").status_code == 404
    assert employee_client.get("/treinamentos/999").status_code == 404


def test_user_content_is_escaped(employee_client, training):
    training.titulo = "<script>alert(1)</script>"
    training.save()
    Aula.objects.create(treinamento=training, titulo="Explicação", conteudo="<img src=x onerror=alert(1)>")
    page = employee_client.get(f"/treinamentos/{training.pk}").content.decode()
    assert "<script>" not in page
    assert "<img src=x" not in page
    assert "&lt;script&gt;" in page
    assert "&lt;img" in page


@pytest.mark.parametrize("name", ["", "   ", "a"*101])
def test_sector_validation(name):
    with pytest.raises(ValidationError):
        Setor(nome=name).full_clean()


def test_lesson_validation_and_unique_order(training):
    Aula.objects.create(treinamento=training,titulo="Introdução",ordem=1)
    with pytest.raises(ValidationError):
        Aula(treinamento=training,titulo="Duplicada",ordem=1).full_clean()
    with pytest.raises(ValidationError):
        Aula(treinamento=training,titulo="Inválida",ordem=0).full_clean()
    with pytest.raises(ValidationError):
        Aula(treinamento=training,titulo="Vídeo",ordem=2,video_url="javascript:alert(1)").full_clean()
    with transaction.atomic(), pytest.raises(IntegrityError):
        Aula.objects.create(treinamento=training,titulo="Duplicada",ordem=1)


def test_parent_deletion_does_not_orphan_documents(training):
    Documento.objects.create(treinamento=training,nome="POP.pdf",caminho="file.pdf",tipo="pdf")
    with pytest.raises(ProtectedError):
        training.delete()
    with pytest.raises(ProtectedError):
        training.setor.delete()


def test_missing_original_is_not_exposed_or_used_in_rag(staff_client,training,platform_settings):
    document = Documento.objects.create(treinamento=training,nome="Ausente.pdf",caminho="missing.pdf",tipo="pdf",processado=True)
    page = staff_client.get(f"/treinamentos/{training.pk}").content.decode()
    assert f'href="/documentos/{document.pk}/arquivo"' not in page
    status = staff_client.get(f"/admin/treinamentos/{training.pk}/documentos").content.decode()
    assert "Arquivo ausente" in status
    response = staff_client.post(f"/treinamentos/{training.pk}/perguntar",{"pergunta":"Como proceder?"},content_type="application/json")
    assert response.status_code == 409
    assert "indexação" in response.json()["detail"]


def test_staff_needs_explicit_document_permissions(client,django_user_model,training):
    user = django_user_model.objects.create(username="staff_sem_permissao",is_staff=True)
    client.force_login(user)
    url = f"/admin/treinamentos/{training.pk}/documentos"
    assert client.get(url).status_code == 403
    user.user_permissions.add(Permission.objects.get(codename="view_documento"))
    assert client.get(url).status_code == 200
    assert client.post(url).status_code == 403


def test_csrf_protects_chat_upload_logout(employee_client,training,django_user_model):
    client = Client(enforce_csrf_checks=True)
    client.force_login(django_user_model.objects.get(username="colaborador"))
    url = f"/treinamentos/{training.pk}/perguntar"
    assert client.post(url,{"pergunta":"Teste"},content_type="application/json").status_code == 403
    page = client.get(f"/treinamentos/{training.pk}").content.decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',page).group(1)
    assert client.post(url,{"pergunta":"Teste"},content_type="application/json",HTTP_X_CSRFTOKEN=token).status_code == 409
    assert client.post(url,{"pergunta":"Teste"},content_type="application/json",HTTP_X_CSRFTOKEN=token,HTTP_ORIGIN="https://evil.example").status_code == 403
    assert client.post("/conta/sair/").status_code == 403
    assert client.get("/conta/sair/").status_code == 405


def test_login_and_logout(client,django_user_model):
    user = django_user_model.objects.create_user(username="teste_login", password="senha-ficticia-apenas-teste-123")
    assert client.post("/conta/entrar/",{"username":user.username,"password":"errada"}).status_code == 200
    assert "_auth_user_id" not in client.session
    assert client.post("/conta/entrar/",{"username":user.username,"password":"senha-ficticia-apenas-teste-123","next":"https://evil.example"}).url == "/"
    assert client.post("/conta/sair/").status_code == 302
    assert "_auth_user_id" not in client.session


@pytest.mark.parametrize("body",[{},{"pergunta":" "},{"pergunta":"a"*2001},{"pergunta":"ok","training_id":2},{"pergunta":1},[],None])
def test_question_validation(employee_client,training,body):
    response = employee_client.post(f"/treinamentos/{training.pk}/perguntar",data=json.dumps(body),content_type="application/json")
    assert response.status_code == 422
