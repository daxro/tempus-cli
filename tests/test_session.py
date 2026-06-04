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
