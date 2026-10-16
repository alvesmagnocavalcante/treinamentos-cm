import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_cleanup_preserves_original_and_blocks_documents_without_remote_or_database_source():
    previous = [('app', '0003_documentotrecho_documento_arquivo_and_more')]
    current = [('app', '0004_remove_documento_documento_tem_origem_and_more')]
    executor = MigrationExecutor(connection)
    executor.migrate(previous)
    apps = executor.loader.project_state(previous).apps
    Sector = apps.get_model('app', 'Setor')
    Training = apps.get_model('app', 'Treinamento')
    Document = apps.get_model('app', 'Documento')
    document = None
    try:
        sector = Sector.objects.create(nome='Migration test')
        training = Training.objects.create(setor=sector, titulo='Migration test')
        document = Document.objects.create(treinamento=training, nome='Original.pdf', tipo='pdf', caminho='original.pdf')
        with pytest.raises(RuntimeError, match='documentos'):
            MigrationExecutor(connection).migrate(current)
        document.refresh_from_db()
        assert document.caminho == 'original.pdf'
        Document.objects.filter(pk=document.pk).update(arquivo=b'original-preserved')
        MigrationExecutor(connection).migrate(current)
        from app.models import Documento
        persisted = Documento.objects.get(pk=document.pk)
        assert bytes(persisted.arquivo) == b'original-preserved'
        assert persisted.nome == 'Original.pdf'
    finally:
        if document and document.pk:
            # Mesmo em caso de falha, restaura o esquema esperado pelos demais testes.
            Document.objects.filter(pk=document.pk).update(arquivo=b'original-preserved')
        MigrationExecutor(connection).migrate(current)
