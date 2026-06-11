import json
from pathlib import Path

import pytest

from tempus_cli.upcoming_events_fixtures import (
    sanitize_upcoming_events_capture,
    write_sanitized_fixture,
)
from tempus_cli.pickup_fixtures import assert_sanitized_fixture


def test_sanitize_upcoming_events_capture_removes_sensitive_values(tmp_path):
    raw = {
        "log": {
            "entries": [
                {
                    "request": {
                        "method": "POST",
                        "url": "https://home.tempusinfo.se/tempusHome/tempusHome/service",
                        "headers": [{"name": "Cookie", "value": "secret-cookie"}],
                        "postData": {"text": "7|0|4|BASE|PERM|SERVICE|getHomeOverviewData|1|2|3|4|0|"},
                    },
                    "response": {
                        "status": 200,
                        "headers": [{"name": "Set-Cookie", "value": "secret-cookie"}],
                        "content": {"text": "//OK[]"},
                    },
                }
            ]
        }
    }
    fixture = sanitize_upcoming_events_capture(json.dumps(raw))
    entry = fixture["entries"][0]
    assert entry["request"]["headers"] == [{"name": "Cookie", "value": "[REDACTED]"}]
    assert entry["response"]["headers"] == [{"name": "Set-Cookie", "value": "[REDACTED]"}]
    assert entry["request"]["gwt_rpc_method"] is None

    output = tmp_path / "fixture.json"
    written = write_sanitized_fixture(json.dumps(raw), output)
    assert json.loads(output.read_text(encoding="utf-8")) == written


def test_upcoming_events_fixture_rejects_sensitive_identifier():
    with pytest.raises(ValueError, match="sensitive-looking"):
        assert_sanitized_fixture({"raw": "raw capture still has 201001010101"})


def test_committed_upcoming_events_fixture_is_sanitized():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "upcoming_events" / "home_overview_data.json").read_text(encoding="utf-8")
    )
    assert_sanitized_fixture(fixture)
