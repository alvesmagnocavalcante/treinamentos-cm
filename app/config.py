import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default="", repr=False)
    google_api_key: str = field(default="", repr=False)
    embedding_model: str = "models/gemini-embedding-001"
    embedding_dimensions: int = 768
    openrouter_api_key: str = field(default="", repr=False)
    openrouter_model: str = "openrouter/free"
    timeout_seconds: float = 60
    max_upload_bytes: int = 10 * 1024 * 1024
    chunk_tokens: int = 1000
    overlap_tokens: int = 150
    max_distance: float = 0.5

    def __post_init__(self):
        if not 0 <= self.overlap_tokens < self.chunk_tokens <= 2000:
            raise ValueError("CHUNK_TOKENS deve ser <= 2000 e maior que CHUNK_OVERLAP_TOKENS.")
        if self.max_upload_bytes <= 0 or self.timeout_seconds <= 0:
            raise ValueError("Tamanho máximo e timeout devem ser positivos.")
        if not 0 <= self.max_distance <= 2 or not 1 <= self.embedding_dimensions <= 3072:
            raise ValueError("Distância ou dimensionalidade inválida.")

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(ROOT / ".env")
        return cls(
            database_url=os.getenv("DATABASE_URL", "").strip(),
            google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
            embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001").strip(),
            embedding_dimensions=int(os.getenv("GEMINI_EMBEDDING_DIMENSIONS", "768")),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
            openrouter_model=os.getenv("OPENROUTER_MODEL", "openrouter/free").strip(),
            timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "60")),
            max_upload_bytes=int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024,
            chunk_tokens=int(os.getenv("CHUNK_TOKENS", "1000")),
            overlap_tokens=int(os.getenv("CHUNK_OVERLAP_TOKENS", "150")),
            max_distance=float(os.getenv("RAG_MAX_DISTANCE", "0.5")),
        )
