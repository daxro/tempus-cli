import pytest

from tempus_cli.session import find_freja_link, stockholm_login_url


def test_find_freja_link_finds_href_variants():
    html = '<a href="/login/freja/start?x=1">Freja</a>'
    assert find_freja_link(html) == "/login/freja/start?x=1"


def test_find_freja_link_reports_upstream_login_failure():
    html = "<h2>Inloggningen misslyckades</h2><p>BankID/federerad inloggning</p>"
    with pytest.raises(RuntimeError, match="upstream login failure"):
        find_freja_link(html)


def test_stockholm_login_url_keeps_parameters_out_of_logs_only_by_caller():
    url = stockholm_login_url(399)
    assert url.startswith("https://login.tempusinfo.se/login/saml/login?")
    assert "schemaId=399" in url
    assert "project=HOME" in url
    assert "force_client=STOCKHOLM_PROD" in url
    assert "provider%3D399" in url
    assert "createLoginCookie=true" in url


class DummyResponse:
    def __init__(self, url="https://home.tempusinfo.se/tempusHome/", text="<html>Tempus Home</html>", status_code=200, headers=None):
        self.url = url
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class DummySession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append((url, kwargs))
        return self.responses.pop(0)


def test_verify_login_return_accepts_tempus_home():
    from tempus_cli.session import verify_login_return

    session = DummySession([DummyResponse()])

    assert verify_login_return(session) is True
    assert session.requested[0][0] == "https://home.tempusinfo.se/tempusHome/"


def test_verify_login_return_rejects_login_failure_page():
    from tempus_cli.session import verify_login_return

    session = DummySession([DummyResponse(text="<h2>Inloggningen misslyckades</h2>")])

    with pytest.raises(RuntimeError, match="login return verification failed"):
        verify_login_return(session)


def test_verify_authenticated_fails_closed_without_authenticated_read_probe():
    from tempus_cli.session import verify_authenticated

    with pytest.raises(RuntimeError, match="authenticated read verification is not available"):
        verify_authenticated(DummySession([]))


def test_status_text_reports_no_persisted_session(tmp_path):
    from tempus_cli.session import status_text

    output = status_text(session_path=tmp_path / "missing.json")

    assert "session: none" in output
    assert "authenticated: no" in output


def test_status_text_verifies_persisted_session(monkeypatch, tmp_path):
    from tempus_cli import session as session_module

    session_file = tmp_path / "session.json"
    session_file.write_text("[]")
    dummy_session = object()
    monkeypatch.setattr(session_module, "new_session", lambda: dummy_session)
    monkeypatch.setattr(session_module, "load_session_opt_in", lambda session, path: session is dummy_session and path == session_file)
    monkeypatch.setattr(session_module, "verify_authenticated", lambda session: True)

    output = session_module.status_text(session_path=session_file)

    assert "session: persisted" in output
    assert "authenticated: yes" in output


def test_status_text_fails_closed_when_authenticated_read_probe_is_missing(monkeypatch, tmp_path):
    from tempus_cli import session as session_module

    session_file = tmp_path / "session.json"
    session_file.write_text("[]")
    monkeypatch.setattr(session_module, "load_session_opt_in", lambda session, path: True)
    monkeypatch.setattr(
        session_module,
        "verify_authenticated",
        lambda session: (_ for _ in ()).throw(RuntimeError("authenticated read verification is not available yet: https://example.test/?SAMLTRANSACTIONID=secret")),
    )

    output = session_module.status_text(session_path=session_file)

    assert "session: persisted" in output
    assert "authenticated: no" in output
    assert "SAMLTRANSACTIONID=%5BREDACTED%5D" in output
    assert "secret" not in output
