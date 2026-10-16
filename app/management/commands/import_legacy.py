import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.config import ROOT
from app.models import Aula, Documento, Setor, Treinamento
from app.services.errors import ServiceError
from app.services.video import normalize_video_url


class Command(BaseCommand):
    help = "Importa o SQLite anterior em modo somente leitura, preservando IDs e arquivos."

    def add_arguments(self, parser):
        parser.add_argument("--database", type=Path, help="Caminho do SQLite FastAPI anterior")

    def handle(self, *args, **options):
        source = options["database"] or Path(os.getenv("LEGACY_DATABASE_PATH", os.getenv("DATABASE_PATH", "app/database/training.sqlite3")))
        source = source if source.is_absolute() else ROOT / source
        source = source.resolve()
        target = Path(settings.DATABASES["default"]["NAME"]).resolve()
        if source == target:
            raise CommandError("O banco de origem deve ser diferente do banco Django.")
        if not source.is_file():
            raise CommandError("Banco legado não encontrado. Use --database <arquivo>.")
        try:
            with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as legacy:
                legacy.row_factory = sqlite3.Row
                # Tabelas constantes; o caminho recebido nunca compõe SQL.
                sectors = list(legacy.execute("SELECT * FROM setores ORDER BY id"))
                trainings = list(legacy.execute("SELECT * FROM treinamentos ORDER BY id"))
                documents = list(legacy.execute("SELECT * FROM documentos ORDER BY id"))
            with transaction.atomic():
                for row in sectors:
                    self.insert(Setor, row["id"], {"nome": row["nome"], "descricao": row["descricao"]})
                for row in trainings:
                    self.insert(Treinamento, row["id"], {
                        "setor_id": row["setor_id"], "titulo": row["titulo"],
                        "descricao": row["descricao"], "ativo": bool(row["ativo"]),
                    })
                    self.lesson(row)
                missing = 0
                for row in documents:
                    filename = row["caminho"]
                    root = settings.SERVICE_SETTINGS.documents_path.resolve()
                    path = (root / filename).resolve()
                    if path.parent != root or path.suffix not in {".pdf", ".docx"}:
                        raise CommandError("Documento legado com caminho inválido. Importação cancelada.")
                    exists = path.is_file()
                    missing += not exists
                    created = datetime.fromisoformat(row["criado_em"])
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    self.insert(Documento, row["id"], {
                        "treinamento_id": row["treinamento_id"], "nome": row["nome"],
                        "caminho": filename, "tipo": row["tipo"],
                        "processado": bool(row["processado"]) and exists, "criado_em": created,
                    })
        except sqlite3.Error:
            raise CommandError("Não foi possível ler o esquema do banco legado.") from None
        except (ValidationError, ServiceError, ValueError):
            raise CommandError("Dados legados inválidos. Nenhuma alteração foi confirmada.") from None
        self.stdout.write(self.style.SUCCESS(
            f"Importação concluída: {len(sectors)} setores, {len(trainings)} treinamentos, {len(documents)} documentos."
        ))
        if missing:
            self.stdout.write(self.style.WARNING(f"{missing} arquivo(s) ausente(s); documentos mantidos como pendentes."))
        self.stdout.write("Origem preservada. Nenhuma chamada aos provedores de IA foi realizada.")

    def insert(self, model, pk, values):
        existing = model.objects.filter(pk=pk).first()
        if existing:
            if any(getattr(existing, key) != value for key, value in values.items()):
                raise CommandError("Há IDs conflitantes no destino. Importação cancelada sem sobrescrever registros.")
            return existing
        obj = model(pk=pk, **values)
        obj.full_clean()
        obj.save(force_insert=True)
        return obj

    def lesson(self, row):
        video = normalize_video_url(row["video_url"] if "video_url" in row.keys() else "")
        text = row["conteudo"] if "conteudo" in row.keys() else ""
        existing = Aula.objects.filter(treinamento_id=row["id"], ordem=1).first()
        values = {"titulo": row["titulo"], "video_url": video, "conteudo": text, "ativo": True}
        if existing:
            if any(getattr(existing, key) != value for key, value in values.items()):
                raise CommandError("A aula inicial já foi alterada no destino. Importação cancelada.")
            return
        lesson = Aula(treinamento_id=row["id"], ordem=1, **values)
        lesson.full_clean()
        lesson.save()
