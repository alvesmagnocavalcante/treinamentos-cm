from django.urls import path

from app.views import chat, documents, training, video

urlpatterns = [
    path("", training.index, name="index"),
    path("treinamentos/<int:training_id>", training.training, name="training"),
    path("treinamentos/<int:training_id>/perguntar", chat.ask, name="ask"),
    path("aulas/<int:lesson_id>/video", video.lesson_video, name="lesson_video"),
    path("documentos/<int:document_id>/arquivo", documents.download, name="document_download"),
    path("admin/treinamentos/<int:training_id>/documentos", documents.documents, name="training_documents"),
    path("admin/documentos/<int:document_id>/reindexar", documents.reindex, name="document_reindex"),
    path("admin/documentos/<int:document_id>/excluir", documents.delete_document, name="document_delete"),
]
