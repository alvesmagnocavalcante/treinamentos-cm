class ServiceError(Exception):
    """Erro público seguro: nunca incluir resposta bruta, documentos ou credenciais."""

    def __init__(self, message: str, status_code: int = 502, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
