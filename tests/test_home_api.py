import json
import os
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from tempus_cli.errors import SafetyError
from tempus_cli.home_api import HomeApiClient, HomeApiTransport, validate_home_api_login_url
from tempus_cli.home_client import (
    HomeTempusApi,
    _normalize_content,
    normalize_absences,
    normalize_attendance,
    normalize_calendar_link,
    normalize_calendar_events,
    normalize_children,
    normalize_pickups,
    normalize_schedules,
)
from tempus_cli.session import parse_home_api_auth_token
from tempus_cli.token_store import load_token, save_token


FIXTURES = Path(__file__).parent / "fixtures" / "home_api"
TOKEN_A = "a" * 64
TOKEN_B = "b" * 64
TOKEN_C = "c" * 64


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_home_api_auth_token_accepts_only_one_static_message():
    html = f"<script>window.ReactNativeWebView.postMessage('{TOKEN_A}')</script>"
    assert parse_home_api_auth_token(html) == TOKEN_A
    with pytest.raises(RuntimeError, match="exactly one"):
        parse_home_api_auth_token("<html>missing</html>")
    with pytest.raises(RuntimeError, match="exactly one"):
        parse_home_api_auth_token(html + f'<script>ReactNativeWebView.postMessage("{TOKEN_B}")</script>')
    with pytest.raises(RuntimeError, match="exactly one"):
        parse_home_api_auth_token(html + html)


def test_validate_home_api_login_url_rejects_changed_project_and_host():
    valid = (
        "https://login.tempusinfo.se/login/saml/login?force_client=STOCKHOLM_PROD"
        "&schemaId=399&project=HOME_API&createLoginCookie=false&origin=null"
    )
    assert validate_home_api_login_url(valid) == valid
    with pytest.raises(SafetyError):
        validate_home_api_login_url(valid.replace("project=HOME_API", "project=HOME"))
    with pytest.raises(SafetyError):
        validate_home_api_login_url(valid.replace("force_client=STOCKHOLM_PROD", "force_client=OTHER"))
    with pytest.raises(SafetyError):
        validate_home_api_login_url(valid.replace("login.tempusinfo.se", "example.test"))


def test_transport_blocks_unknown_paths_and_queries():
    transport = HomeApiTransport()
    with pytest.raises(SafetyError, match="path"):
        transport._check_request("https://homeapi.tempusinfo.se/tempusHomeApi/v1/income")
    with pytest.raises(SafetyError, match="path"):
        transport._check_request("https://homeapi.tempusinfo.se/tempusHomeApi/v1/messages/not-a-date")
    with pytest.raises(SafetyError, match="query"):
        transport._check_request("https://homeapi.tempusinfo.se/tempusHomeApi/v1/init?unexpected=true")
    with pytest.raises(SafetyError, match="query"):
        transport._check_request(
            "https://homeapi.tempusinfo.se/tempusHomeApi/v1/init",
            params={"token": "secret"},
        )
    with pytest.raises(SafetyError, match="validateAuthToken"):
        transport._check_request(
            "https://homeapi.tempusinfo.se/tempusHomeApi/v1/validateAuthToken",
            params={"wrong": "secret"},
        )


def test_transport_streams_and_bounds_json_response(monkeypatch):
    from tempus_cli import home_api as home_api_module

    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def __init__(self, chunks):
            self.chunks = chunks
            self.closed = False

        def iter_content(self, chunk_size):
            assert chunk_size == 64 * 1024
            yield from self.chunks

        def close(self):
            self.closed = True

    class Session:
        def __init__(self, response):
            self.headers = {}
            self.response = response
            self.kwargs = None

        def get(self, url, **kwargs):
            self.kwargs = kwargs
            return self.response

    response = Response([b'{"ok":', b"true}"])
    session = Session(response)
    assert HomeApiTransport(session=session).get_json("/init", token=TOKEN_A) == {"ok": True}
    assert session.kwargs["stream"] is True
    assert session.kwargs["allow_redirects"] is False
    assert response.closed is True

    monkeypatch.setattr(home_api_module, "MAX_JSON_BYTES", 8)
    oversized = Response([b"12345", b"6789"])
    with pytest.raises(SafetyError, match="oversized"):
        HomeApiTransport(session=Session(oversized)).get_json("/init")
    assert oversized.closed is True


def test_token_store_is_versioned_0600_and_recognizes_legacy(tmp_path):
    path = tmp_path / "session.json"
    save_token(path, TOKEN_A)
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert load_token(path) == (TOKEN_A, "persisted")
    path.write_text("[]", encoding="utf-8")
    assert load_token(path) == (None, "legacy")


def test_sanitized_home_api_normalizers_have_stable_shapes():
    init = fixture("init.json")
    refresh = fixture("refresh_calendar.json")
    assert normalize_children(init) == [{"id": "101", "name": "Example Child"}]
    assert normalize_pickups(init)[0]["id"] == "201"
    assert normalize_schedules(refresh)[0]["pickup"] == {"id": "201", "name": "Example Guardian"}
    assert normalize_attendance(refresh)[0]["intervals"][0]["start_at"].startswith("2026-08-24T08:05")
    assert normalize_absences(refresh)[0] == {
        "id": "901",
        "child": "Example Child",
        "unit": "Example Unit",
        "start_date": "2026-08-24",
        "stop_date": "2026-08-24",
        "all_day": True,
        "start_time": None,
        "stop_time": None,
        "category": "Example category",
        "message": "Generated fixture",
    }
    assert normalize_calendar_events(refresh)[0] == {
        "child": "Example Child",
        "unit": "Example Unit",
        "id": "501",
        "message": "Example event",
        "description": "Generated fixture",
        "start_date": "2026-09-02",
        "stop_date": "2026-09-03",
        "scheduling_allowed": True,
    }


def test_sanitized_content_endpoint_fixtures_have_stable_shapes():
    init = fixture("init.json")
    messages = _normalize_content(fixture("messages.json"), "messages")
    assert messages == [{
        "id": "1001",
        "sent_at": "2026-08-25T00:00:00+02:00",
        "sender": "Example Sender",
        "subject": "Example message",
        "body": "Generated fixture",
        "is_read": True,
        "reply_allowed": False,
    }]

    blog = _normalize_content(fixture("blog.json"), "blog")
    assert blog[0] == {
        "id": "1101",
        "published_at": "2026-08-25T00:00:00+02:00",
        "author": "Example Publisher",
        "title": "Example blog post",
        "body": "Generated fixture",
        "is_read": False,
        "comments_allowed": True,
    }

    todos = _normalize_content(fixture("todo.json"), "todos", init)
    assert todos[0]["child"] == "Example Child"
    assert todos[0]["title"] == "Example action"
    assert todos[0]["due_date"] == "2026-09-01"

    meetings = _normalize_content(fixture("meetings.json"), "meetings", init)
    reservation = next(row for row in meetings if row["id"] == "1301")
    assert reservation["child"] == "Example Child"
    assert reservation["unit"] == "Example Unit"
    assert reservation["start_at"] == "2026-09-02T09:00:00+02:00"
    assert reservation["stop_at"] == "2026-09-02T09:30:00+02:00"
    midnight_data = fixture("meetings.json")
    midnight_data["reservations"][0]["slot"]["startTime"] = 0
    midnight = _normalize_content(midnight_data, "meetings", init)
    midnight_reservation = next(row for row in midnight if row["id"] == "1301")
    assert midnight_reservation["start_at"] == "2026-09-02T00:00:00+02:00"

    reviews = _normalize_content(fixture("reviews.json"), "reviews", init)
    assert reviews[0]["child"] == "Example Child"
    assert reviews[0]["unit"] == "Example Unit"
    assert reviews[0]["title"] == "Example review"
    assert reviews[0]["due_date"] == "2026-09-03"
    assert normalize_calendar_link(fixture("calendar_link.json")) == {"configured": True}


def test_pickup_assignment_accepts_consistent_multi_department_rows():
    api = HomeTempusApi(token=TOKEN_A)
    api.schedules = lambda start, stop: [
        {"date": start, "child_id": "101", "pickup": {"id": "201"}, "_raw": {"date": start}},
        {"date": start, "child_id": "101", "pickup": {"id": "201"}, "_raw": {"date": start}},
    ]
    assert api.pickup_assignment("2026-08-25", "101")["pickup_id"] == "201"

    api.schedules = lambda start, stop: [
        {"date": start, "child_id": "101", "pickup": {"id": "201"}, "_raw": {}},
        {"date": start, "child_id": "101", "pickup": {"id": "202"}, "_raw": {}},
    ]
    with pytest.raises(RuntimeError, match="conflicting"):
        api.pickup_assignment("2026-08-25", "101")


class FakeTransport:
    def __init__(self):
        self.tokens = []

    def get_json(self, path, *, token=None, params=None):
        self.tokens.append(token)
        assert path == "/init"
        return fixture("init.json")


def test_authenticated_init_reloads_and_persists_rotated_token(tmp_path):
    path = tmp_path / "session.json"
    save_token(path, TOKEN_A)
    transport = FakeTransport()
    api = HomeTempusApi(token_path=path, transport=transport)
    api.initialize()
    assert transport.tokens == [TOKEN_A]
    assert load_token(path) == (TOKEN_B, "persisted")


def test_authenticated_requests_serialize_reload_and_rotation(tmp_path):
    class RotatingTransport:
        def __init__(self):
            self.tokens = []
            self.in_flight = 0
            self.max_in_flight = 0
            self.guard = threading.Lock()

        def get_json(self, path, *, token=None, params=None):
            assert path == "/init"
            with self.guard:
                self.tokens.append(token)
                self.in_flight += 1
                self.max_in_flight = max(self.max_in_flight, self.in_flight)
            time.sleep(0.03)
            with self.guard:
                self.in_flight -= 1
            return {"newJwt": {"token": TOKEN_B if token == TOKEN_A else TOKEN_C}}

    path = tmp_path / "session.json"
    save_token(path, TOKEN_A)
    transport = RotatingTransport()
    apis = [HomeTempusApi(token_path=path, transport=transport) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda api: api.initialize(), apis))

    assert transport.max_in_flight == 1
    assert transport.tokens == [TOKEN_A, TOKEN_B]
    assert load_token(path) == (TOKEN_C, "persisted")
