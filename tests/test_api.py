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


def test_pickup_assignment_authenticates_then_reads(monkeypatch):
    calls = []

    class FakeTransport:
        def __init__(self, session):
            pass

        def post_rpc(self, url, payload, headers=None, **kwargs):
            calls.append(rpc_method_from_payload(payload))
            if calls[-1] == "authenticateUserWithCookies":
                return DummyResponse("//OK[]")
            return DummyResponse(
                '//OK[{"assignment":{"date":"2026-06-11","childId":101,"pickupId":456,'
                '"assignmentId":901,"version":"assignment-version-before","writeToken":"assignment-write-token-before"}}]'
            )

    monkeypatch.setattr(api_module, "ReadOnlyTempusTransport", FakeTransport)

    api = api_module.TempusApi(session=object(), permutation="P")

    assert api.pickup_assignment("2026-06-11", 101)["child_id"] == "101"
    assert calls == ["authenticateUserWithCookies", "getPickupDateAssignment"]


def test_assign_pickup_uses_pickup_write_transport(monkeypatch):
    calls = []

    class FakeTransport:
        def __init__(self, session):
            pass

        def post_pickup_write_rpc(self, url, payload, headers=None, **kwargs):
            calls.append(rpc_method_from_payload(payload))
            return DummyResponse('//OK[{"success":true,"assignmentId":901,"version":"assignment-version-after"}]')

    monkeypatch.setattr(api_module, "ReadOnlyTempusTransport", FakeTransport)

    api = api_module.TempusApi(session=object(), permutation="P")

    result = api.assign_pickup(
        {
            "date": "2026-06-11",
            "child_id": "101",
            "pickup_id": "123",
            "assignment_id": "901",
            "version": "assignment-version-before",
            "write_token": "assignment-write-token-before",
        }
    )

    assert result["success"] is True
    assert calls == ["assignPickupForDate"]


def test_contact_write_methods_remain_disabled():
    api = api_module.TempusApi(session=object(), permutation="P")
    for call in (
        lambda: api.create_pickup("Generated Pickup", "0700000000", ["Generated Child"]),
        lambda: api.update_pickup("123", "Generated Pickup", "0700000000", ["Generated Child"]),
        lambda: api.remove_pickup("123"),
    ):
        try:
            call()
        except RuntimeError as exc:
            assert "pickup contact writes require sanitized Tempus write fixtures" in str(exc)
        else:
            raise AssertionError("contact write should remain disabled")
