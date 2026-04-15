class KatalogError(Exception):
    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class ValidationError(KatalogError):
    status_code = 400
    error_code = "VALIDATION_ERROR"


class AuthError(KatalogError):
    status_code = 401
    error_code = "AUTH_ERROR"


class NotFoundError(KatalogError):
    status_code = 404
    error_code = "NOT_FOUND"


class RateLimitError(KatalogError):
    status_code = 429
    error_code = "RATE_LIMIT"


class UpstreamError(KatalogError):
    status_code = 502
    error_code = "UPSTREAM_ERROR"
