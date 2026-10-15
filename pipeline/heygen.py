"""Cliente HTTP do HeyGen — gera o vídeo a partir do roteiro APROVADO no gate humano.

Este módulo só deve ser chamado depois que o gate humano do Crew (Task
`human_input=True` no Roteirista, ver `crew.py`) aprovar o roteiro. A chamada é
paga e é ação de escrita real externa: além do gate do Crew, este módulo exige
confirmação explícita via `HEYGEN_AUTORIZAR_CHAMADA=1` (ver §5.3/§6 da spec
`spec-pipeline-videos-pop.md`), para que "kickoff retornou" nunca baste sozinho
para queimar crédito.

Payload e resposta confirmados em 2026-08-23 via documentação oficial
(developers.heygen.com/docs/avatar-looks, /docs/video-agent): a API de geração é
`POST /v3/videos` (corpo `{"type": "avatar", "avatar_id", "voice_id", "script"}`,
resposta `{"data": {"id": ...}}`), e o status é `GET /v3/videos/{video_id}`
(resposta `{"data": {"id", "status", "video_url", "duration", ...}}`). O `v2/video/generate`
usado numa versão anterior deste módulo foi implementado sem consultar a doc e
estava desatualizado/incorreto — substituído por completo nesta revisão.
"""

import os
import re
from typing import Optional

import requests

API_URL = "https://api.heygen.com/v3/videos"
STATUS_URL_TEMPLATE = "https://api.heygen.com/v3/videos/{video_id}"
TIMEOUT_S = 60


class HeyGenNotConfigured(RuntimeError):
    """Falta configuração (API key, avatar, voz) ou autorização para a chamada paga."""


class HeyGenAPIError(RuntimeError):
    """A API do HeyGen respondeu erro. Nunca é engolido: status e corpo são propagados."""


# Aceita "Narração:", "Narracao:", "**Narração:**", "- Narração -", etc.
_RE_NARRACAO = re.compile(
    r"^\s*(?:[-*\d.)\s]*)?(?:\*\*|__)?\s*narra[çc][ãa]o\s*(?:\*\*|__)?\s*[:\-–]\s*(.*)$",
    re.IGNORECASE,
)
# Qualquer outro rótulo de campo encerra a narração multi-linha.
_RE_OUTRO_ROTULO = re.compile(
    r"^\s*(?:[-*\d.)\s]*)?(?:\*\*|__)?\s*"
    r"(visual|cena|etapa|descri[çc][ãa]o visual|aten[çc][ãa]o|texto em tela)"
    r"\s*(?:\*\*|__)?\s*[:\-–]",
    re.IGNORECASE,
)


def extrair_narracoes(roteiro_aprovado: str) -> str:
    """Extrai apenas as linhas de narração do roteiro, na ordem das cenas.

    Nada é inventado nem reescrito: o retorno é exclusivamente texto que veio do
    roteiro aprovado. Se o roteiro não usar o rótulo "Narração:", a extração falha
    de forma explícita em vez de mandar o roteiro inteiro (descrições visuais
    incluídas) para a narração do avatar.
    """
    narracoes: list[str] = []
    capturando = False

    for linha in roteiro_aprovado.splitlines():
        m = _RE_NARRACAO.match(linha)
        if m:
            texto = m.group(1).strip()
            if texto:
                narracoes.append(texto)
            capturando = True
            continue

        if capturando:
            if not linha.strip() or _RE_OUTRO_ROTULO.match(linha):
                capturando = False
                continue
            # Continuação da narração da mesma cena (quebra de linha simples).
            if narracoes:
                narracoes[-1] = f"{narracoes[-1]} {linha.strip()}".strip()
            else:
                narracoes.append(linha.strip())

    if not narracoes:
        raise HeyGenNotConfigured(
            "Nenhuma narração encontrada no roteiro aprovado (esperado o rótulo "
            "'Narração:' por cena, conforme expected_output da tarefa do Roteirista "
            "em pipeline/crew.py). Abortando antes de gastar crédito do HeyGen."
        )

    return "\n\n".join(narracoes)


def _env_obrigatoria(nome: str, descricao: str) -> str:
    valor = (os.environ.get(nome) or "").strip()
    if not valor:
        raise HeyGenNotConfigured(
            f"{nome} não configurada ({descricao}). Preencher no .env — ver .env.example."
        )
    return valor


def consultar_status(video_id: str, api_key: str) -> Optional[dict]:
    """Best-effort: consulta o status do vídeo uma única vez, sem polling.

    Nunca bloqueia nem falha a geração — se a consulta der erro, retorna None. O
    vídeo já foi enfileirado no HeyGen independentemente desta chamada.
    """
    try:
        resp = requests.get(
            STATUS_URL_TEMPLATE.format(video_id=video_id),
            headers={"X-Api-Key": api_key, "Accept": "application/json"},
            timeout=TIMEOUT_S,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except (requests.RequestException, ValueError):
        return None


def gerar_video(roteiro_aprovado: str) -> dict:
    """Gera o vídeo no HeyGen com o avatar/voz da 'Mel' a partir do roteiro aprovado.

    Retorna o corpo da resposta da API (contendo o `video_id`) acrescido do texto
    de narração efetivamente enviado, para rastreabilidade. Levanta
    `HeyGenNotConfigured` se faltar configuração/autorização e `HeyGenAPIError` se
    a API responder erro (status code e corpo sempre propagados).
    """
    api_key = _env_obrigatoria("HEYGEN_API_KEY", "chave de API do painel HeyGen")
    avatar_id = _env_obrigatoria(
        "HEYGEN_AVATAR_ID", "ID do avatar 'Mel' criado no painel HeyGen"
    )
    voice_id = _env_obrigatoria(
        "HEYGEN_VOICE_ID", "ID da voz pt-BR feminina da 'Mel' na biblioteca do HeyGen"
    )

    if (os.environ.get("HEYGEN_AUTORIZAR_CHAMADA") or "").strip() != "1":
        raise HeyGenNotConfigured(
            "Chamada paga ao HeyGen bloqueada. Jadson autorizou 1 chamada de teste "
            "condicionada a roteiro aprovado no gate humano (decisão 6 da §4.3 da "
            "spec). Para executar, definir HEYGEN_AUTORIZAR_CHAMADA=1 no ambiente "
            "desta execução — e só depois de aprovar o roteiro."
        )

    input_text = extrair_narracoes(roteiro_aprovado)

    # Formato confirmado em developers.heygen.com/docs/avatar-looks (POST /v3/videos).
    payload = {
        "type": "avatar",
        "avatar_id": avatar_id,
        "voice_id": voice_id,
        "script": input_text,
    }

    try:
        resp = requests.post(
            API_URL,
            json=payload,
            headers={
                "X-Api-Key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise HeyGenAPIError(f"Falha de rede ao chamar {API_URL}: {exc!r}") from exc

    if resp.status_code >= 400:
        raise HeyGenAPIError(
            f"HeyGen respondeu HTTP {resp.status_code} em {API_URL}. "
            f"Corpo: {resp.text[:2000]}"
        )

    try:
        corpo = resp.json()
    except ValueError as exc:
        raise HeyGenAPIError(
            f"HeyGen respondeu HTTP {resp.status_code} com corpo não-JSON: "
            f"{resp.text[:2000]}"
        ) from exc

    # A API pode responder HTTP 200 com erro no corpo — não engolir.
    if isinstance(corpo, dict) and corpo.get("error"):
        raise HeyGenAPIError(
            f"HeyGen respondeu HTTP {resp.status_code} com erro no corpo: {corpo['error']!r}"
        )

    dados = corpo.get("data") if isinstance(corpo, dict) else None
    video_id = dados.get("id") if isinstance(dados, dict) else None

    resultado = {
        "http_status": resp.status_code,
        "resposta": corpo,
        "video_id": video_id,
        "input_text": input_text,
    }

    if video_id:
        resultado["status_inicial"] = consultar_status(video_id, api_key)

    return resultado
