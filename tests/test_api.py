from tempus_cli import api as api_module
from tempus_cli.transport import rpc_method_from_payload


class DummyResponse:
    def __init__(self, text="//OK[]"):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        return None


def test_pickups_authenticates_with_cookies_before_protected_read(monkeypatch):
    calls = []

    class FakeTransport:
        def __init__(self, session):
            pass

        def post_rpc(self, url, payload, headers=None, **kwargs):
            calls.append(rpc_method_from_payload(payload))
            return DummyResponse()

    monkeypatch.setattr(api_module, "ReadOnlyTempusTransport", FakeTransport)

    api = api_module.TempusApi(session=object(), permutation="P")

    assert api.pickups() == []
    assert calls == ["authenticateUserWithCookies", "getPickups"]
