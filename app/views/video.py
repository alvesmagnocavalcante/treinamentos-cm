from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_safe

from app.models import Aula
from app.services.video import open_video


@login_required
@require_safe
def lesson_video(request, lesson_id):
    lesson = get_object_or_404(Aula, pk=lesson_id, ativo=True, treinamento__ativo=True)
    stream = open_video(lesson.video_url, request.headers.get("Range", "bytes=0-"), method=request.method)
    upstream = stream.response
    if request.method == "HEAD":
        response = HttpResponse(status=upstream.status_code)
    else:
        response = StreamingHttpResponse(stream, status=upstream.status_code)
    for header in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
        if header in upstream.headers:
            response[header] = upstream.headers[header]
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    if request.method == "HEAD":
        stream.close()
    return response
