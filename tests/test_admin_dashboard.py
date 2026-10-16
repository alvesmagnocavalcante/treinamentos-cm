import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse

from app.models import Aula, Documento, Setor, Treinamento

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog():
    sector = Setor.objects.create(nome="Recepção")
    active = Treinamento.objects.create(setor=sector, titulo="Atendimento")
    inactive = Treinamento.objects.create(setor=sector, titulo="Integração", ativo=False)
    Aula.objects.create(treinamento=active, titulo="Introdução")
    Documento.objects.create(treinamento=active, nome="POP.pdf", arquivo=b"test-pdf", tipo="pdf")
    return active, inactive


def test_dashboard_metrics_and_management_links(staff_client, catalog):
    response = staff_client.get(reverse("admin:index"))
    assert response.status_code == 200
    assert response.templates[0].name == "admin/dashboard.html"
    metrics = {metric["label"]: metric for metric in response.context["metrics"]}
    assert metrics["Setores"]["total"] == 1
    assert metrics["Treinamentos"]["total"] == 2
    assert metrics["Treinamentos"]["ready"] == 1
    assert metrics["Aulas"]["ready"] == 1
    assert metrics["Documentos"]["total"] == 1
    assert metrics["Documentos"]["ready"] == 0
    page = response.content.decode()
    for name in ("admin:app_treinamento_add", "admin:auth_user_changelist", "admin:auth_group_changelist"):
        assert reverse(name) in page
    assert reverse("training_documents", args=[catalog[0].pk]) in page


@pytest.mark.parametrize("params, titles", [
    ({"q": "Atendimento"}, ["Atendimento"]),
    ({"q": "Recepção", "status": "inactive"}, ["Integração"]),
    ({"status": "active"}, ["Atendimento"]),
    ({"q": "Ausente"}, []),
])
def test_dashboard_filters(staff_client, catalog, params, titles):
    response = staff_client.get(reverse("admin:index"), params)
    assert [training.titulo for training in response.context["trainings_page"]] == titles


def test_dashboard_requires_active_staff(client, employee_client):
    assert client.get(reverse("admin:index")).status_code == 302
    assert employee_client.get(reverse("admin:index")).status_code == 302


def test_dashboard_hides_data_without_model_permissions(client, django_user_model, catalog):
    user = django_user_model.objects.create(username="restricted", is_staff=True)
    client.force_login(user)
    response = client.get(reverse("admin:index"))
    assert response.status_code == 200
    assert response.context["metrics"] == []
    assert response.context["trainings_page"] is None
    assert "Atendimento" not in response.content.decode()


def test_dashboard_read_only_permission(client, django_user_model, catalog):
    user = django_user_model.objects.create(username="reader", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="view_treinamento"))
    client.force_login(user)
    response = client.get(reverse("admin:index"))
    assert [metric["label"] for metric in response.context["metrics"]] == ["Treinamentos"]
    page = response.content.decode()
    assert "Consultar" in page
    assert reverse("admin:app_treinamento_add") not in page
    assert reverse("training_documents", args=[catalog[0].pk]) not in page
    assert client.get(reverse("admin:app_treinamento_change", args=[catalog[0].pk])).status_code == 200


def test_dashboard_pagination_and_escaped_search(staff_client, catalog):
    sector = catalog[0].setor
    Treinamento.objects.bulk_create([
        Treinamento(setor=sector, titulo=f"Curso {number:02}") for number in range(23)
    ])
    response = staff_client.get(reverse("admin:index"))
    assert len(response.context["trainings_page"]) == 20
    response = staff_client.get(reverse("admin:index"), {"page": 2})
    assert len(response.context["trainings_page"]) == 5
    response = staff_client.get(reverse("admin:index"), {"q": '<script>alert("x")</script>'})
    assert '<script>alert("x")</script>' not in response.content.decode()


@pytest.mark.parametrize("client_fixture, visible", [("staff_client", True), ("employee_client", False)])
def test_dashboard_link_only_for_staff(request, client_fixture, visible):
    client = request.getfixturevalue(client_fixture)
    assert ('aria-label="Administração"' in client.get("/").content.decode()) is visible
