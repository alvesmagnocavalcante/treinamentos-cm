import logging
from contextlib import asynccontextmanager
from threading import RLock
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.config import ROOT, Settings
from app.database import Base, create_database
from app.routes.training import router
from app.routes.documents import router as documents_router
from app.routes.chat import router as chat_router
from app.services.documents import DocumentService
from app.services.embeddings import EmbeddingService
from app.services.errors import ServiceError
from app.services.llm import LLMService
from app.services.rag import RagService
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        engine, factory = create_database(settings.database_path)
        application.state.session_factory = factory
        application.state.settings = settings
        application.state.document_lock = RLock()
        try:
            Base.metadata.create_all(engine)
            logger.info("Banco de treinamento inicializado.")
            with httpx.Client(timeout=settings.timeout_seconds, follow_redirects=False) as client:
                embeddings = EmbeddingService(settings, client)
                store = VectorStore(settings)
                application.state.documents = DocumentService(settings, embeddings, store)
                application.state.rag = RagService(embeddings, store, LLMService(settings, client), settings.max_distance)
                yield
        finally:
            engine.dispose()

    application = FastAPI(title="Treinamento interno", lifespan=lifespan)
    application.mount("/static", StaticFiles(directory=ROOT / "app/static"), name="static")
    application.include_router(router)
    application.include_router(documents_router)
    application.include_router(chat_router)

    @application.middleware("http")
    async def request_guards(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and (urlsplit(origin).scheme, urlsplit(origin).netloc) != (request.url.scheme, request.url.netloc):
                return JSONResponse(status_code=403, content={"detail": "Origem da requisição não permitida."})
            raw_length = request.headers.get("content-length")
            is_upload = request.headers.get("content-type", "").startswith("multipart/form-data")
            if is_upload and raw_length is None:
                return JSONResponse(status_code=411, content={"detail": "Upload exige Content-Length."})
            if raw_length and (not raw_length.isdigit() or int(raw_length) > settings.max_upload_bytes + 256 * 1024):
                return JSONResponse(status_code=413, content={"detail": "Requisição excede o tamanho máximo permitido."})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @application.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else None
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)}, headers=headers)

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError):
        # Não registrar SQL/parâmetros: podem conter documentos internos.
        logger.error("Falha de persistência: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Banco indisponível. Tente novamente."})

    @application.exception_handler(OSError)
    async def storage_error(request: Request, exc: OSError):
        logger.error("Falha de armazenamento: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Não foi possível acessar o armazenamento. Verifique espaço e permissões."})

    return application


app = create_app()
