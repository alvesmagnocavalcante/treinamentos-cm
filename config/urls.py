from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

urlpatterns = [
    path("conta/entrar/", LoginView.as_view(template_name="login.html", template_engine="jinja2", redirect_authenticated_user=True), name="login"),
    path("conta/sair/", LogoutView.as_view(), name="logout"),
    path("", include("app.urls")),
    path("admin/", admin.site.urls),
]
