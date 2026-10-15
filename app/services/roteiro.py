from app.config import Settings
from app.database import create_database
from app.models import Documento
from app.services.errors import ServiceError
from app.services.ingest import stored_path


def document_path(document_id: int, settings: Settings):
    if not settings.database_path.is_file():
        raise ServiceError("Banco não encontrado. Cadastre um treinamento e envie um documento.", 404)
    engine, factory = create_database(settings.database_path)
    try:
        with factory() as session:
            document = session.get(Documento, document_id)
            if document is None:
                raise ServiceError("Documento não encontrado.", 404)
            return stored_path(settings.documents_path, document.caminho)
    finally:
        engine.dispose()


def generate_script(path: str) -> tuple[str, str]:
    # Importação tardia: servidor web e RAG não dependem do runtime CrewAI.
    from pipeline.crew import build_crew
    from pipeline.ingest import pop_to_markdown

    markdown = pop_to_markdown(path)
    crew = build_crew(markdown)
    result = crew.kickoff(inputs={"pop_markdown": markdown})
    return str(crew.tasks[0].output), str(result)
