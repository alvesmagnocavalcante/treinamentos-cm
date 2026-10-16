import hashlib
import sqlite3
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from app.models import Aula, Documento, Setor, Treinamento

pytestmark = pytest.mark.django_db


@pytest.fixture
def legacy(tmp_path, platform_settings):
    path = tmp_path / "legacy.sqlite3"
    platform_settings.documents_path.mkdir()
    (platform_settings.documents_path / "source.pdf").write_bytes(b"%PDF- legacy fixture")
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE setores(id INTEGER PRIMARY KEY,nome TEXT,descricao TEXT);
            CREATE TABLE treinamentos(id INTEGER PRIMARY KEY,setor_id INTEGER,titulo TEXT,descricao TEXT,conteudo TEXT,video_url TEXT,ativo INTEGER);
            CREATE TABLE documentos(id INTEGER PRIMARY KEY,treinamento_id INTEGER,nome TEXT,caminho TEXT,tipo TEXT,processado INTEGER,criado_em TEXT);
            INSERT INTO setores VALUES(7,'Recepção','Setor original');
            INSERT INTO treinamentos VALUES(12,7,'Early Check-in','Descrição','Texto existente','https://drive.google.com/file/d/legacy-video/view?usp=sharing',1);
            INSERT INTO documentos VALUES(33,12,'POP.pdf','source.pdf','pdf',1,'2026-08-23 13:20:00');
        """)
    return path


def import_source(path):
    call_command("import_legacy",database=path,stdout=StringIO())


def test_import_preserves_ids_source_bytes_and_lesson(legacy):
    before = hashlib.sha256(legacy.read_bytes()).hexdigest()
    import_source(legacy)
    assert Setor.objects.get(pk=7).nome == "Recepção"
    assert Treinamento.objects.get(pk=12).setor_id == 7
    document = Documento.objects.get(pk=33)
    assert document.treinamento_id == 12
    assert document.caminho == "source.pdf"
    assert document.processado
    assert document.criado_em.isoformat() == "2026-08-23T13:20:00+00:00"
    lesson = Aula.objects.get(treinamento_id=12)
    assert lesson.conteudo == "Texto existente"
    assert lesson.video_url == "https://drive.google.com/file/d/legacy-video/view"
    assert hashlib.sha256(legacy.read_bytes()).hexdigest() == before
    import_source(legacy)
    assert Setor.objects.count() == Treinamento.objects.count() == Documento.objects.count() == Aula.objects.count() == 1


def test_conflicting_ids_roll_back_import(legacy):
    Setor.objects.create(pk=7,nome="Outro setor")
    with pytest.raises(CommandError,match="conflitantes"):
        import_source(legacy)
    assert Setor.objects.get(pk=7).nome == "Outro setor"
    assert not Treinamento.objects.exists()
    assert not Documento.objects.exists()


def test_import_invalid_video_is_atomic(legacy):
    with sqlite3.connect(legacy) as db:
        db.execute("UPDATE treinamentos SET video_url='https://evil.example/video'")
    with pytest.raises(CommandError,match="inválidos"):
        import_source(legacy)
    assert not Setor.objects.exists()
    assert not Treinamento.objects.exists()


def test_import_missing_file_is_pending(legacy, platform_settings):
    (platform_settings.documents_path / "source.pdf").unlink()
    import_source(legacy)
    assert not Documento.objects.get(pk=33).processado


def test_import_rejects_path_traversal_and_rolls_back(legacy):
    with sqlite3.connect(legacy) as db:
        db.execute("UPDATE documentos SET caminho='../outside.pdf'")
    with pytest.raises(CommandError,match="caminho inválido"):
        import_source(legacy)
    assert not Setor.objects.exists()
    assert not Treinamento.objects.exists()
    assert not Aula.objects.exists()


def test_import_missing_source_does_not_create_file(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(CommandError,match="não encontrado"):
        import_source(path)
    assert not path.exists()


def test_import_legacy_without_video_column(legacy):
    with sqlite3.connect(legacy) as db:
        db.execute("ALTER TABLE treinamentos DROP COLUMN video_url")
    import_source(legacy)
    lesson = Aula.objects.get()
    assert lesson.video_url == ""
    assert lesson.conteudo == "Texto existente"
