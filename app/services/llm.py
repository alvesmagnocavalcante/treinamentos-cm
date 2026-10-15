import httpx

from app.config import Settings
from app.services.errors import ServiceError
from app.services.http import post_json


class LLMService:
    def __init__(self, settings: Settings, client: httpx.Client):
        self.settings, self.client = settings, client

    def complete(self, system: str, user: str) -> str:
        if not self.settings.openrouter_api_key:
            raise ServiceError("Configure OPENROUTER_API_KEY para usar o assistente.", 503)
        payload = post_json(
            self.client, "OpenRouter", "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.openrouter_api_key}"},
            json={"model": self.settings.openrouter_model, "temperature": 0, "max_tokens": 1500,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        )
        try:
            choice = payload["choices"][0]
            content = choice["message"]["content"]
            if not isinstance(content, str) or not content.strip() or choice.get("finish_reason") == "length":
                raise ValueError
            return content.strip()
        except (KeyError, IndexError, TypeError, ValueError):
            raise ServiceError("OpenRouter retornou uma resposta vazia, incompleta ou inválida.") from None
