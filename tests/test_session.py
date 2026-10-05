import pytest

from tempus_cli.session import find_freja_link

TEST_PERSONNUMMER = "0" * 12


def test_find_freja_link_finds_href_variants():
    html = '<a href="/login/freja/start?x=1">Freja</a>'
    assert find_freja_link(html) == "/login/freja/start?x=1"


def test_find_freja_link_reports_upstream_login_failure():
    html = "<h2>Inloggningen misslyckades</h2><p>BankID/federerad inloggning</p>"
    with pytest.raises(RuntimeError, match="upstream login failure"):
        find_freja_link(html)


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
        session_module.login_home_api()

    assert network_calls == []




def test_home_login_uses_verified_option_and_freja_then_exchanges_token(monkeypatch, capsys):
    from tempus_cli import session as session_module
    calls = []
    class Client:
        token = 'x' * 64
        def schemas(self, area):
            assert area == 12
            return [{'name': 'Stockholms stad', 'id': 399}]
        def login_options(self, destination):
            assert destination == 399
            return [{'clientEnum': 'STOCKHOLM_PROD', 'url':
                     'https://login.tempusinfo.se/login/saml/login?force_client=STOCKHOLM_PROD'
                     '&schemaId=399&project=HOME_API&createLoginCookie=false&origin=null'}]
        def exchange_saml_token(self, token):
            calls.append(('exchange', token))
        def initialize(self):
            calls.append(('initialize',))
    class Response:
        status_code = 200
        headers = {}
        url = 'https://login001.stockholm.se/NECSadc/start'
        text = '<a href="/NECSadcfreja/start">Freja</a>'
    class Session:
        def get(self, url, **kwargs):
            assert kwargs['allow_redirects'] is False
            return Response()
    def freja(raw_session, url, personnummer, timeout, on_started):
        assert personnummer == TEST_PERSONNUMMER
        assert timeout == 90
        calls.append(('freja',))
        on_started()
    saml_pages = iter([
        (Response.text, Response.url),
        ('<script>ReactNativeWebView.postMessage("' + 'a' * 64 + '")</script>', Response.url),
    ])
    monkeypatch.setattr(session_module, 'HomeApiClient', Client)
    monkeypatch.setattr(session_module, 'freja_login', freja)
    monkeypatch.setattr(session_module, 'handle_saml_chain', lambda *args: next(saml_pages))
    assert session_module.login_home_api(personnummer=TEST_PERSONNUMMER, session=Session(),
                                         freja_timeout=90, allow_prompt=False) == 'x' * 64
    assert calls == [('freja',), ('exchange', 'a' * 64), ('initialize',)]
    output = capsys.readouterr()
    assert output.out == ''
    assert 'Approve the login in Freja' in output.err
