from unittest.mock import Mock

import pytest

from app.services.rag import NOT_FOUND, RagService
from app.services.vector_store import SearchHit


def services(hits, answer="Consulte a disponibilidade [1]."):
    embeddings, store, llm = Mock(), Mock(), Mock()
    embeddings.embed_text.return_value = [1, 0, 0]
    store.search.return_value = hits
    llm.complete.return_value = answer
    return RagService(embeddings, store, llm, 0.5)


def hit(training=1, document=1, distance=0.1):
    return SearchHit("Consulte a disponibilidade.", {
        "treinamento_id": training, "documento_id": document, "documento": "POP.pdf", "pagina": 3,
    }, distance)


def test_rag_context_citations_and_scope():
    rag = services([hit()])
    result = rag.answer("Como proceder?", 1, [1])
    assert result["fontes"][0]["pagina"] == 3
    assert result["fontes"][0]["documento"] == "POP.pdf"
    rag.store.search.assert_called_once_with([1, 0, 0], 1, [1], top_k=5)
    system, user = rag.llm.complete.call_args.args
    assert "Não invente" in system
    assert "Consulte a disponibilidade." in user
    assert "Como proceder?" in user


@pytest.mark.parametrize("hits", [[], [hit(distance=0.9)], [hit(training=2)], [hit(document=3)]])
def test_no_relevant_context_does_not_call_llm(hits):
    rag = services(hits)
    assert rag.answer("Como proceder?", 1, [1]) == {"resposta": NOT_FOUND, "fontes": []}
    rag.llm.complete.assert_not_called()


def test_no_documents_skips_all_providers():
    rag = services([])
    assert rag.answer("Como proceder?", 1, []) == {"resposta": NOT_FOUND, "fontes": []}
    rag.embeddings.embed_text.assert_not_called()


@pytest.mark.parametrize("answer", [NOT_FOUND, "Resposta sem citação.", "Resposta [99].", "Resposta [1] [2]."])
def test_unsupported_or_invalid_citations_abstain(answer):
    rag = services([hit()], answer)
    assert rag.answer("Como proceder?", 1, [1]) == {"resposta": NOT_FOUND, "fontes": []}


def test_only_cited_sources_are_returned():
    rag = services([hit(), hit(document=2)], "Consulte [2].")
    result = rag.answer("Como proceder?", 1, [1, 2])
    assert len(result["fontes"]) == 1
    assert result["fontes"][0]["documento_id"] == 2
