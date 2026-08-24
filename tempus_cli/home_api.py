import json
import re
from datetime import date
from urllib.parse import urlsplit

import requests

from . import __version__
from .errors import SafetyError, TempusError
from .net import wrap_network_error


HOME_API_BASE = "https://homeapi.tempusinfo.se/tempusHomeApi/v1"
HOME_API_HOST = "homeapi.tempusinfo.se"
# Public protocol identifier shipped in the official Android app; not a user credential.
HOME_API_KEY = "4c2894b0-703e-11e6-bdf4-0800200c9a66"
HOME_APP_VERSION = "3.41.0"
HTTP_TIMEOUT = 30
MAX_JSON_BYTES = 10 * 1024 * 1024

_DATE = r"\d{4}-\d{2}-\d{2}"
_PUBLIC_PATHS = (
    re.compile(r"/tempusHomeApi/v1/loginDestinations"),
    re.compile(r"/tempusHomeApi/v1/loginOptions/HOME_API/[1-9]\d*"),
    re.compile(r"/tempusHomeApi/v1/identityProviders/HOME_API/[1-9]\d*"),
    re.compile(r"/tempusHomeApi/v1/validateAuthToken"),
)
_READ_PATHS = _PUBLIC_PATHS + (
    re.compile(r"/tempusHomeApi/v1/init"),
    re.compile(rf"/tempusHomeApi/v1/refreshCalendar/{_DATE}/{_DATE}"),
    re.compile(rf"/tempusHomeApi/v1/schedules/{_DATE}/{_DATE}"),
    re.compile(rf"/tempusHomeApi/v1/absenceReports/{_DATE}/{_DATE}"),
    re.compile(rf"/tempusHomeApi/v1/calendarevents/{_DATE}/{_DATE}"),
    re.compile(r"/tempusHomeApi/v1/pickups"),
    re.compile(rf"/tempusHomeApi/v1/messages/{_DATE}"),
    re.compile(rf"/tempusHomeApi/v1/blog/{_DATE}"),
    re.compile(r"/tempusHomeApi/v1/todo"),
    re.compile(r"/tempusHomeApi/v1/meetings"),
    re.compile(rf"/tempusHomeApi/v1/review/{_DATE}/{_DATE}"),
    re.compile(r"/tempusHomeApi/v1/calendarlink"),
)


class HomeApiAuthenticationRequired(TempusError):
    """Raised when a Home API JWT is missing or rejected."""


def _validate_date(value):
    if not isinstance(value, str) or not re.fullmatch(_DATE, value):
        raise ValueError("date must be a valid YYYY-MM-DD value")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("date must be a valid YYYY-MM-DD value") from exc


class HomeApiTransport:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json;charset=UTF-8",
                "Accept-Language": "sv",
                "Content-Type": "application/json;charset=UTF-8",
                "User-Agent": f"tempus-cli/{__version__}",
                "x-app-os-version": "cli",
                "x-app-device-id": "tempus-cli",
                "x-app-version": HOME_APP_VERSION,
                "x-app-platform": "Android",
                "x-api-key": HOME_API_KEY,
            }
        )

    def get_json(self, path, *, token=None, params=None):
        url = HOME_API_BASE + path
        self._check_request(url, params=params)
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            response = self.session.get(
                url,
                params=params,
                headers=headers,
                allow_redirects=False,
                stream=True,
                timeout=HTTP_TIMEOUT,
            )
        except requests.exceptions.RequestException as exc:
            raise wrap_network_error(exc, "Tempus Home API GET") from exc
        try:
            if 300 <= response.status_code < 400:
                raise SafetyError("Blocked unexpected Home API redirect")
            if response.status_code == 401:
                raise HomeApiAuthenticationRequired("Tempus Home API session is expired; run tempus setup again")
            if not 200 <= response.status_code < 300:
                raise TempusError(f"Tempus Home API returned HTTP {response.status_code}")
            length = response.headers.get("Content-Length")
            if length:
                try:
                    if not 0 <= int(length) <= MAX_JSON_BYTES:
                        raise SafetyError("Blocked oversized Home API response")
                except ValueError as exc:
                    raise SafetyError("Blocked invalid Home API content length") from exc
            content_type = response.headers.get("Content-Type", "").lower()
            if "json" not in content_type:
                raise RuntimeError("Tempus Home API returned a non-JSON response")
            chunks = []
            size = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                size += len(chunk)
                if size > MAX_JSON_BYTES:
                    raise SafetyError("Blocked oversized Home API response")
                chunks.append(chunk)
            try:
                return json.loads(b"".join(chunks))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RuntimeError("Tempus Home API returned invalid JSON") from exc
        finally:
            response.close()

    def _check_request(self, url, *, params=None):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != HOME_API_HOST or parsed.port not in (None, 443):
            raise SafetyError("Blocked non-allowlisted Home API URL")
        if parsed.query or parsed.fragment:
            raise SafetyError("Blocked embedded Home API query or fragment")
        if ".." in parsed.path.split("/"):
            raise SafetyError("Blocked Home API path traversal")
        if not any(pattern.fullmatch(parsed.path) for pattern in _READ_PATHS):
            raise SafetyError(f"Blocked Home API path: {parsed.path}")
        keys = set((params or {}).keys())
        if parsed.path.endswith("/validateAuthToken"):
            if keys != {"authTokenCookieValue"}:
                raise SafetyError("Blocked unexpected validateAuthToken query")
        elif keys:
            raise SafetyError("Blocked unexpected Home API query parameters")


class HomeApiClient:
    def __init__(self, *, token=None, transport=None):
        self.token = token
        self.transport = transport or HomeApiTransport()

    def login_destinations(self):
        data = self.transport.get_json("/loginDestinations")
        locations = data.get("locations") if isinstance(data, dict) else None
        if not isinstance(locations, list):
            raise RuntimeError("Tempus login destinations response had an unexpected shape")
        return locations

    def schemas(self, area_id=12):
        location = next(
            (row for row in self.login_destinations() if str(row.get("locationId")) == str(area_id)),
            None,
        )
        if not location:
            return []
        destinations = location.get("destinations") or []
        return [
            {
                "id": row.get("destinationId"),
                "name": row.get("destinationName"),
                "project": "HOME_API",
            }
            for row in destinations
            if isinstance(row, dict)
        ]

    def login_options(self, destination_id):
        data = self.transport.get_json(f"/loginOptions/HOME_API/{int(destination_id)}")
        options = data.get("loginOptions") if isinstance(data, dict) else None
        if not isinstance(options, list):
            raise RuntimeError("Tempus login options response had an unexpected shape")
        return options

    def identity_providers(self, destination_id=399):
        options = self.login_options(destination_id)
        return [
            {"name": row.get("displayName"), "option": row.get("clientEnum")}
            for row in options
            if isinstance(row, dict)
        ]

    def exchange_saml_token(self, auth_token):
        if (
            not isinstance(auth_token, str)
            or not 16 <= len(auth_token) <= 8192
            or any(ch.isspace() for ch in auth_token)
        ):
            raise ValueError("Tempus SAML authentication token had an invalid shape")
        data = self.transport.get_json(
            "/validateAuthToken",
            params={"authTokenCookieValue": auth_token},
        )
        token = data.get("token") if isinstance(data, dict) else None
        self._set_token(token)
        return self.token

    def get(self, path):
        if not self.token:
            raise HomeApiAuthenticationRequired("No Tempus Home API session; run tempus setup")
        return self.transport.get_json(path, token=self.token)

    def initialize(self):
        data = self.get("/init")
        self._rotate_from(data)
        return data

    def refresh_calendar(self, start_date, stop_date):
        start_date = _validate_date(start_date)
        stop_date = _validate_date(stop_date)
        if start_date > stop_date:
            raise ValueError("start date must not be after stop date")
        data = self.get(f"/refreshCalendar/{start_date}/{stop_date}")
        self._rotate_from(data)
        return data

    def _rotate_from(self, data):
        new_jwt = data.get("newJwt") if isinstance(data, dict) else None
        token = new_jwt.get("token") if isinstance(new_jwt, dict) else None
        self._set_token(token)

    def _set_token(self, token):
        if not isinstance(token, str) or not 32 <= len(token) <= 16384 or any(ch.isspace() for ch in token):
            raise RuntimeError("Tempus Home API returned an invalid JWT")
        self.token = token


def validate_home_api_login_url(url, *, destination_id=399):
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise SafetyError("Tempus returned an invalid login URL") from exc
    if parsed.scheme != "https" or parsed.hostname != "login.tempusinfo.se" or parsed.port not in (None, 443):
        raise SafetyError("Tempus returned a non-allowlisted login URL")
    if parsed.path != "/login/saml/login":
        raise SafetyError("Tempus returned an unexpected login path")
    from urllib.parse import parse_qs

    query = parse_qs(parsed.query, keep_blank_values=True)
    expected_keys = {"force_client", "schemaId", "project", "createLoginCookie", "origin"}
    if set(query) != expected_keys:
        raise SafetyError("Tempus returned unexpected login query parameters")
    expected = {
        "force_client": "STOCKHOLM_PROD",
        "schemaId": str(destination_id),
        "project": "HOME_API",
        "createLoginCookie": "false",
        "origin": "null",
    }
    for key, value in expected.items():
        if query.get(key) != [value]:
            raise SafetyError(f"Tempus returned an unexpected {key} login value")
    return url
