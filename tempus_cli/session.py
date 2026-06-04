import getpass
import re
from html import unescape
from urllib.parse import urljoin

from .api import TempusApi, new_session
from .freja import freja_login

HTTP_TIMEOUT = 30
REDIRECT_CODES = (301, 302, 303, 307, 308)


def follow_redirects(session, resp, max_hops=20):
    for _ in range(max_hops):
        if resp.status_code not in REDIRECT_CODES:
            break
        location = resp.headers.get("Location")
        if not location:
            break
        resp = session.get(urljoin(resp.url, location), allow_redirects=False, timeout=HTTP_TIMEOUT)
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


def handle_saml_chain(session, html, page_url, max_hops=10):
    for _ in range(max_hops):
        action = parse_form_action(html)
        fields = parse_hidden_fields(html)
        if not action or not fields:
            break
        resp = session.post(urljoin(page_url, action), data=fields, allow_redirects=False, timeout=HTTP_TIMEOUT)
        resp = follow_redirects(session, resp)
        html, page_url = resp.text, resp.url
    return html, page_url


def find_freja_link(html):
    m = re.search(r'href=["\'](https://login00[13]\.stockholm\.se/[^"\']*freja[^"\']*)', html, re.I)
    if not m:
        raise RuntimeError("Could not find Freja link on Stockholm login page")
    return unescape(m.group(1))


def login(personnummer=None, session=None, quiet=False):
    session = session or new_session()
    api = TempusApi(session=session)
    schemas = api.schemas(12)
    stockholm = next((s for s in schemas if s["name"] == "Stockholms stad"), None)
    if not stockholm or not stockholm.get("id"):
        raise RuntimeError("Could not find Stockholms stad schema")
    providers = api.identity_providers(stockholm["id"])
    if not any(p.get("name") == "Stockholm-inlogg" for p in providers):
        raise RuntimeError("Could not find Stockholm-inlogg provider")
    login_url = f"https://login.tempusinfo.se/login/saml/login?schemaId={stockholm['id']}&project=tempus-stockholm&origin=tempusHome"
    resp = session.get(login_url, allow_redirects=False, timeout=HTTP_TIMEOUT)
    resp = follow_redirects(session, resp)
    if personnummer is None:
        personnummer = getpass.getpass("Personnummer för Freja (visas inte): ")
    if not quiet:
        print("Godkänn i Freja eID+...", flush=True)
    freja_url = find_freja_link(resp.text)
    freja_page = follow_redirects(session, session.get(freja_url, allow_redirects=False, timeout=HTTP_TIMEOUT))
    freja_login(session, freja_page.url, personnummer)
    resp = follow_redirects(session, session.get(freja_page.url, allow_redirects=False, timeout=HTTP_TIMEOUT))
    handle_saml_chain(session, resp.text, resp.url)
    return session


def status_text():
    return "session: in-memory only\nauthenticated: unknown"
