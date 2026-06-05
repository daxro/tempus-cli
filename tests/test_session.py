import pytest

from tempus_cli.session import find_freja_link, stockholm_login_url

TEST_PERSONNUMMER = "0" * 12


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


def _mock_login_flow(monkeypatch, session_module, calls):
    class FakeApi:
        def __init__(self, session=None):
            self.session = session
            pass

        def schemas(self, area_id):
            return [{"name": "Stockholms stad", "id": 399}]

        def identity_providers(self, schema_id):
            return [{"name": "Stockholm-inlogg", "option": "STOCKHOLM_PROD"}]

        def authenticate_user_with_cookies(self):
            calls.setdefault("authenticated_sessions", []).append(self.session)
            return True

    class FakeTransport:
        def __init__(self, session):
            pass

        def get(self, *args, **kwargs):
            return DummyResponse()

    def fake_freja_login(raw_session, url, personnummer, on_started=None, timeout=None):
        calls.update(raw_session=raw_session, personnummer=personnummer, timeout=timeout)
        if on_started:
            on_started()

    monkeypatch.setattr(session_module, "TempusApi", FakeApi)
    monkeypatch.setattr(session_module, "ReadOnlyTempusTransport", FakeTransport)
    monkeypatch.setattr(session_module, "follow_redirects", lambda transport, resp: resp)
    monkeypatch.setattr(
        session_module,
        "handle_saml_chain",
        lambda transport, html, url: ('<a href="/freja/start">Freja</a>', "https://login001.stockholm.se/page"),
    )
    monkeypatch.setattr(session_module, "freja_login", fake_freja_login)


def test_login_passes_timeout_and_progress_to_stderr(monkeypatch, capsys):
    from tempus_cli import session as session_module

    calls = {}
    _mock_login_flow(monkeypatch, session_module, calls)
    raw_session = object()

    session_module.login(personnummer=TEST_PERSONNUMMER, session=raw_session, freja_timeout=180)

    captured = capsys.readouterr()
    assert calls == {
        "authenticated_sessions": [raw_session],
        "raw_session": raw_session,
        "personnummer": TEST_PERSONNUMMER,
        "timeout": 180,
    }
    assert captured.out == ""
    assert "Freja" in captured.err


def test_login_uses_tempus_personnummer_env(monkeypatch, capsys):
    from tempus_cli import session as session_module

    calls = {}
    monkeypatch.setenv("TEMPUS_PERSONNUMMER", TEST_PERSONNUMMER)
    _mock_login_flow(monkeypatch, session_module, calls)

    session_module.login(session=object(), quiet=True)

    assert calls["personnummer"] == TEST_PERSONNUMMER
    assert "Freja" in capsys.readouterr().err


def test_resolve_personnummer_uses_saved_config(monkeypatch, tmp_path):
    from tempus_cli import session as session_module

    config_file = tmp_path / "config.env"
    config_file.write_text(f"TEMPUS_PERSONNUMMER={TEST_PERSONNUMMER}\n")
    monkeypatch.delenv("TEMPUS_PERSONNUMMER", raising=False)
    monkeypatch.setattr(session_module, "default_config_path", lambda: config_file)

    assert session_module.resolve_personnummer() == TEST_PERSONNUMMER


def test_login_non_interactive_missing_input_fails_before_network(monkeypatch, tmp_path):
    from tempus_cli import session as session_module

    network_calls = []
    monkeypatch.delenv("TEMPUS_PERSONNUMMER", raising=False)
    monkeypatch.setattr(session_module, "default_config_path", lambda: tmp_path / "missing.env")
    monkeypatch.setattr(session_module.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(session_module, "new_session", lambda: network_calls.append(True))

    with pytest.raises(ValueError, match="non-interactive"):
        session_module.login()

    assert network_calls == []


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


def test_verify_authenticated_uses_cookie_auth_and_heartbeat(monkeypatch):
    from tempus_cli import session as session_module

    calls = []

    class FakeApi:
        def __init__(self, session):
            calls.append(session)

        def authenticate_user_with_cookies(self):
            calls.append("auth")
            return True

        def heartbeat(self):
            calls.append("heartbeat")
            return True

    raw_session = object()
    monkeypatch.setattr(session_module, "TempusApi", FakeApi)

    assert session_module.verify_authenticated(raw_session) is True
    assert calls == [raw_session, "auth", "heartbeat"]


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


def test_status_text_redacts_failed_verification(monkeypatch, tmp_path):
    from tempus_cli import session as session_module

    session_file = tmp_path / "session.json"
    session_file.write_text("[]")
    monkeypatch.setattr(session_module, "load_session_opt_in", lambda session, path: True)
    monkeypatch.setattr(
        session_module,
        "verify_authenticated",
        lambda session: (_ for _ in ()).throw(RuntimeError("verification failed: https://example.test/?SAMLTRANSACTIONID=secret")),
    )

    output = session_module.status_text(session_path=session_file)

    assert "session: persisted" in output
    assert "authenticated: no" in output
    assert "SAMLTRANSACTIONID=%5BREDACTED%5D" in output
    assert "secret" not in output
