import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

SENSITIVE_QUERY_KEYS = {
    "samltransactionid", "smportalurl", "token", "code", "state",
    "schemaid", "origin", "target", "smagentname", "guid", "oauth_token",
}

_PNR_RE = re.compile(r"(?<!\d)(?:\d{8}[-+]?\d{4}|\d{6}[-+]?\d{4})(?!\d)")
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9+/=_-])(?:[A-Fa-f0-9]{32,}|[A-Za-z0-9+/=_-]{40,})(?![A-Za-z0-9+/=_-])")
_COOKIE_RE = re.compile(r"(?im)^(Cookie):\s*.*$")
_SET_COOKIE_RE = re.compile(r"(?im)^(Set-Cookie):\s*([^=;\s]+)=([^;]*)(.*)$")


def redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    pairs = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        pairs.append((key, "[REDACTED]" if key.lower() in SENSITIVE_QUERY_KEYS else value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(pairs), parts.fragment))


def redact_text(text: str) -> str:
    text = _COOKIE_RE.sub(r"\1: [REDACTED]", text)
    text = _SET_COOKIE_RE.sub(r"\1: \2=[REDACTED]\4", text)
    text = _PNR_RE.sub("[REDACTED_PNR]", text)
    # Redact query values inside URL-like strings.
    text = re.sub(r"https?://[^\s'\"]+", lambda m: redact_url(m.group(0)), text)
    text = _TOKEN_RE.sub("[REDACTED_TOKEN]", text)
    return text
