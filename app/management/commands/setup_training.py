from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.models import Setor, Treinamento
from app.services.drive import normalize_folder_url
from app.services.errors import ServiceError


class Command(BaseCommand):
    help = "Cadastra setor e treinamento iniciais sem copiar dados de outro banco. Pode ser repetido."

    def add_arguments(self, parser):
        parser.add_argument("--setor", default="RH")
        parser.add_argument("--titulo", default="Integração")
        parser.add_argument("--drive-folder", required=True, help="Link da pasta de documentos")

    def handle(self, *args, **options):
        sector_name, title = options["setor"].strip(), options["titulo"].strip()
        if not sector_name or len(sector_name) > 100 or not title or len(title) > 200:
            raise CommandError("Informe setor (até 100 caracteres) e título (até 200 caracteres).")
        try:
            folder = normalize_folder_url(options["drive_folder"])
            if not folder:
                raise ServiceError("Informe a pasta do Drive.", 422)
        except ServiceError as exc:
            raise CommandError(str(exc)) from None
        with transaction.atomic():
            sector, _ = Setor.objects.get_or_create(nome=sector_name)
            trainings = Treinamento.objects.filter(setor=sector, titulo=title)
            if trainings.count() > 1:
                raise CommandError("Há treinamentos com mesmo título neste setor. Configure a pasta pelo Admin.")
            training = trainings.first()
            if training is None:
                training = Treinamento.objects.create(setor=sector, titulo=title, drive_folder_url=folder)
            elif not training.drive_folder_url:
                training.drive_folder_url = folder
                training.save(update_fields=["drive_folder_url"])
            elif training.drive_folder_url != folder:
                raise CommandError("O treinamento já tem outra pasta. Altere-a explicitamente pelo Admin.")
        self.stdout.write(self.style.SUCCESS(f"Treinamento pronto (ID {training.pk}). Crie o administrador com createsuperuser e sincronize pelo Admin."))
