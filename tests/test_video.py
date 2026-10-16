import pytest
from django.core.exceptions import ValidationError

from app.models import Aula, Setor, Treinamento
from app.services.errors import ServiceError
from app.services.video import normalize_video_url, video_preview_url

VIDEO = "https://drive.google.com/file/d/example-video-id/view"


@pytest.mark.parametrize("url",[VIDEO,VIDEO+"?usp=sharing",VIDEO.replace("/view","/preview"),"https://drive.google.com/open?id=example-video-id"])
def test_drive_links_are_canonicalized(url):
    assert normalize_video_url(url) == VIDEO
    assert video_preview_url(url) == VIDEO.replace("/view","/preview")


def test_optional_video_and_resource_key():
    assert normalize_video_url("  ") == ""
    assert video_preview_url("") == ""
    assert video_preview_url(VIDEO+"?resourcekey=key-123&usp=sharing") == VIDEO.replace("/view","/preview?resourcekey=key-123")


def test_preview_preserves_file_id():
    assert video_preview_url("https://drive.google.com/file/d/view-video-id/view") == "https://drive.google.com/file/d/view-video-id/preview"


@pytest.mark.parametrize("url",["javascript:alert(1)","http://drive.google.com/file/d/id/view","https://evil.example/file/d/id/view","https://drive.google.com.evil.example/file/d/id/view","https://drive.google.com@evil.example/file/d/id/view","https://drive.google.com:443/file/d/id/view","https://drive.google.com/drive/folders/id","https://drive.google.com/open?id=../bad",VIDEO+"?resourcekey=bad%22key",VIDEO+"\ninvalid","https://[invalid","https://drive.google.com/"+"x"*2048])
def test_unsafe_links_rejected(url):
    with pytest.raises(ServiceError) as error:
        normalize_video_url(url)
    assert error.value.status_code == 422


@pytest.mark.django_db
def test_video_is_saved_on_lesson_and_displayed(employee_client):
    sector = Setor.objects.create(nome="Recepção")
    training = Treinamento.objects.create(setor=sector,titulo="Early Check-in")
    lesson = Aula(treinamento=training,titulo="Introdução",video_url=VIDEO+"?usp=sharing")
    lesson.full_clean()
    lesson.save()
    assert lesson.video_url == VIDEO
    page = employee_client.get(f"/treinamentos/{training.pk}").content.decode()
    assert f'src="{VIDEO.replace("/view","/preview")}"' in page
    assert f'href="{VIDEO}"' in page
    lesson.video_url = "javascript:alert(1)"
    with pytest.raises(ValidationError):
        lesson.full_clean()
