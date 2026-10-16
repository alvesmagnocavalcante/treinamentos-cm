import json

import httpx
import pytest

from app.config import Settings
from app.services.embeddings import EmbeddingService
from app.services.errors import ServiceError
from app.services.llm import LLMService


def settings(tmp_path):
    return Settings(google_api_key="secret-google", openrouter_api_key="secret-router", embedding_dimensions=3)


def test_embedding_batches_query_type_and_normalization(tmp_path):
    requests = []

    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.headers["x-goog-api-key"] == "secret-google"
        return httpx.Response(200, json={"embeddings": [{"values": [3, 4, 0]} for _ in payload["requests"]]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        service = EmbeddingService(settings(tmp_path), client)
        assert service.embed_text("pergunta") == [0.6, 0.8, 0]
        assert requests[0]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"
        assert len(service.embed_documents(["documento"] * 34)) == 34
        assert [len(item["requests"]) for item in requests] == [1, 32, 2]
        assert requests[1]["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"


@pytest.mark.parametrize("payload", [{}, {"embeddings": []}, {"embeddings": [{"values": [0, 0, 0]}]},
                                      {"embeddings": [{"values": [1, 2]}]}, {"embeddings": [{"values": [True, 2, 3]}]}])
def test_invalid_embeddings(tmp_path, payload):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as client:
        with pytest.raises(ServiceError):
            EmbeddingService(settings(tmp_path), client).embed_text("pergunta")


def test_openrouter_request_and_content(tmp_path):
    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "openrouter/free"
        assert payload["messages"] == [{"role": "system", "content": "regras"}, {"role": "user", "content": "contexto"}]
        return httpx.Response(200, json={"choices": [{"message": {"content": "Resposta [1]"}, "finish_reason": "stop"}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert LLMService(settings(tmp_path), client).complete("regras", "contexto") == "Resposta [1]"


@pytest.mark.parametrize("status, expected", [(401, 503), (402, 503), (403, 503), (404, 503), (429, 429), (500, 502), (503, 503)])
def test_provider_errors_do_not_leak_keys(tmp_path, caplog, status, expected):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(
        status, text="secret-router secret-google", headers={"Retry-After": "12"}
    ))) as client:
        for service in (LLMService(settings(tmp_path), client), EmbeddingService(settings(tmp_path), client)):
            with pytest.raises(ServiceError) as error:
                service.complete("", "") if isinstance(service, LLMService) else service.embed_text("teste")
            assert error.value.status_code == expected
            if status == 429:
                assert error.value.retry_after == 12
            assert "secret" not in str(error.value)
    assert "secret" not in caplog.text


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{"message": {"content": ""}}]},
                                      {"choices": [{"message": {"content": "cortado"}, "finish_reason": "length"}]},
                                      {"error": {"message": "erro interno"}}])
def test_invalid_openrouter_response(tmp_path, payload):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload))) as client:
        with pytest.raises(ServiceError):
            LLMService(settings(tmp_path), client).complete("", "")


def test_timeout_and_invalid_json(tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout("secret-router", request=request)

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ServiceError) as error:
            LLMService(settings(tmp_path), client).complete("", "")
        assert error.value.status_code == 504
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="invalid"))) as client:
        with pytest.raises(ServiceError):
            LLMService(settings(tmp_path), client).complete("", "")


def test_missing_keys_do_not_call_network(tmp_path):
    def forbidden(request):
        pytest.fail("Chamada de rede indevida")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        empty = Settings()
        for function in (lambda: LLMService(empty, client).complete("", ""), lambda: EmbeddingService(empty, client).embed_text("test")):
            with pytest.raises(ServiceError, match="Configure"):
                function()
