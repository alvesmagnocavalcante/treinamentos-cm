import httpx
import pytest
from django.urls import reverse

from app.models import Aula, Setor, Treinamento

pytestmark = pytest.mark.django_db


@pytest.fixture
def lesson():
    sector = Setor.objects.create(nome="RH")
    training = Treinamento.objects.create(setor=sector, titulo="Integração")
    return Aula.objects.create(
        treinamento=training, titulo="Boas-vindas",
        video_url="https://drive.google.com/file/d/video-id/view?resourcekey=key-123",
    )


@pytest.fixture
def upstream(monkeypatch):
    original_client = httpx.Client
    state = {"status": 206, "type": "video/mp4", "body": b"video-bytes", "clients": [], "requests": []}

    def handler(request):
        state["requests"].append(request)
        if state.get("error"):
            raise state["error"]
        return httpx.Response(state["status"], content=state["body"], headers={
            "Content-Type": state["type"], "Content-Range": "bytes 0-10/100",
            "Accept-Ranges": "bytes",
        })

    def client(**kwargs):
        instance = original_client(transport=httpx.MockTransport(handler), **kwargs)
        state["clients"].append(instance)
        return instance

    monkeypatch.setattr("app.services.video.httpx.Client", client)
    return state


def test_video_stream_requires_login(client, lesson, upstream):
    assert client.get(reverse("lesson_video", args=[lesson.pk])).status_code == 302
    assert not upstream["requests"]


def test_stream_forwards_range_and_preserves_resource_key(employee_client, lesson, upstream):
    response = employee_client.get(reverse("lesson_video", args=[lesson.pk]), HTTP_RANGE="bytes=0-10")
    assert response.status_code == 206
    assert response["Content-Range"] == "bytes 0-10/100"
    assert response["Accept-Ranges"] == "bytes"
    assert response["Cache-Control"] == "private, no-store"
    assert b"".join(response.streaming_content) == b"video-bytes"
    request = upstream["requests"][0]
    assert request.headers["Range"] == "bytes=0-10"
    assert request.url.host == "drive.usercontent.google.com"
    assert dict(request.url.params) == {"id": "video-id", "export": "download", "resourcekey": "key-123"}
    assert upstream["clients"][0].is_closed


def test_stream_closes_if_browser_cancels_before_reading(employee_client, lesson, upstream):
    response = employee_client.get(reverse("lesson_video", args=[lesson.pk]))
    assert not upstream["clients"][0].is_closed
    response.close()
    assert upstream["clients"][0].is_closed


def test_head_closes_upstream_without_streaming(employee_client, lesson, upstream):
    response = employee_client.head(reverse("lesson_video", args=[lesson.pk]))
    assert response.status_code == 206
    assert response.content == b""
    assert upstream["requests"][0].method == "HEAD"
    assert upstream["clients"][0].is_closed


@pytest.mark.parametrize("value", ["bytes=-", "bytes=-0", "bytes=10-2", "bytes=0-1,4-5", "items=0-10", "bytes=" + "9" * 100 + "-"])
def test_invalid_ranges_do_not_contact_drive(employee_client, lesson, upstream, value):
    assert employee_client.get(reverse("lesson_video", args=[lesson.pk]), HTTP_RANGE=value).status_code == 416
    assert not upstream["clients"]


@pytest.mark.parametrize("target", ["lesson", "training"])
def test_inactive_content_is_not_streamed(employee_client, lesson, upstream, target):
    model = lesson if target == "lesson" else lesson.treinamento
    model.ativo = False
    model.save()
    assert employee_client.get(reverse("lesson_video", args=[lesson.pk])).status_code == 404
    assert not upstream["requests"]


@pytest.mark.parametrize("status,content_type,expected", [
    (200, "text/html", 503), (302, "text/html", 503), (403, "text/html", 503),
    (429, "text/html", 503), (416, "text/html", 416),
])
def test_provider_errors_and_login_pages_are_not_streamed(employee_client, lesson, upstream, status, content_type, expected):
    upstream.update(status=status, type=content_type, body=b"private upstream details")
    response = employee_client.get(reverse("lesson_video", args=[lesson.pk]))
    assert response.status_code == expected
    assert b"private upstream details" not in response.content
    assert upstream["clients"][0].is_closed
    assert not upstream["clients"][0].follow_redirects


def test_network_failure_closes_client(employee_client, lesson, upstream):
    upstream["error"] = httpx.ReadTimeout("upstream details")
    response = employee_client.get(reverse("lesson_video", args=[lesson.pk]))
    assert response.status_code == 503
    assert b"upstream details" not in response.content
    assert upstream["clients"][0].is_closed


@pytest.mark.parametrize("url,expected", [("", 404), ("http://169.254.169.254/", 422)])
def test_empty_or_unsafe_source_does_not_contact_network(employee_client, lesson, upstream, url, expected):
    lesson.video_url = url
    lesson.save()
    assert employee_client.get(reverse("lesson_video", args=[lesson.pk])).status_code == expected
    assert not upstream["clients"]
