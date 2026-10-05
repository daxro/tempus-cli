import pytest
import requests

from tempus_cli.errors import SafetyError
from tempus_cli.net import TempusNetworkError
from tempus_cli.transport import LoginTransport


@pytest.mark.parametrize('url', [
    'http://login.tempusinfo.se/login/start',
    'https://login.tempusinfo.se:444/login/start',
    'https://example.test/login/start',
    'https://login.tempusinfo.se/other',
    'https://login001.stockholm.se/other',
    'https://login001.stockholm.se/NECSadc/%2e%2e/other',
    'https://home.tempusinfo.se/tempusHome/tempusHome/service',
])
def test_login_transport_rejects_unapproved_urls_before_network(url):
    transport = LoginTransport(object())
    with pytest.raises(SafetyError):
        transport.get(url)
    with pytest.raises(SafetyError):
        transport.post_login_form(url, data={'SAMLRequest': 'generated-value'})


@pytest.mark.parametrize('url', [
    'https://login.tempusinfo.se/login/saml/login',
    'https://login001.stockholm.se/NECSadc/start',
    'https://login003.stockholm.se/affwebservices/start',
])
def test_login_transport_allows_only_login_form_fields(url):
    calls = []
    class Session:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return 'generated-response'
    transport = LoginTransport(Session())
    assert transport.post_login_form(url, data={'SAMLResponse': 'generated-value'}) == 'generated-response'
    with pytest.raises(SafetyError):
        transport.post_login_form(url, data={'pickupId': 201})
    assert len(calls) == 1


def test_login_transport_wraps_network_errors():
    class Session:
        def get(self, *args, **kwargs):
            raise requests.exceptions.Timeout('generated-timeout')
    with pytest.raises(TempusNetworkError):
        LoginTransport(Session()).get('https://login.tempusinfo.se/login/start')


def test_login_transport_has_no_rpc_entrypoints():
    transport = LoginTransport(object())
    assert not hasattr(transport, 'post_rpc')
    assert not hasattr(transport, 'post_pickup_write_rpc')
