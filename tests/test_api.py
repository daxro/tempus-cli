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
                '//OK[2026,24,4,11,0,0,1,0,1,0,0,101,0,0,'
                '["java.util.ArrayList/4159755760","se.tempus.common.shared.wrapper.ChildScheduleHomeWrapper/2354870038"],0,7]'
            )

    monkeypatch.setattr(api_module, "ReadOnlyTempusTransport", FakeTransport)

    api = api_module.TempusApi(session=object(), permutation="P")

    assert api.pickup_assignment("2026-06-11", 101)["child_id"] == "101"
    assert calls == ["authenticateUserWithCookies", "getWeekSchedules"]


def test_children_and_notifications_authenticates_then_reads(monkeypatch):
    calls = []

    class FakeTransport:
        def __init__(self, session):
            pass

        def post_rpc(self, url, payload, headers=None, **kwargs):
            calls.append(rpc_method_from_payload(payload))
            if calls[-1] == "authenticateUserWithCookies":
                return DummyResponse("//OK[]")
            return DummyResponse(
                '//OK[0,0,101,3,0,0,4,2,1,["java.util.ArrayList/4159755760",'
                '"se.tempus.common.shared.wrapper.Child/3395224863","Generated Child",'
                '"java.util.TreeSet/4043497002"],0,7]'
            )

    monkeypatch.setattr(api_module, "ReadOnlyTempusTransport", FakeTransport)

    api = api_module.TempusApi(session=object(), permutation="P")

    assert api.children_and_notifications() == [{"id": "101", "name": "Generated Child"}]
    assert calls == ["authenticateUserWithCookies", "getChildrenAndNotifications"]


def test_assign_pickup_uses_update_schedule_write_transport(monkeypatch):
    calls = []

    class FakeTransport:
        def __init__(self, session):
            pass

        def post_pickup_write_rpc(self, url, payload, headers=None, **kwargs):
            calls.append(rpc_method_from_payload(payload))
            return DummyResponse("//OK[]")

    monkeypatch.setattr(api_module, "ReadOnlyTempusTransport", FakeTransport)
    api = api_module.TempusApi(session=object(), permutation="P")

    result = api.assign_pickup(
        {
            "date": "2026-06-11",
            "child_id": "101",
            "pickup_id": "123",
            "pickup_name": "Generated Pickup",
            "pickup_phone": "0700000000",
            "owner_name": "Generated Owner",
            "pickup_child_ids": ["101", "102", "103"],
            "schedule_id": "901",
            "start_ms": "28800000",
            "end_ms": "59400000",
        }
    )

    assert result == {"success": True}
    assert calls == ["updateSchedule"]


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
