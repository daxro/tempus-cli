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


def test_absence_write_uses_separate_exact_path_and_fixture_payload():
    fixture_data = fixture("absence_write.json")

    class Response:
        status_code = 200
        headers = {"Content-Type": "application/json"}

        def iter_content(self, chunk_size):
            yield json.dumps(fixture_data["response"]).encode()

        def close(self):
            pass

    class Session:
        def __init__(self):
            self.headers = {}
            self.calls = []

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return Response()

    session = Session()
    client = HomeApiClient(token=TOKEN_A, transport=HomeApiTransport(session=session))
    assert client.report_absence("101", ["2026-10-23"]) == fixture_data["response"]
    url, kwargs = session.calls[0]
    assert url == "https://homeapi.tempusinfo.se/tempusHomeApi/v1/absenceReports"
    assert kwargs["json"] == fixture_data["request"]
    assert kwargs["headers"] == {"Authorization": f"Bearer {TOKEN_A}"}
    assert kwargs["allow_redirects"] is False
    with pytest.raises(SafetyError, match="path"):
        HomeApiTransport()._check_request(url)
    assert normalize_absences(fixture_data["readback"], fixture("init.json"))[0]["all_day"] is True


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


def test_meeting_normalizer_ignores_non_list_collections():
    data = {
        "invitations": True,
        "reservations": {"id": "not-a-list"},
        "meetings": "not-a-list",
    }

    assert _normalize_content(data, "meetings") == []


def test_normalizers_ignore_non_list_child_enrollments():
    data = {"children": [{"id": "101", "name": "Example Child", "enrollments": 1.5}]}

    assert normalize_absences(data) == []




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




@pytest.mark.parametrize('status', [200, 204, 401, 302, 500])
def test_pickup_transport_exact_contract_one_post_and_no_redirect_or_retry(status):
    data = fixture('pickup_write.json')
    class Response:
        status_code = status
        headers = {'Content-Type': 'application/json'}
        closed = False
        def iter_content(self, chunk_size):
            yield b'{}'
        def close(self):
            self.closed = True
    class Session:
        headers = {}
        calls = []
        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            return response
    session = Session()
    session.calls = []
    response = Response()
    transport = HomeApiTransport(session=session)
    if status in (200, 204):
        transport.post_pickup(data['request']['body'], token=TOKEN_A)
    else:
        with pytest.raises(Exception):
            transport.post_pickup(data['request']['body'], token=TOKEN_A)
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == 'https://homeapi.tempusinfo.se/tempusHomeApi/v1/schedules'
    assert kwargs['json'] == data['request']['body']
    assert kwargs['allow_redirects'] is False
    assert kwargs['stream'] is True
    assert response.closed
    # Generic GET does not acquire write access.
    with pytest.raises(SafetyError):
        transport._check_request(url)


def test_pickup_transport_rejects_retry_enabled_session_before_post():
    from requests.adapters import HTTPAdapter
    session = __import__('requests').Session()
    session.mount('https://', HTTPAdapter(max_retries=3))
    transport = HomeApiTransport(session=session)
    with pytest.raises(SafetyError, match='retries'):
        transport.post_pickup(fixture('pickup_write.json')['request']['body'], token=TOKEN_A)


def test_pickup_transport_rejects_extra_dates_and_arbitrary_fields_before_network():
    from copy import deepcopy
    class Session:
        headers = {}
    transport = HomeApiTransport(session=Session())
    body = deepcopy(fixture('pickup_write.json')['request']['body'])
    body[0]['schedules'].append(deepcopy(body[0]['schedules'][0]))
    with pytest.raises(ValueError):
        transport.post_pickup(body, token=TOKEN_A)
    body = deepcopy(fixture('pickup_write.json')['request']['body'])
    body[0]['schedules'][0]['unverifiedField'] = True
    with pytest.raises(ValueError):
        transport.post_pickup(body, token=TOKEN_A)


def test_pickup_transport_checks_exact_host_before_post(monkeypatch):
    from tempus_cli import home_api
    class Session:
        headers = {}
    monkeypatch.setattr(home_api, 'HOME_API_BASE', 'https://example.test/tempusHomeApi/v1')
    with pytest.raises(SafetyError, match='pickup write URL'):
        HomeApiTransport(session=Session()).post_pickup(fixture('pickup_write.json')['request']['body'], token=TOKEN_A)
