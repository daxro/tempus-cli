class TempusError(Exception):
    """Base Tempus CLI error."""

class SafetyError(TempusError):
    """Raised when a request is blocked by safety policy."""

class FrejaError(TempusError):
    """Freja authentication failed."""

class FrejaRejectedError(FrejaError):
    """Freja authentication was rejected."""

class FrejaTimeoutError(FrejaError):
    """Freja authentication timed out."""
