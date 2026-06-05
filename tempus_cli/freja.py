import datetime
import json
import re
import time
from urllib.parse import urlparse, urlunparse

from .errors import FrejaError, FrejaRejectedError, FrejaTimeoutError

HTTP_TIMEOUT = 30


def freja_login(client, freja_url, personnummer, poll_interval=2.0, timeout=60.0, on_started=None):
    pn = _ensure_12_digits(personnummer)
    _init_auth(client, freja_url, pn)
    if on_started:
        on_started()
    _poll_until_done(client, freja_url, poll_interval, timeout)


def _ensure_12_digits(personnummer):
    pn = re.sub(r"\D", "", personnummer or "")
    if len(pn) == 12:
        return pn
    if len(pn) == 10:
        year = int(pn[:2])
        cutoff = datetime.date.today().year % 100
        return ("20" if year <= cutoff else "19") + pn
    raise FrejaError("Personnummer must be 10 or 12 digits")


def _init_auth(client, freja_url, personnummer):
    parsed = urlparse(freja_url)
    base_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    post = client.post_login_form if hasattr(client, "post_login_form") else client.post
    init_url = f"{base_url}?action=init&userInput={personnummer}"
    resp = post(init_url, headers=_ajax_headers(base_url), timeout=HTTP_TIMEOUT)
    if not getattr(resp, "ok", False):
        raise FrejaError(f"Failed to initiate Freja auth: HTTP {resp.status_code}")


def _poll_until_done(client, freja_url, poll_interval, timeout):
    poll_url = freja_url + ("&" if "?" in freja_url else "?") + "action=checkstatus"
    headers = _ajax_headers(freja_url)
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        time.sleep(poll_interval)
        resp = client.get(poll_url, headers=headers, timeout=HTTP_TIMEOUT)
        status = _parse_status(resp.text)
        if status == "APPROVED":
            return
        if status in ("CANCELED", "REJECTED"):
            raise FrejaRejectedError("Authentication was rejected in Freja")
        if status in ("EXPIRED", "TIMEOUT"):
            raise FrejaTimeoutError(f"Authentication expired: {status}")
        if status in ("ERROR", "RP_CANCELED"):
            raise FrejaError(f"Authentication failed: {status}")
    raise FrejaTimeoutError(f"Authentication timed out after {timeout}s")


def _parse_status(text):
    text = text.strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
    return data.get("status", text) if isinstance(data, dict) else text


def _ajax_headers(referer):
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "*/*",
        "Referer": referer,
    }
