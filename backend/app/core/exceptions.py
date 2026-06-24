class AppError(Exception):
    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConflictError(AppError):
    status_code = 409


class NotFoundError(AppError):
    status_code = 404


class ValidationError(AppError):
    status_code = 422

    def __init__(self, message: str, payload: dict | None = None):
        self.payload = payload or {}
        super().__init__(message)
