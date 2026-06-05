import requests

from .errors import TempusError
from .redact import redact_text


class TempusNetworkError(TempusError):
    """Network request to Tempus or login provider failed."""


def wrap_network_error(exc, action="Tempus request"):
    if isinstance(exc, requests.exceptions.Timeout):
        return TempusNetworkError(f"{action} timed out")
    if isinstance(exc, requests.exceptions.RequestException):
        message = redact_text(str(exc))
        return TempusNetworkError(f"{action} failed: {message}")
    return exc
