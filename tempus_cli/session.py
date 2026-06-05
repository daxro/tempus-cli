import getpass
import os
import re
from html import unescape
from urllib.parse import urlencode, urljoin

from .api import TempusApi, new_session
from .freja import freja_login
from .paths import default_config_path, default_session_path
from .redact import redact_text
from .session_store import load_session_opt_in
from .transport import ReadOnlyTempusTransport

HTTP_TIMEOUT = 30
REDIRECT_CODES = (301, 302, 303, 307, 308)


def _client(session_or_transport):
    if isinstance(session_or_transport, ReadOnlyTempusTransport):
        return session_or_transport
    return ReadOnlyTempusTransport(session_or_transport)


def follow_redirects(session_or_transport, resp, max_hops=20):
    client = _client(session_or_transport)
    for _ in range(max_hops):
        if resp.status_code not in REDIRECT_CODES:
            break
        location = resp.headers.get("Location")
        if not location:
            break
        resp = client.get(urljoin(resp.url, location), allow_redirects=False, timeout=HTTP_TIMEOUT)
    return resp


def parse_hidden_fields(html):
    fields = {}
    for match in re.finditer(r'<input\b[^>]*\btype=["\']hidden["\'][^>]*>', html, re.I):
        tag = match.group()
        name = re.search(r'\bname=["\']([^"\']+)', tag)
        value = re.search(r'\bvalue=["\']([^"\']*)', tag)
        if name:
            fields[name.group(1)] = unescape(value.group(1)) if value else ""
    return fields


def parse_form_action(html):
    m = re.search(r'<form[^>]*\baction=["\']([^"\']*)', html, re.I)
    return unescape(m.group(1)) if m else None


def handle_saml_chain(session_or_transport, html, page_url, max_hops=10):
    client = _client(session_or_transport)
    for _ in range(max_hops):
        action = parse_form_action(html)
        fields = parse_hidden_fields(html)
        if not action or not fields:
            break
        resp = client.post_login_form(urljoin(page_url, action), data=fields, allow_redirects=False, timeout=HTTP_TIMEOUT)
        resp = follow_redirects(client, resp)
        html, page_url = resp.text, resp.url
    return html, page_url


def find_freja_link(html):
    patterns = [
        r'href=["\']([^"\']*(?:freja|bankid|eleg|e-legitimation)[^"\']*)',
        r'data-(?:href|url)=["\']([^"\']*(?:freja|bankid|eleg|e-legitimation)[^"\']*)',
        r'location\.(?:href|assign|replace)\(["\']([^"\']*(?:freja|bankid|eleg|e-legitimation)[^"\']*)',
    ]
    for pattern in patterns:
        m = re.search(pattern, html, re.I)
        if m:
            return unescape(m.group(1))
    if "Inloggningen misslyckades" in html or "BankID/federerad inloggning" in html:
        raise RuntimeError("Tempus login endpoint returned an upstream login failure before Stockholm/Freja")
    raise RuntimeError("Could not find Freja/BankID link on Stockholm login page")


def stockholm_login_url(schema_id, provider_option="STOCKHOLM_PROD", origin=None):
    params = {
        "schemaId": schema_id,
        "project": "HOME",
        "force_client": provider_option,
        "origin": origin or f"https://home.tempusinfo.se/tempusHome/#loc=12&provider={schema_id}",
        "createLoginCookie": "true",
    }
    return "https://login.tempusinfo.se/login/saml/login?" + urlencode(params)


def _read_config_personnummer(path=None):
    path = path or default_config_path()
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("TEMPUS_PERSONNUMMER="):
            return line.split("=", 1)[1].strip()
    return None


def _resolve_personnummer(personnummer=None):
    return personnummer or os.environ.get("TEMPUS_PERSONNUMMER") or _read_config_personnummer()


def login(personnummer=None, session=None, quiet=False, freja_timeout=180.0):
    session = session or new_session()
    transport = ReadOnlyTempusTransport(session)
    api = TempusApi(session=session)
    schemas = api.schemas(12)
    stockholm = next((s for s in schemas if s["name"] == "Stockholms stad"), None)
    if not stockholm or not stockholm.get("id"):
        raise RuntimeError("Could not find Stockholms stad schema")
    providers = api.identity_providers(stockholm["id"])
    provider = next((p for p in providers if p.get("name") == "Stockholm-inlogg"), None)
    if not provider:
        raise RuntimeError("Could not find Stockholm-inlogg provider")

    login_url = stockholm_login_url(stockholm["id"], provider_option=provider.get("option") or "STOCKHOLM_PROD")
    resp = transport.get(login_url, allow_redirects=False, timeout=HTTP_TIMEOUT)
    resp = follow_redirects(transport, resp)
    html, page_url = handle_saml_chain(transport, resp.text, resp.url)
    freja_url = urljoin(page_url, find_freja_link(html))
    personnummer = _resolve_personnummer(personnummer)
    if personnummer is None:
        personnummer = getpass.getpass("Personnummer för Freja (visas inte): ")
    freja_page = follow_redirects(transport, transport.get(freja_url, allow_redirects=False, timeout=HTTP_TIMEOUT))
    freja_login(
        transport,
        freja_page.url,
        personnummer,
        timeout=freja_timeout,
        on_started=(lambda: print("Godkänn i Freja eID+...", flush=True)) if not quiet else None,
    )
    resp = follow_redirects(transport, transport.get(freja_page.url, allow_redirects=False, timeout=HTTP_TIMEOUT))
    handle_saml_chain(transport, resp.text, resp.url)
    verify_login_return(session)
    return session


def verify_login_return(session):
    """Verify that the login flow lands back on Tempus Home.

    This is not a proof that authenticated child/pickup data can be read; those
    RPC methods are still unknown. It only prevents known failed login returns
    from being reported as a clean login flow.
    """
    transport = ReadOnlyTempusTransport(session)
    resp = follow_redirects(
        transport,
        transport.get("https://home.tempusinfo.se/tempusHome/", allow_redirects=False, timeout=HTTP_TIMEOUT),
    )
    resp.raise_for_status()
    if not resp.url.startswith("https://home.tempusinfo.se/tempusHome/"):
        raise RuntimeError(f"Tempus login return verification failed: unexpected final URL {redact_text(resp.url)}")
    if "Inloggningen misslyckades" in resp.text or "BankID/federerad inloggning" in resp.text:
        raise RuntimeError("Tempus login return verification failed: login failure page returned")
    return True


def verify_authenticated(session):
    """Fail closed until an authenticated read-only Tempus RPC is allowlisted."""
    raise RuntimeError("authenticated read verification is not available yet")


def status_text(session_path=None):
    session_path = session_path or default_session_path()
    if not session_path.exists():
        return "session: none\nauthenticated: no"

    session = new_session()
    if not load_session_opt_in(session, session_path):
        return "session: unreadable\nauthenticated: no"

    try:
        verify_authenticated(session)
    except Exception as exc:
        reason = redact_text(str(exc))
        return f"session: persisted\nauthenticated: no\nreason: {reason}"
    return "session: persisted\nauthenticated: yes"
