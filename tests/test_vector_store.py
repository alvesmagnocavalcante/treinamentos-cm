from dataclasses import replace

import pytest

from app.config import Settings
from app.services.chunking import Chunk
from app.services.errors import ServiceError
from app.services.vector_store import VectorStore


@pytest.fixture
def store(tmp_path):
    return VectorStore(Settings(tmp_path / "db.sqlite3", vector_path=tmp_path / "chroma", embedding_dimensions=3))


def add(store, document_id, training_id, texts):
    store.replace_document(document_id, [Chunk(text, 3, "") for text in texts], [[1, 0, 0]] * len(texts),
                           {"treinamento_id": training_id, "documento": f"{document_id}.pdf", "setor": "Recepção"})


def test_chroma_filters_training_and_processed_document_ids(store):
    add(store, 1, 10, ["Early check-in"])
    add(store, 2, 20, ["Documento de outro treinamento"])
    add(store, 3, 10, ["Documento pendente"])
    hits = store.search([1, 0, 0], 10, [1, 2])
    assert len(hits) == 1
    assert hits[0].text == "Early check-in"
    assert hits[0].metadata["pagina"] == 3
    assert store.search([1, 0, 0], 10, []) == []


def test_reindex_removes_stale_chunks_and_delete(store):
    add(store, 1, 10, ["antigo1", "antigo2"])
    add(store, 1, 10, ["novo"])
    assert [hit.text for hit in store.search([1, 0, 0], 10, [1])] == ["novo"]
    assert store.collection.count() == 1
    store.remove_document(1)
    assert store.search([1, 0, 0], 10, [1]) == []


def test_vector_persistence_and_model_mismatch(store):
    add(store, 1, 10, ["persistente"])
    reopened = VectorStore(store.settings)
    assert reopened.search([1, 0, 0], 10, [1])[0].text == "persistente"
    incompatible = VectorStore(replace(store.settings, embedding_model="models/other"))
    with pytest.raises(ServiceError, match="outro modelo"):
        incompatible.search([1, 0, 0], 10, [1])
