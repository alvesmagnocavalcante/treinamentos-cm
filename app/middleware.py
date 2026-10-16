import logging

from django.conf import settings
from django.db import DatabaseError
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from app.services.errors import ServiceError

logger = logging.getLogger(__name__)


class RequestGuards(MiddlewareMixin):
    def process_request(self, request):
        if request.method != "POST":
            return None
        length = request.META.get("CONTENT_LENGTH", "")
        multipart = request.content_type == "multipart/form-data"
        if multipart and not length:
            return JsonResponse({"detail": "Upload exige Content-Length."}, status=411)
        if length and (not length.isdigit() or int(length) > settings.DATA_UPLOAD_MAX_MEMORY_SIZE):
            return JsonResponse({"detail": "Requisição excede o tamanho máximo permitido."}, status=413)
        return None


class ServiceErrors(MiddlewareMixin):
    def process_exception(self, request, exception):
        if isinstance(exception, ServiceError):
            response = JsonResponse({"detail": str(exception)}, status=exception.status_code)
            if exception.retry_after is not None:
                response["Retry-After"] = str(exception.retry_after)
            return response
        if isinstance(exception, (DatabaseError, OSError)):
            logger.error("Falha de persistência/armazenamento: %s", type(exception).__name__)
            return JsonResponse({"detail": "Armazenamento indisponível. Verifique espaço e permissões."}, status=503)
        return None
