import getpass
import os
import re
import sys
from html import unescape
from urllib.parse import urljoin

import requests
from stockholm_freja import freja_login
from .home_api import HomeApiClient, validate_home_api_login_url
from .paths import default_config_path
from .transport import LoginTransport
from stockholm_freja import FrejaInputError, validate_personnummer as validate_freja_personnummer

HTTP_TIMEOUT = 30
REDIRECT_CODES = (301, 302, 303, 307, 308)


_POST_MESSAGE_PATTERNS = (
    re.compile(r"(?:window\.)?ReactNativeWebView\.postMessage\(\s*'([^'\r\n]{16,8192})'\s*\)"),
    re.compile(r'(?:window\.)?ReactNativeWebView\.postMessage\(\s*"([^"\r\n]{16,8192})"\s*\)'),
)


def new_session():
    session = requests.Session()
    session.headers["User-Agent"] = "tempus-cli"
    return session


def _client(session_or_transport):
    if isinstance(session_or_transport, LoginTransport):
        return session_or_transport
    return LoginTransport(session_or_transport)


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


def parse_home_api_auth_token(html):
    matches = []
    for pattern in _POST_MESSAGE_PATTERNS:
        matches.extend(pattern.findall(html or ""))
    if len(matches) != 1:
        raise RuntimeError("Tempus Home API login did not return exactly one authentication token")
    token = unescape(matches[0])
    if any(character.isspace() for character in token):
        raise RuntimeError("Tempus Home API login returned a malformed authentication token")
    return token


def read_config_personnummer(path=None):
    path = path or default_config_path()
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("TEMPUS_PERSONNUMMER="):
            return line.split("=", 1)[1].strip()
    return None


def validate_personnummer(personnummer):
    try:
        return validate_freja_personnummer(personnummer)
    except FrejaInputError:
        raise ValueError("TEMPUS_PERSONNUMMER must contain exactly 12 digits")


def resolve_personnummer(personnummer=None, *, allow_prompt=True):
    value = personnummer or os.environ.get("TEMPUS_PERSONNUMMER") or read_config_personnummer()
    if value:
        return validate_personnummer(value)
    if not allow_prompt or not sys.stdin.isatty():
        raise ValueError("TEMPUS_PERSONNUMMER is required when input is non-interactive")
    return validate_personnummer(getpass.getpass("Personal number for Freja (hidden): ").strip())


def login_home_api(personnummer=None, session=None, quiet=False, freja_timeout=180.0, allow_prompt=True):
    personnummer = resolve_personnummer(personnummer, allow_prompt=allow_prompt)
    session = session or new_session()
    client = HomeApiClient()
    schemas = client.schemas(12)
    stockholm = next((row for row in schemas if row.get("name") == "Stockholms stad"), None)
    if not stockholm or int(stockholm.get("id") or 0) != 399:
        raise RuntimeError("Could not verify the Stockholms stad Home API destination")
    options = client.login_options(stockholm["id"])
    option = next((row for row in options if row.get("clientEnum") == "STOCKHOLM_PROD"), None)
    if not option or not option.get("url"):
        raise RuntimeError("Could not find Stockholm-inlogg Home API login option")
    login_url = validate_home_api_login_url(option["url"], destination_id=stockholm["id"])

    transport = LoginTransport(session)
    response = follow_redirects(transport, transport.get(login_url, allow_redirects=False, timeout=HTTP_TIMEOUT))
    html, page_url = handle_saml_chain(transport, response.text, response.url)
    freja_url = urljoin(page_url, find_freja_link(html))
    freja_page = follow_redirects(transport, transport.get(freja_url, allow_redirects=False, timeout=HTTP_TIMEOUT))
    freja_login(
        session,
        freja_page.url,
        personnummer,
        timeout=freja_timeout,
        on_started=(
            None
            if quiet
            else lambda: print("Approve the login in Freja eID+.", file=sys.stderr, flush=True)
        ),
    )
    response = follow_redirects(
        transport,
        transport.get(freja_page.url, allow_redirects=False, timeout=HTTP_TIMEOUT),
    )
    html, _ = handle_saml_chain(transport, response.text, response.url)
    auth_token = parse_home_api_auth_token(html)
    client.exchange_saml_token(auth_token)
    client.initialize()
    return client.token
