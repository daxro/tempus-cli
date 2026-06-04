import getpass
import re
from html import unescape
from urllib.parse import urlencode, urljoin

from .api import TempusApi, new_session
from .freja import freja_login
from .redact import redact_url
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


def stockholm_login_url(schema_id, project="tempus-stockholm", origin="tempusHome"):
    params = {
        "schemaId": schema_id,
        "project": project,
        "force_client": "false",
        "origin": origin,
        "createLoginCookie": "false",
    }
    return "https://login.tempusinfo.se/login/saml/login?" + urlencode(params)


def login(personnummer=None, session=None, quiet=False):
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

    login_url = stockholm_login_url(stockholm["id"], project=stockholm.get("project") or "tempus-stockholm")
    resp = transport.get(login_url, allow_redirects=False, timeout=HTTP_TIMEOUT)
    resp = follow_redirects(transport, resp)
    freja_url = urljoin(resp.url, find_freja_link(resp.text))
    if personnummer is None:
        personnummer = getpass.getpass("Personnummer för Freja (visas inte): ")
    if not quiet:
        print("Godkänn i Freja eID+...", flush=True)
    freja_page = follow_redirects(transport, transport.get(freja_url, allow_redirects=False, timeout=HTTP_TIMEOUT))
    freja_login(session, freja_page.url, personnummer)
    resp = follow_redirects(transport, transport.get(freja_page.url, allow_redirects=False, timeout=HTTP_TIMEOUT))
    handle_saml_chain(transport, resp.text, resp.url)
    return session


def status_text():
    return "session: in-memory only\nauthenticated: unknown"
