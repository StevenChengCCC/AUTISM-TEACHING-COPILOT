class AppError(Exception):
    status_code = 400

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConflictError(AppError):
    status_code = 409


class NotFoundError(AppError):
    status_code = 404
