import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from app.config import ROOT, Settings

SERVICE_SETTINGS = Settings.from_env()
BASE_DIR = ROOT
DEBUG = os.getenv("DJANGO_DEBUG", "true").lower() in {"1", "true", "yes"}
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Configure DJANGO_SECRET_KEY fora do ambiente local.")
    key_path = ROOT / ".cache/django-secret"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with key_path.open("x", encoding="utf-8") as key_file:
            key_file.write(secrets.token_urlsafe(64))
    except FileExistsError:
        pass
    SECRET_KEY = key_path.read_text(encoding="utf-8").strip()
    if not SECRET_KEY:
        raise ImproperlyConfigured("A chave local do Django está vazia.")

ALLOWED_HOSTS = [host.strip() for host in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if host.strip()]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "app.apps.TrainingConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "app.middleware.RequestGuards",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "app.middleware.ServiceErrors",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True,
     "OPTIONS": {"context_processors": [
         "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
         "django.contrib.messages.context_processors.messages",
     ]}},
    {"NAME": "jinja2", "BACKEND": "django.template.backends.jinja2.Jinja2",
     "DIRS": [ROOT / "app/templates"], "APP_DIRS": False,
     "OPTIONS": {"environment": "app.jinja2.environment"}},
]
SERVICE_SETTINGS.database_path.parent.mkdir(parents=True, exist_ok=True)
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": SERVICE_SETTINGS.database_path, "OPTIONS": {"timeout": 15}}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [ROOT / "app/static"]
STATIC_ROOT = ROOT / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/conta/entrar/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = LOGIN_URL
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
DATA_UPLOAD_MAX_MEMORY_SIZE = SERVICE_SETTINGS.max_upload_bytes + 256 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = min(SERVICE_SETTINGS.max_upload_bytes, 2_500_000)
X_FRAME_OPTIONS = "DENY"
