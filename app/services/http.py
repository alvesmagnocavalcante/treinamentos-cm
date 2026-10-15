import logging

import httpx

from app.services.errors import ServiceError

logger = logging.getLogger(__name__)


def post_json(client: httpx.Client, provider: str, url: str, **kwargs) -> dict:
    """Uma tentativa por ação: não repetir automaticamente chamadas cobradas."""
    try:
        response = client.post(url, **kwargs)
    except httpx.TimeoutException:
        logger.warning("Timeout no provedor %s", provider)
        raise ServiceError(f"{provider}: tempo de resposta excedido. Tente novamente.", 504) from None
    except httpx.RequestError:
        logger.warning("Falha de conexão no provedor %s", provider)
        raise ServiceError(f"Não foi possível conectar ao {provider}.", 503) from None

    status = response.status_code
    if status >= 400:
        logger.warning("Provedor %s retornou HTTP %s", provider, status)
        if status == 429:
            raw = response.headers.get("retry-after", "60")
            retry = min(int(raw), 3600) if raw.isdigit() else 60
            raise ServiceError(f"{provider}: limite de requisições atingido. Aguarde antes de tentar novamente.", 429, retry)
        if status in (401, 403):
            raise ServiceError(f"{provider}: credencial inválida ou sem acesso. Verifique a configuração.", 503)
        if status == 402:
            raise ServiceError(f"{provider}: saldo ou cota insuficiente.", 503)
        if status in (404, 400, 422, 503):
            raise ServiceError(f"{provider}: modelo indisponível ou configuração não aceita. Verifique o modelo configurado.", 503)
        raise ServiceError(f"{provider} temporariamente indisponível.", 502)
    try:
        payload = response.json()
    except ValueError:
        raise ServiceError(f"{provider} retornou uma resposta inválida.") from None
    if not isinstance(payload, dict) or payload.get("error"):
        raise ServiceError(f"{provider} retornou uma resposta inválida ou erro de processamento.")
    return payload
