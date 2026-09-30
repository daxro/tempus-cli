from datetime import date, datetime, timedelta
from html import unescape
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from filelock import Timeout

from .home_api import HomeApiAuthenticationRequired, HomeApiClient, HomeApiTransport
from .token_store import load_token, save_token, session_lock


def _first(raw, *keys):
    if not isinstance(raw, dict):
        return None
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return value
    return None


def _walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _list_at(value, *keys):
    if isinstance(value, list):
        return value
    for item in _walk(value):
        if not isinstance(item, dict):
            continue
        for key in keys:
            rows = item.get(key)
            if isinstance(rows, list):
                return rows
    return []


def _iso_date(value):
    if value is None:
        return None
    text = str(value)
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def _iso_datetime(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=ZoneInfo("Europe/Stockholm")).isoformat()
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return text


def _child_name(raw):
    child = _first(raw, "child", "homeChild")
    if isinstance(child, dict):
        return _first(child, "name", "displayName", "fullName")
    direct = _first(raw, "childName", "name")
    if direct:
        return direct
    first_name = _first(raw, "firstName")
    last_name = _first(raw, "lastName")
    return " ".join(str(part) for part in (first_name, last_name) if part) or None


def _unit_name(raw):
    unit = _first(raw, "department", "unit", "enrollment")
    if isinstance(unit, dict):
        return _first(unit, "name", "departmentName", "unitName")
    return _first(raw, "departmentName", "unitName")


def _context(data):
    children = _list_at(data, "children")
    departments = _list_at(data, "departments")
    child_names = {}
    child_enrollments = {}
    enrollment_map = {}
    for child in children:
        if not isinstance(child, dict):
            continue
        child_id = _first(child, "childId", "homeChildId", "id")
        if child_id is None:
            continue
        child_id = str(child_id)
        child_names[child_id] = _child_name(child)
        child_enrollments[child_id] = []
        enrollments = child.get("enrollments")
        for enrollment in enrollments if isinstance(enrollments, list) else []:
            if not isinstance(enrollment, dict):
                continue
            enrollment_id = _first(enrollment, "enrollmentId", "id")
            department_id = _first(enrollment, "departmentId")
            record = {
                "department_id": str(department_id) if department_id is not None else None,
                "start": _iso_date(_first(enrollment, "enrollmentStart", "startDate")),
                "stop": _iso_date(_first(enrollment, "enrollmentStop", "stopDate")),
            }
            child_enrollments[child_id].append(record)
            if enrollment_id is not None:
                enrollment_map[str(enrollment_id)] = (child_id, record["department_id"])
    department_names = {
        str(_first(row, "departmentId", "id")): _first(row, "departmentName", "name")
        for row in departments
        if isinstance(row, dict) and _first(row, "departmentId", "id") is not None
    }
    return child_names, child_enrollments, enrollment_map, department_names


def normalize_children(data):
    rows = _list_at(data, "children")
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        child_id = _first(row, "childId", "homeChildId", "id")
        name = _first(row, "name", "displayName", "fullName", "childName") or _child_name(row)
        if child_id is None or not name:
            continue
        key = (str(child_id), str(name))
        if key in seen:
            continue
        seen.add(key)
        result.append({"id": str(child_id), "name": str(name)})
    return result


def normalize_pickups(data, init_data=None):
    rows = _list_at(data, "pickups")
    child_names, _, _, _ = _context(init_data or data)
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        pickup_id = _first(row, "pickupId", "id")
        name = _first(row, "name", "pickupName", "displayName")
        if pickup_id is None and not name:
            continue
        child_rows = row.get("children") or row.get("childIds") or []
        children = []
        if isinstance(child_rows, list):
            for child in child_rows:
                if isinstance(child, dict):
                    child_name = _first(child, "name", "displayName", "childName")
                else:
                    child_name = child_names.get(str(child), child)
                if child_name:
                    children.append(str(child_name))
        result.append(
            {
                "id": str(pickup_id) if pickup_id is not None else None,
                "name": str(name or ""),
                "phone": _first(row, "phoneNumber", "phone"),
                "children": children,
                "_raw": row,
            }
        )
    return result


def normalize_calendar_events(data, init_data=None):
    rows = _list_at(data, "calendarEvents", "events")
    child_names, child_enrollments, _, department_names = _context(init_data or data)
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        start = _first(row, "startDate", "start", "fromDate", "date")
        stop = _first(row, "stopDate", "endDate", "stop", "toDate", "date")
        start_date = _iso_date(start)
        if not start_date:
            continue
        department_ids = [str(value) for value in row.get("departmentIds") or []]
        matches = []
        for child_id, enrollments in child_enrollments.items():
            for enrollment in enrollments:
                if enrollment["department_id"] not in department_ids:
                    continue
                if enrollment["start"] and enrollment["start"] > (_iso_date(stop) or start_date):
                    continue
                if enrollment["stop"] and enrollment["stop"] < start_date:
                    continue
                matches.append((child_names.get(child_id), department_names.get(enrollment["department_id"])))
        if not matches:
            matches = [(_child_name(row), _unit_name(row))]
        scheduling_allowed = _first(row, "schedulingAllowed", "scheduleAllowed")
        if scheduling_allowed is None and isinstance(row.get("locked"), bool):
            scheduling_allowed = not row["locked"]
        for child_name, unit_name in matches:
            result.append({
                "child": child_name,
                "unit": unit_name,
                "id": str(_first(row, "calendarEventId", "eventId", "id") or ""),
                "message": str(_first(row, "title", "message", "name") or ""),
                "description": _first(row, "description", "text", "information"),
                "start_date": start_date,
                "stop_date": _iso_date(stop) or start_date,
                "scheduling_allowed": scheduling_allowed,
            })
    result.sort(key=lambda row: (row["start_date"], row.get("child") or "", row.get("id") or ""))
    return result


def _clock(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        total_minutes = int(value) // 60000
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
    return str(value)[:5]


def _dated_time(day, value):
    if value is None:
        return None
    if isinstance(value, str) and "T" in value:
        return _iso_datetime(value)
    clock = _clock(value)
    if not day or not clock:
        return None
    try:
        return datetime.fromisoformat(f"{day}T{clock}").replace(
            tzinfo=ZoneInfo("Europe/Stockholm")
        ).isoformat()
    except ValueError:
        return None


def normalize_schedules(data, init_data=None):
    rows = _list_at(data, "schedules")
    child_names, _, enrollment_map, department_names = _context(init_data or data)
    result = []
    pickup_names = {
        str(_first(row, "pickupId", "id")): _first(row, "name", "pickupName")
        for row in _list_at(init_data or data, "pickups")
        if isinstance(row, dict) and _first(row, "pickupId", "id") is not None
    }
    for wrapper in rows:
        if not isinstance(wrapper, dict):
            continue
        wrapper_child_id = _first(wrapper, "childId", "homeChildId")
        nested = wrapper.get("schedules") if isinstance(wrapper.get("schedules"), list) else [wrapper]
        for row in nested:
            if not isinstance(row, dict):
                continue
            schedule_date = _iso_date(_first(row, "date", "scheduleDate"))
            if not schedule_date:
                continue
            groups = {}
            raw_times = _first(row, "scheduleTimes", "times", "timeSpans") or []
            for span in raw_times if isinstance(raw_times, list) else []:
                if not isinstance(span, dict):
                    continue
                enrollment_id = _first(span, "enrollmentId")
                mapped_child, department_id = enrollment_map.get(str(enrollment_id), (None, None))
                child_id = str(wrapper_child_id or mapped_child or "") or None
                key = department_id
                groups.setdefault(key, []).append(
                    {
                        "start": _clock(_first(span, "startTime", "start", "from")),
                        "stop": _clock(_first(span, "stopTime", "stop", "to", "end")),
                    }
                )
            if not groups:
                groups[None] = []
            pickup_id = _first(row, "pickupId")
            for department_id, times in groups.items():
                child_id = str(wrapper_child_id or "") or None
                result.append(
                    {
                        "date": schedule_date,
                        "child": child_names.get(child_id) or _child_name(row),
                        "child_id": child_id,
                        "unit": department_names.get(department_id) or _unit_name(row),
                        "times": times,
                        "pickup": (
                            {"id": str(pickup_id), "name": pickup_names.get(str(pickup_id))}
                            if pickup_id is not None
                            else None
                        ),
                        "arriving_alone": bool(_first(row, "arrivingAlone") or False),
                        "departing_alone": bool(_first(row, "departingAlone") or False),
                        "message": _first(row, "message", "note"),
                        "_raw": {**row, "childId": wrapper_child_id},
                    }
                )
    result.sort(key=lambda row: (row["date"], row.get("child") or ""))
    return result


def normalize_absences(data, init_data=None):
    rows = _list_at(data, "absences", "absenceReports")
    child_names, child_enrollments, enrollment_map, department_names = _context(init_data or data)
    result = []
    for wrapper in rows:
        if not isinstance(wrapper, dict):
            continue
        wrapper_child_id = _first(wrapper, "childId", "homeChildId")
        nested = wrapper.get("reports") if isinstance(wrapper.get("reports"), list) else [wrapper]
        for report in nested:
            if not isinstance(report, dict):
                continue
            spans = report.get("absenceTimes") if isinstance(report.get("absenceTimes"), list) else [report]
            for row in spans:
                if not isinstance(row, dict):
                    continue
                dates = report.get("dates") if isinstance(report.get("dates"), list) else []
                start = _iso_date(
                    _first(report, "startDate", "date", "fromDate")
                    or _first(row, "startDate", "date", "fromDate")
                    or (dates[0] if dates else None)
                )
                stop = _iso_date(
                    _first(report, "stopDate", "toDate")
                    or _first(row, "stopDate", "toDate")
                    or (dates[-1] if dates else start)
                )
                if not start:
                    continue
                category = _first(row, "absenceCategoryName", "category", "absenceCategory", "reason")
                if isinstance(category, dict):
                    category = _first(category, "name", "title", "description")
                enrollment_id = _first(row, "enrollmentId")
                mapped_child, department_id = enrollment_map.get(str(enrollment_id), (None, None))
                child_id = str(wrapper_child_id or mapped_child or "") or None
                if department_id is None and child_id:
                    active = [
                        enrollment["department_id"]
                        for enrollment in child_enrollments.get(child_id, [])
                        if (not enrollment["start"] or enrollment["start"] <= start)
                        and (not enrollment["stop"] or enrollment["stop"] >= start)
                    ]
                    if len(set(active)) == 1:
                        department_id = active[0]
                result.append(
                    {
                        "id": str(_first(row, "absenceReportId", "absenceId", "id") or ""),
                        "child": child_names.get(child_id) or _child_name(row),
                        "unit": department_names.get(department_id) or _unit_name(row),
                        "start_date": start,
                        "stop_date": stop or start,
                        "all_day": bool(_first(report, "allDayAbsence", "allDay", "completeDay") or False),
                        "start_time": _clock(_first(row, "startTime")),
                        "stop_time": _clock(_first(row, "stopTime", "endTime")),
                        "category": category,
                        "message": _first(row, "messageFromParent", "message", "note"),
                    }
                )
    result.sort(key=lambda row: (row["start_date"], row.get("child") or ""))
    return result


def normalize_attendance(data, init_data=None):
    rows = _list_at(data, "attendance", "attendances")
    child_names, _, enrollment_map, department_names = _context(init_data or data)
    grouped = []
    for wrapper in rows:
        if not isinstance(wrapper, dict):
            continue
        child_id = str(_first(wrapper, "childId") or "") or None
        nested = wrapper.get("attendance") if isinstance(wrapper.get("attendance"), list) else [wrapper]
        for row in nested:
            attendance_date = _iso_date(_first(row, "date", "attendanceDate", "startTime"))
            if not attendance_date:
                continue
            by_department = {}
            intervals = row.get("attendanceTimes") or row.get("intervals") or [row]
            for interval in intervals if isinstance(intervals, list) else []:
                if not isinstance(interval, dict):
                    continue
                _, department_id = enrollment_map.get(str(_first(interval, "enrollmentId")), (None, None))
                by_department.setdefault(department_id, []).append(
                    {
                        "start_at": _dated_time(attendance_date, _first(interval, "startTime", "checkIn", "start")),
                        "stop_at": _dated_time(
                            attendance_date,
                            _first(interval, "stopTime", "checkOut", "stop", "end"),
                        ),
                    }
                )
            for department_id, normalized in by_department.items():
                grouped.append(
                    {
                        "date": attendance_date,
                        "child": child_names.get(child_id) or _child_name(row),
                        "unit": department_names.get(department_id) or _unit_name(row),
                        "intervals": normalized,
                    }
                )
    grouped.sort(key=lambda row: (row["date"], row.get("child") or ""))
    return grouped


def _normalize_content(data, kind, init_data=None):
    keys = {
        "messages": ("messages",),
        "blog": ("blogPosts", "posts", "blog"),
        "todos": ("toDoList", "todos", "list"),
        "meetings": ("invitations", "reservations", "meetings"),
        "reviews": ("reviews",),
    }[kind]
    if kind == "meetings" and isinstance(data, dict):
        rows = []
        for key in ("invitations", "reservations", "meetings"):
            values = data.get(key)
            if isinstance(values, list):
                rows.extend(row for row in values if isinstance(row, dict))
    else:
        rows = [row for row in _list_at(data, *keys) if isinstance(row, dict)]
    child_names, _, _, department_names = _context(init_data or data)

    def child_name(row):
        child_id = _first(row, "childId", "homeChildId")
        return (child_names.get(str(child_id)) if child_id is not None else None) or _child_name(row)

    def unit_name(row):
        department_id = _first(row, "departmentId")
        return (department_names.get(str(department_id)) if department_id is not None else None) or _unit_name(row)

    def text(value):
        if value is None:
            return None
        value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", str(value))
        value = re.sub(r"(?s)<[^>]+>", " ", value)
        return " ".join(unescape(value).split())

    result = []
    for row in rows:
        if kind == "messages":
            sender = _first(row, "sender", "author", "from", "authorName")
            if isinstance(sender, dict):
                sender = _first(sender, "name", "displayName")
            result.append(
                {
                    "id": str(_first(row, "messageId", "id") or ""),
                    "sent_at": _iso_datetime(_first(row, "sentAt", "sentTimestamp", "created", "date", "timestamp")),
                    "sender": sender,
                    "subject": text(_first(row, "subject", "title")),
                    "body": text(_first(row, "body", "messageHtml", "message", "text", "content")),
                    "is_read": bool(_first(row, "isRead", "markedAsRead", "read") or False),
                    "reply_allowed": bool(_first(row, "replyAllowed", "repliesAllowed", "canReply") or False),
                }
            )
        elif kind == "blog":
            author = _first(row, "author", "sender", "publisherName")
            if isinstance(author, dict):
                author = _first(author, "name", "displayName")
            result.append(
                {
                    "id": str(_first(row, "blogPostId", "postId", "id") or ""),
                    "published_at": _iso_datetime(
                        _first(row, "publishedAt", "publicationTimestamp", "created", "date", "timestamp")
                    ),
                    "author": author,
                    "title": text(_first(row, "title", "subject")),
                    "body": text(_first(row, "body", "message", "text", "content")),
                    "is_read": bool(_first(row, "isRead", "markedAsRead", "read") or False),
                    "comments_allowed": bool(_first(row, "commentsAllowed", "canComment") or False),
                }
            )
        elif kind == "todos":
            result.append(
                {
                    "id": str(_first(row, "todoId", "toDoId", "id") or ""),
                    "child": child_name(row),
                    "title": text(_first(row, "title", "toDoTitle", "name")),
                    "description": text(_first(row, "description", "message", "text")),
                    "due_date": _iso_date(_first(row, "dueDate", "deadlineDate", "stopDate", "date")),
                    "finished": bool(_first(row, "finished", "isFinished", "completed") or False),
                }
            )
        elif kind == "meetings":
            meeting = row.get("meeting") if isinstance(row.get("meeting"), dict) else {}
            slot = row.get("slot") if isinstance(row.get("slot"), dict) else {}
            meeting_date = _iso_date(_first(slot, "date") or _first(row, "date"))
            start_value = _first(slot, "startTime")
            if start_value is None:
                start_value = _first(row, "startTime", "start", "date")
            stop_value = _first(slot, "stopTime")
            if stop_value is None:
                stop_value = _first(row, "stopTime", "stop", "end")
            result.append(
                {
                    "id": str(
                        _first(row, "reservationId", "invitationId", "meetingId", "id")
                        or _first(meeting, "meetingId", "id")
                        or ""
                    ),
                    "child": child_name(row),
                    "unit": unit_name(row),
                    "title": text(_first(row, "title", "name", "subject") or _first(meeting, "title", "name")),
                    "start_at": _dated_time(meeting_date, start_value),
                    "stop_at": _dated_time(meeting_date, stop_value),
                    "status": _first(row, "status", "state"),
                    "response_required": bool(
                        _first(row, "responseRequired", "requiresResponse")
                        or (_first(row, "reservationId") is None and bool(meeting))
                    ),
                }
            )
        elif kind == "reviews":
            result.append(
                {
                    "id": str(_first(row, "reviewId", "id") or ""),
                    "child": child_name(row),
                    "unit": unit_name(row),
                    "title": text(_first(row, "title", "reviewName", "name")),
                    "description": text(_first(row, "description", "message", "text")),
                    "due_date": _iso_date(_first(row, "dueDate", "answerStartDate", "stopDate", "date")),
                    "answered": bool(_first(row, "answered", "isAnswered", "finished") or False),
                }
            )
    if kind in {"messages", "blog"}:
        timestamp_key = "sent_at" if kind == "messages" else "published_at"
        result.sort(key=lambda row: (row.get(timestamp_key) or "", row.get("id") or ""), reverse=True)
    elif kind in {"todos", "reviews"}:
        complete_key = "finished" if kind == "todos" else "answered"
        result.sort(
            key=lambda row: (
                row.get(complete_key) is True,
                row.get("due_date") or "9999-12-31",
                row.get("id") or "",
            )
        )
    else:
        result.sort(key=lambda row: (row.get("start_at") or "", row.get("id") or ""))
    return result


def normalize_calendar_link(data):
    if isinstance(data, dict):
        configured = bool(_first(data, "url", "calendarLink", "link", "enabled"))
    else:
        configured = bool(data)
    return {"configured": configured}


class HomeTempusApi:
    def __init__(self, *, token=None, token_path=None, transport=None):
        self.token = token
        self.token_path = Path(token_path) if token_path else None
        self.transport = transport or HomeApiTransport()
        self._init_cache = None

    def schemas(self, area_id=12):
        return HomeApiClient(transport=self.transport).schemas(area_id)

    def identity_providers(self, schema_id=399):
        return HomeApiClient(transport=self.transport).identity_providers(schema_id)

    def _authenticated(self, operation):
        if not self.token_path:
            client = HomeApiClient(token=self.token, transport=self.transport)
            result = operation(client)
            self.token = client.token
            return result
        try:
            with session_lock(self.token_path):
                token, _state = load_token(self.token_path)
                if not token:
                    raise HomeApiAuthenticationRequired(
                        "Legacy or missing Tempus session; run tempus setup to create a Home API session"
                    )
                client = HomeApiClient(token=token, transport=self.transport)
                result = operation(client)
                if client.token != token:
                    save_token(self.token_path, client.token)
                self.token = client.token
                return result
        except Timeout as exc:
            raise RuntimeError("Timed out waiting for the Tempus session lock") from exc

    def initialize(self):
        self._init_cache = self._authenticated(lambda client: client.initialize())
        return self._init_cache

    def _init_data(self):
        return self._init_cache if self._init_cache is not None else self.initialize()

    def children_and_notifications(self):
        return normalize_children(self._init_data())

    def pickups(self):
        init_data = self._init_data()
        data = self._authenticated(lambda client: client.get("/pickups"))
        return normalize_pickups(data, init_data)

    def refresh_calendar(self, start_date, stop_date):
        return self._authenticated(lambda client: client.refresh_calendar(start_date, stop_date))

    def upcoming_events(self, start_date=None, stop_date=None):
        today = date.today()
        start_date = start_date or today.isoformat()
        stop_date = stop_date or (today + timedelta(days=90)).isoformat()
        data = self.refresh_calendar(start_date, stop_date)
        return normalize_calendar_events(data, data)

    def schedules(self, start_date, stop_date):
        init_data = self._init_data()
        data = self._authenticated(lambda client: client.get(f"/schedules/{start_date}/{stop_date}"))
        return normalize_schedules(data, init_data)

    def pickup_assignment(self, pickup_date, child_id):
        rows = self.schedules(pickup_date, pickup_date)
        matches = [row for row in rows if row.get("date") == pickup_date and str(row.get("child_id")) == str(child_id)]
        if not matches:
            raise RuntimeError("Tempus schedule response did not contain a matching child/date assignment")
        pickup_ids = {(row.get("pickup") or {}).get("id") for row in matches}
        if len(pickup_ids) != 1:
            raise RuntimeError("Tempus schedule response contained conflicting child/date pickup assignments")
        row = matches[0]
        raw = row.get("_raw") or {}
        pickup = row.get("pickup") or {}
        schedule_id = _first(raw, "scheduleId", "id")
        return {
            "date": pickup_date,
            "child_id": str(child_id),
            "pickup_id": pickup.get("id"),
            "assignment_id": str(schedule_id) if schedule_id is not None else None,
            "version": _first(raw, "version"),
            "write_token": None,
            "write_supported": False,
            "schedule_id": str(schedule_id) if schedule_id is not None else None,
            "start_ms": None,
            "end_ms": None,
            "block_reason": "home_api_write_fixture_required",
            "_raw": raw,
        }

    def attendance(self, start_date, stop_date):
        data = self.refresh_calendar(start_date, stop_date)
        return normalize_attendance(data, data)

    def absences(self, start_date, stop_date):
        init_data = self._init_data()
        data = self._authenticated(lambda client: client.get(f"/absenceReports/{start_date}/{stop_date}"))
        return normalize_absences(data, init_data)

    def report_absence(self, child_id, dates):
        return self._authenticated(lambda client: client.report_absence(child_id, dates))

    def calendar_events(self, start_date, stop_date):
        init_data = self._init_data()
        data = self._authenticated(lambda client: client.get(f"/calendarevents/{start_date}/{stop_date}"))
        return normalize_calendar_events(data, init_data)

    def messages(self, since):
        data = self._authenticated(lambda client: client.get(f"/messages/{since}"))
        return _normalize_content(data, "messages")

    def blog_posts(self, since):
        data = self._authenticated(lambda client: client.get(f"/blog/{since}"))
        return _normalize_content(data, "blog")

    def todos(self):
        init_data = self._init_data()
        return _normalize_content(
            self._authenticated(lambda client: client.get("/todo")),
            "todos",
            init_data,
        )

    def meetings(self):
        init_data = self._init_data()
        return _normalize_content(
            self._authenticated(lambda client: client.get("/meetings")),
            "meetings",
            init_data,
        )

    def reviews(self):
        stop = date.today()
        try:
            start = stop.replace(year=stop.year - 10)
        except ValueError:
            start = stop.replace(year=stop.year - 10, day=28)
        path = f"/review/{start.isoformat()}/{stop.isoformat()}"
        init_data = self._init_data()
        return _normalize_content(
            self._authenticated(lambda client: client.get(path)),
            "reviews",
            init_data,
        )

    def calendar_link(self):
        data = self._authenticated(lambda client: client.get("/calendarlink"))
        return normalize_calendar_link(data)

    def assign_pickup(self, assignment):
        raise RuntimeError("Home API pickup writes require sanitized POST /schedules fixtures")
