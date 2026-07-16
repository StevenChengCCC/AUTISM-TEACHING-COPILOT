class AppError(Exception):
    status_code = 400
    error_code = "application_error"
    retryable = False

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class ConflictError(AppError):
    status_code = 409
    error_code = "conflict"


class VersionConflictError(ConflictError):
    error_code = "version_conflict"


class NotFoundError(AppError):
    status_code = 404
    error_code = "not_found"


class ForbiddenError(AppError):
    status_code = 403
    error_code = "forbidden"


class AuthenticationError(AppError):
    status_code = 401
    error_code = "authentication_required"


class SessionExpiredError(AuthenticationError):
    error_code = "session_expired"


class AIProviderConfigurationError(AppError, RuntimeError):
    """Safe provider setup failure that may be returned to the frontend."""

    status_code = 503
    error_code = "ai_provider_not_configured"


class AIProviderUnavailableError(AppError, RuntimeError):
    """Safe transient provider failure without vendor or learner details."""

    status_code = 503
    error_code = "ai_provider_unavailable"
    retryable = True


class AIProviderFailureError(AIProviderUnavailableError):
    """External generation failed before a usable response was returned."""

    error_code = "provider_failure"


class AIInvalidOutputError(AIProviderUnavailableError):
    """External generation returned content that failed the product contract."""

    error_code = "invalid_output"


class SkillConfigurationError(AppError, RuntimeError):
    """A required, explicitly versioned skill is missing or invalid."""

    status_code = 503
    error_code = "skill_configuration_error"


class ObjectStorageUnavailableError(AppError, RuntimeError):
    status_code = 503
    error_code = "object_storage_unavailable"
    retryable = True


class ValidationError(AppError):
    status_code = 422
    error_code = "validation_error"

    def __init__(self, message: str, payload: dict | None = None):
        self.payload = payload or {}
        super().__init__(message)


class SafetyDeferralError(ValidationError):
    def __init__(self, payload: dict):
        super().__init__(payload["message"], payload)
