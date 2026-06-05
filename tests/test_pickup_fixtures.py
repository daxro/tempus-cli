import json

import pytest

from tempus_cli.gwt import GWT_MODULE_BASE, GWT_SERVICE_URL, HOME_SERVICE
from tempus_cli.pickup_fixtures import (
    assert_sanitized_fixture,
    write_sanitized_fixture,
)


def _payload(method):
    return f"7|0|4|{GWT_MODULE_BASE}|{'A' * 32}|{HOME_SERVICE}|{method}|1|2|3|4|0|"


def test_sanitize_pickup_assignment_har_removes_sensitive_values(tmp_path):
    raw = {
        "log": {
            "entries": [
                {
                    "request": {
                        "method": "POST",
                        "url": GWT_SERVICE_URL + "?SAMLTRANSACTIONID=secret&state=abc&safe=1",
                        "headers": [
                            {"name": "Cookie", "value": "JSESSIONID=session-secret"},
                            {"name": "Authorization", "value": "Bearer token-secret"},
                            {"name": "X-GWT-Permutation", "value": "A" * 32},
                        ],
                        "postData": {
                            "text": _payload("assignPickupForDate")
                            + "201001010101|Generated Child|Generated Guardian|"
                            + ("B" * 48)
                        },
                    },
                    "response": {
                        "status": 200,
                        "headers": [{"name": "Set-Cookie", "value": "sid=session-secret"}],
                        "content": {"text": '//OK[{"child":"Generated Child","name":"Generated Guardian"}]'},
                    },
                }
            ]
        }
    }
    output = tmp_path / "assignment.json"

    fixture = write_sanitized_fixture(
        json.dumps(raw),
        output,
        replacements={
            "Generated Child": "Example Child",
            "Generated Guardian": "Example Guardian",
        },
    )
    text = output.read_text()

    assert fixture["fixture_type"] == "tempus_pickup_date_assignment_capture"
    assert fixture["entries"][0]["request"]["gwt_rpc_method"] == "assignPickupForDate"
    assert "Generated Child" not in text
    assert "Generated Guardian" not in text
    assert "201001010101" not in text
    assert "session-secret" not in text
    assert "token-secret" not in text
    assert "secret" not in text
    assert "A" * 32 not in text
    assert "B" * 48 not in text
    assert "Example Child" in text
    assert "Example Guardian" in text
    assert fixture["write_enablement"]["enabled"] is False


def test_sanitized_fixture_guard_fails_when_sensitive_value_remains():
    with pytest.raises(ValueError, match="sensitive-looking"):
        assert_sanitized_fixture({"raw": "raw capture still has 201001010101"})


def test_fixture_based_assignment_payload_work_remains_gated():
    from tempus_cli.api import PICKUP_WRITES_DISABLED, TempusApi
    from tempus_cli.errors import SafetyError
    from tempus_cli.transport import ReadOnlyTempusTransport

    class FakeSession:
        def post(self, *args, **kwargs):
            raise AssertionError("write request should not be sent")

    with pytest.raises(RuntimeError, match=PICKUP_WRITES_DISABLED):
        TempusApi().assign_pickup("2026-06-08", "child-1", "123")

    transport = ReadOnlyTempusTransport(FakeSession())
    with pytest.raises(SafetyError, match="non-pickup"):
        transport.post_pickup_write_rpc(GWT_SERVICE_URL, _payload("assignPickupForDate"))


def test_assert_sanitized_fixture_accepts_generated_placeholders():
    assert_sanitized_fixture(
        {
            "fixture_type": "tempus_pickup_date_assignment_capture",
            "version": 1,
            "entries": [{"raw": "Example Child Example Guardian [REDACTED_TOKEN]"}],
        }
    )
