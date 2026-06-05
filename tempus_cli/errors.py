from stockholm_freja import (
    FrejaError,
    FrejaHttpError,
    FrejaInputError,
    FrejaRedirectError,
    FrejaRejectedError,
    FrejaTimeoutError,
)


class TempusError(Exception):
    """Base Tempus CLI error."""

class SafetyError(TempusError):
    """Raised when a request is blocked by safety policy."""
