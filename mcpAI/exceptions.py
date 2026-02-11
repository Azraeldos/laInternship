"""Custom exception classes for the application."""


class AppException(Exception):
    """Base exception for application-specific errors."""

    pass


class AuthenticationError(AppException):
    """Raised when authentication fails."""

    pass


class ValidationError(AppException):
    """Raised when input validation fails."""

    pass


class PlanGenerationError(AppException):
    """Raised when plan generation fails."""

    pass


class RunnerError(AppException):
    """Raised when the robot runner fails."""

    pass
