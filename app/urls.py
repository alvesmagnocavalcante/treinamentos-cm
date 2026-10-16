from django.urls import path
from app import views

urlpatterns = [
    path("", views.index, name="index"),
    path("treinamentos/<int:training_id>", views.training, name="training"),
    path("treinamentos/<int:training_id>/perguntar", views.ask, name="ask"),
    path("documentos/<int:document_id>/arquivo", views.download, name="document_download"),
    path("admin/treinamentos/<int:training_id>/documentos", views.documents, name="training_documents"),
    path("admin/documentos/<int:document_id>/reindexar", views.reindex, name="document_reindex"),
    path("admin/documentos/<int:document_id>/excluir", views.delete_document, name="document_delete"),
]
