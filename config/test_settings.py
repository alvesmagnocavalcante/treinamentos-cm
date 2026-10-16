"""Testes nunca usam a conexão do .env por acidente."""

import os

os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://training_test:local-test-only@127.0.0.1:55439/training_test?sslmode=disable",
)
os.environ["DJANGO_DEBUG"] = "true"
os.environ["DATABASE_SSL_ROOT_CERT"] = ""

from .settings import *  # noqa: E402,F403
