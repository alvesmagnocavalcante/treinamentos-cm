"""Configuração PostgreSQL com URI validada e TLS remoto obrigatório."""

import os
from urllib.parse import urlsplit

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


def database_config(config):
    if not config.database_url:
        raise ImproperlyConfigured("Configure DATABASE_URL com a conexão PostgreSQL da aplicação.")
    try:
        url = urlsplit(config.database_url)
        if (url.scheme not in ("postgres", "postgresql") or not url.hostname or not url.username
                or not url.password or not url.path.strip("/") or any(c.isspace() for c in config.database_url)
                or "CLICK_TO" in config.database_url):
            raise ValueError
        database = dj_database_url.parse(config.database_url, conn_max_age=0, conn_health_checks=True)
        options = database.setdefault("OPTIONS", {})
        options.setdefault("connect_timeout", 10)
        options.setdefault("sslmode", "require")
        if url.hostname not in ("localhost", "127.0.0.1", "::1") and options["sslmode"] not in ("require", "verify-ca", "verify-full"):
            raise ValueError
        certificate = os.getenv("DATABASE_SSL_ROOT_CERT", "").strip()
        if certificate:
            options.update(sslrootcert=certificate, sslmode="verify-full")
        return database
    except (ValueError, TypeError):
        # URLs e exceções do parser podem conter a senha: nunca repassá-las à tela/log.
        raise ImproperlyConfigured("DATABASE_URL inválida. Informe a URI PostgreSQL completa, com usuário, senha e TLS.") from None
