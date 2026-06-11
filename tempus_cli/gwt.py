import json
import re
from datetime import date

TEMPUS_HOME_URL = "https://home.tempusinfo.se/tempusHome/"
GWT_SERVICE_URL = "https://home.tempusinfo.se/tempusHome/tempusHome/service"
GWT_MODULE_BASE = "https://home.tempusinfo.se/tempusHome/tempusHome/"
NOCACHE_URL = GWT_MODULE_BASE + "tempusHome.nocache.js"
HOME_SERVICE = "se.limesaudio.tempushome.client.HomeService"
HTTP_TIMEOUT = 30


def discover_permutation(session):
    resp = session.get(NOCACHE_URL, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    hashes = re.findall(r"[A-F0-9]{32}", resp.text)
    for h in hashes:
        cache = session.get(GWT_MODULE_BASE + h + ".cache.js", timeout=HTTP_TIMEOUT)
        if cache.ok:
            m = re.search(r"this\.d='([A-F0-9]{32})'", cache.text)
            if m:
                return m.group(1)
    raise RuntimeError("Could not discover GWT permutation")


def headers(permutation):
    return {
        "Content-Type": "text/x-gwt-rpc; charset=UTF-8",
        "X-GWT-Module-Base": GWT_MODULE_BASE,
        "X-GWT-Permutation": permutation,
    }


def int_rpc_payload(permutation, method, value):
    return f"7|0|5|{GWT_MODULE_BASE}|{permutation}|{HOME_SERVICE}|{method}|I|1|2|3|4|1|5|{int(value)}|"


def no_arg_rpc_payload(permutation, method):
    return f"7|0|4|{GWT_MODULE_BASE}|{permutation}|{HOME_SERVICE}|{method}|1|2|3|4|0|"


def bool_bool_rpc_payload(permutation, method, first=False, second=False):
    first_value = "1" if first else "0"
    second_value = "1" if second else "0"
    return f"7|0|5|{GWT_MODULE_BASE}|{permutation}|{HOME_SERVICE}|{method}|Z|1|2|3|4|2|5|5|{first_value}|{second_value}|"


def payload_get_schemas(permutation, area_id):
    return int_rpc_payload(permutation, "getSchemas", area_id)


def payload_get_grand_id_identity_providers(permutation, schema_id):
    return int_rpc_payload(permutation, "getGrandIdIdentityProviders", schema_id)


def payload_get_pickups(permutation):
    return no_arg_rpc_payload(permutation, "getPickups")


def payload_get_children_and_notifications(permutation):
    return no_arg_rpc_payload(permutation, "getChildrenAndNotifications")


def payload_get_home_overview_data(permutation):
    return no_arg_rpc_payload(permutation, "getHomeOverviewData")


def payload_get_week_schedules(permutation, weeks):
    encoded_weeks = "".join(f"6|{int(week)}|{int(year)}|" for year, week in weeks)
    return (
        f"7|0|6|{GWT_MODULE_BASE}|{permutation}|{HOME_SERVICE}|getWeekSchedules|"
        "java.util.ArrayList/4159755760|se.tempus.common.date.YearWeek/2102053017|"
        f"1|2|3|4|1|5|5|{len(weeks)}|{encoded_weeks}"
    )


def payload_authenticate_user_with_cookies(permutation, use_nu_cookie=False, use_bearer_auth=False):
    return bool_bool_rpc_payload(
        permutation,
        "authenticateUserWithCookies",
        first=use_nu_cookie,
        second=use_bearer_auth,
    )


def payload_heartbeat(permutation):
    return no_arg_rpc_payload(permutation, "heartbeat")


def payload_remove_pickup(permutation, pickup_id):
    return int_rpc_payload(permutation, "removePickup", pickup_id)


def string_int_rpc_payload(permutation, method, string_value, int_value):
    return (
        f"7|0|6|{GWT_MODULE_BASE}|{permutation}|{HOME_SERVICE}|{method}|"
        "java.lang.String/2004016611|I|1|2|3|4|2|5|6|"
        f"{string_value}|{int(int_value)}|"
    )


def assignment_write_rpc_payload(permutation, method, assignment):
    return (
        f"7|0|6|{GWT_MODULE_BASE}|{permutation}|{HOME_SERVICE}|{method}|"
        "java.lang.String/2004016611|I|1|2|3|4|6|5|6|6|6|5|5|"
        f"{assignment['date']}|{int(assignment['child_id'])}|{int(assignment['pickup_id'])}|"
        f"{int(assignment['assignment_id'])}|{assignment['version']}|{assignment['write_token']}|"
    )


def update_schedule_assignment_payload(permutation, assignment):
    pickup_child_ids = [str(value) for value in assignment["pickup_child_ids"]]
    pickup_child_values = "".join(f"10|{int(value)}|" for value in pickup_child_ids)
    requested = date.fromisoformat(assignment["date"])
    return (
        f"7|0|16|{GWT_MODULE_BASE}|{permutation}|{HOME_SERVICE}|updateSchedule|"
        "I|se.tempus.common.date.DateOnly/4090038506|"
        "se.tempus.common.shared.wrapper.DaySchedule/3784037161|"
        "se.tempus.common.shared.wrapper.Pickup/873253356|"
        "java.util.ArrayList/4159755760|java.lang.Integer/3438268394|"
        f"{assignment['owner_name']}|{assignment['pickup_name']}|{assignment['pickup_phone']}|"
        "java.util.TreeSet/4043497002|se.tempus.common.shared.wrapper.Schedulation/1710330904|"
        "se.tempus.common.date.TimeOnly/1619208844|"
        "1|2|3|4|3|5|6|7|"
        f"{int(assignment['child_id'])}|6|{requested.day}|{requested.month}|{requested.year}|"
        "7|0|0|0|0|8|9|2|"
        f"{pickup_child_values}"
        f"11|{int(assignment['pickup_id'])}|12|13|0|0|14|0|1|15|0|"
        f"{int(assignment['schedule_id'])}|16|{int(assignment['start_ms'])}|16|{int(assignment['end_ms'])}|"
    )


def payload_get_pickup_date_assignment(permutation, pickup_date, child_id):
    return string_int_rpc_payload(permutation, "getPickupDateAssignment", pickup_date, child_id)


def payload_assign_pickup_for_date(permutation, assignment):
    return assignment_write_rpc_payload(permutation, "assignPickupForDate", assignment)


def payload_update_schedule_assignment(permutation, assignment):
    return update_schedule_assignment_payload(permutation, assignment)


def _string_table(response):
    m = re.search(r"(\[[\s\S]*\])", response[4:] if response.startswith("//OK") else response)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    strings = []
    def walk(x):
        if isinstance(x, str):
            strings.append(x)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(data)
    return strings


def _json_payload(response):
    text = response[4:] if response.startswith("//OK") else response
    text = text.lstrip()
    decoder = json.JSONDecoder()
    try:
        data, end = decoder.raw_decode(text)
    except json.JSONDecodeError:
        return None
    remainder = text[end:].lstrip()
    if not isinstance(data, list):
        return data if not remainder else None

    merged = list(data)
    while remainder.startswith(".concat("):
        remainder = remainder[len(".concat(") :].lstrip()
        try:
            part, end = decoder.raw_decode(remainder)
        except json.JSONDecodeError:
            return None
        if not isinstance(part, list):
            return None
        merged.extend(part)
        remainder = remainder[end:].lstrip()
        if not remainder.startswith(")"):
            return None
        remainder = remainder[1:].lstrip()
    if remainder not in ("", ";"):
        return None
    return merged


def _walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _normalize_children(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    children = []
    if isinstance(value, list):
        for child in value:
            if isinstance(child, str):
                children.append(child)
            elif isinstance(child, dict):
                name = child.get("name") or child.get("displayName") or child.get("fullName")
                if name:
                    children.append(str(name))
    return children


def _normalize_pickup(raw):
    pickup_id = raw.get("id") or raw.get("pickupId") or raw.get("pickup_id")
    name = raw.get("name") or raw.get("displayName") or raw.get("fullName")
    phone = raw.get("phone") or raw.get("phoneNumber") or raw.get("mobile") or raw.get("number")
    children = _normalize_children(raw.get("children") or raw.get("child") or raw.get("homeChildren"))
    if pickup_id is None and not name and not phone:
        return None
    pickup = {
        "id": str(pickup_id) if pickup_id is not None else None,
        "name": name,
        "phone": phone,
        "children": children,
        "_raw": raw,
    }
    return pickup


def _first_dict(value):
    return next(_walk_dicts(value), None)


def _normalize_assignment(raw):
    assignment_id = raw.get("assignmentId") or raw.get("id")
    child_id = raw.get("childId") or raw.get("homeChildId") or raw.get("child_id")
    child_name = raw.get("childName") or raw.get("child") or raw.get("name")
    pickup_id = raw.get("pickupId") or raw.get("pickup_id")
    pickup_name = raw.get("pickupName") or raw.get("pickup")
    pickup_date = raw.get("date") or raw.get("pickupDate")
    version = raw.get("version") or raw.get("rowVersion")
    write_token = raw.get("writeToken") or raw.get("token")
    if not pickup_date or child_id is None or assignment_id is None or version is None or write_token is None:
        return None
    return {
        "date": str(pickup_date),
        "child_id": str(child_id),
        "child_name": str(child_name) if child_name is not None else None,
        "pickup_id": str(pickup_id) if pickup_id is not None else None,
        "pickup_name": str(pickup_name) if pickup_name is not None else None,
        "assignment_id": str(assignment_id),
        "version": str(version),
        "write_token": str(write_token),
    }


def _normalize_event_date(value):
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    if isinstance(value, dict):
        nested = value.get("date")
        if isinstance(nested, str):
            return _normalize_event_date(nested)
        year = value.get("year")
        month = value.get("month")
        day = value.get("day")
        if year is None or month is None or day is None:
            return None
        try:
            return date(int(year), int(month), int(day)).isoformat()
        except (TypeError, ValueError):
            return None
    return None


def _value_from_keys(raw, keys):
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _normalize_upcoming_event(raw, *, child=None, unit=None):
    if not isinstance(raw, dict):
        return None
    event_id = _value_from_keys(raw, ("id", "eventId", "calendarEventId"))
    message = _value_from_keys(raw, ("message", "title", "name"))
    start_date = _normalize_event_date(_value_from_keys(raw, ("startDate", "start_date", "date")))
    stop_date = _normalize_event_date(_value_from_keys(raw, ("stopDate", "stop_date", "endDate", "end_date")))
    if event_id is None or message is None:
        return None
    if start_date is None and stop_date is None:
        return None
    if stop_date is None:
        stop_date = start_date
    if start_date is None:
        start_date = stop_date
    return {
        "child": str(child) if child is not None else None,
        "unit": str(unit) if unit is not None else None,
        "id": str(event_id) if event_id is not None else None,
        "message": str(message) if message is not None else None,
        "description": _value_from_keys(raw, ("description", "details")),
        "start_date": start_date,
        "stop_date": stop_date,
        "scheduling_allowed": raw.get("schedulingAllowed", raw.get("scheduling_allowed")),
    }


def _context_value(raw, *, child=None, unit=None):
    next_child = child
    next_unit = unit
    child_value = _value_from_keys(raw, ("childName", "child", "child_name"))
    if isinstance(child_value, dict):
        next_child = _value_from_keys(child_value, ("name", "displayName", "fullName", "childName")) or next_child
        next_unit = _value_from_keys(child_value, ("unit", "departmentName", "department", "groupName", "group")) or next_unit
    elif child_value is not None:
        next_child = child_value
    next_unit = _value_from_keys(raw, ("unit", "departmentName", "department", "groupName", "group")) or next_unit
    return next_child, next_unit


def _child_contexts(raw, child, unit):
    children = raw.get("children")
    if not isinstance(children, list):
        return [(child, unit)]
    contexts = []
    for child_row in children:
        if not isinstance(child_row, dict):
            continue
        child_name = _value_from_keys(child_row, ("name", "displayName", "fullName", "childName")) or child
        child_unit = _value_from_keys(child_row, ("unit", "departmentName", "department", "groupName", "group")) or unit
        if child_name is not None:
            contexts.append((child_name, child_unit))
    return contexts or [(child, unit)]


def _extract_upcoming_events(value, *, child=None, unit=None, seen=None):
    seen = set() if seen is None else seen
    if isinstance(value, dict):
        child, unit = _context_value(value, child=child, unit=unit)
        direct_event = _normalize_upcoming_event(value, child=child, unit=unit)
        if direct_event is not None:
            key = id(value)
            if key not in seen:
                seen.add(key)
                yield direct_event
            return

        for key_name in ("calendarEvent", "event"):
            nested_event = value.get(key_name)
            nested = _normalize_upcoming_event(nested_event, child=child, unit=unit)
            if nested is not None:
                key = id(nested_event)
                if key not in seen:
                    seen.add(key)
                    yield nested

        calendar_events = value.get("calendarEvents") or value.get("calendar_events")
        if isinstance(calendar_events, list):
            for event_child, event_unit in _child_contexts(value, child, unit):
                for event in calendar_events:
                    nested = _normalize_upcoming_event(event, child=event_child, unit=event_unit)
                    if nested is not None:
                        key = (id(event), event_child, event_unit)
                        if key not in seen:
                            seen.add(key)
                            yield nested

        for key_name, nested_value in value.items():
            if key_name in {"calendarEvent", "calendarEvents", "calendar_events", "event"}:
                continue
            yield from _extract_upcoming_events(nested_value, child=child, unit=unit, seen=seen)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _extract_upcoming_events(nested_value, child=child, unit=unit, seen=seen)


def _encoded_string_table(data):
    if not isinstance(data, list):
        return None, []
    string_table_index = next(
        (
            index
            for index, value in enumerate(data)
            if isinstance(value, list) and all(isinstance(item, str) for item in value)
        ),
        None,
    )
    if string_table_index is None:
        return None, []
    return string_table_index, data[string_table_index]


def _encoded_class_ref(strings, class_name):
    return next((index + 1 for index, value in enumerate(strings) if value.startswith(class_name)), None)


def _encoded_event_records(prefix, event_class, date_class, *, start=0, end=None):
    end = len(prefix) if end is None else end
    starts = [
        index
        for index in range(start, max(start, end - 2))
        if prefix[index : index + 3] == [0, event_class, 0]
    ]
    # The first TreeSet item is serialized without a repeated CalendarEvent class
    # marker when it immediately follows a HomeChild object.
    if start > 0:
        leading_end = starts[0] if starts else end
        leading_candidates = [
            index
            for index in range(start, leading_end)
            if prefix[index] == 0
            and _encoded_date(prefix, index + 1, date_class) is not None
            and _encoded_date(prefix, index + 5, date_class) is not None
        ]
        if leading_candidates:
            starts.insert(0, leading_candidates[-1])
    for position, record_start in enumerate(starts):
        record_end = starts[position + 1] if position + 1 < len(starts) else end
        yield prefix[record_start:record_end]


def _encoded_date(record, index, date_class):
    if index + 3 >= len(record) or record[index + 3] != date_class:
        return None
    return _normalize_event_date({"year": record[index], "month": record[index + 1], "day": record[index + 2]})


def _encoded_event_text(strings, record, date_class, integer_class, *, start=0):
    index = start
    while index < len(record):
        if _encoded_date(record, index, date_class) is not None:
            index += 4
            continue
        value = record[index]
        if (
            isinstance(value, int)
            and value > len(strings)
            and index + 1 < len(record)
            and record[index + 1] == integer_class
        ):
            return None
        if not isinstance(value, int) or value <= 0 or value > len(strings):
            index += 1
            continue
        text = _string_from_table(strings, value)
        if text is None or text.startswith(("java.", "se.", "[L")):
            index += 1
            continue
        return text
    return None


def _parse_encoded_event_record(record, strings, *, date_class, timestamp_class):
    if len(record) < 11:
        return None
    event_class = _encoded_class_ref(strings, "se.tempus.common.shared.wrapper.CalendarEvent/")
    date_offset = 3 if len(record) >= 3 and record[:3] == [0, event_class, 0] else 1
    # CalendarEvent serializes stopDate before startDate in the observed HomeService payload.
    stop_date = _encoded_date(record, date_offset, date_class)
    start_date = _encoded_date(record, date_offset + 4, date_class)
    if stop_date is None and start_date is None:
        return None
    if start_date is None:
        start_date = stop_date
    if stop_date is None:
        stop_date = start_date
    timestamp_index = next(
        (
            index
            for index, value in enumerate(record)
            if value == timestamp_class and index >= date_offset + 8 and index + 1 < len(record)
        ),
        None,
    )
    if timestamp_index is None:
        return None
    message = _human_string_from_table(strings, record[timestamp_index + 1])
    if message is None:
        return None
    event_id = None
    if timestamp_index + 3 < len(record) and record[timestamp_index + 2] == 0:
        candidate_id = record[timestamp_index + 3]
        if isinstance(candidate_id, int) and candidate_id > len(strings):
            event_id = candidate_id
    if event_id is None:
        return None
    scheduling_index = date_offset + 8
    scheduling_allowed = (
        record[scheduling_index]
        if len(record) > scheduling_index and record[scheduling_index] in (0, 1)
        else None
    )
    integer_class = _encoded_class_ref(strings, "java.lang.Integer/")
    description = _encoded_event_text(
        strings,
        record,
        date_class,
        integer_class,
        start=timestamp_index + 4,
    )
    return {
        "id": str(event_id),
        "message": message,
        "description": description or None,
        "start_date": start_date,
        "stop_date": stop_date,
        "scheduling_allowed": bool(scheduling_allowed) if scheduling_allowed is not None else None,
    }


def _encoded_child_contexts(prefix, strings, *, child_class, enrollment_class):
    contexts = []
    for marker in (
        index
        for index, value in enumerate(prefix)
        if value == child_class
    ):
        candidates = []
        for start in range(max(0, marker - 1000), max(0, marker - 3)):
            if prefix[start : start + 2] != [0, 0]:
                continue
            child_id = prefix[start + 2]
            name = _human_string_from_table(strings, prefix[start + 3])
            if isinstance(child_id, int) and child_id > len(strings) and name:
                candidates.append((start, name))
        if not candidates:
            continue
        start, child = candidates[-1]
        unit = None
        if enrollment_class is not None:
            for index in range(start, marker):
                if prefix[index] == enrollment_class and index + 1 < marker:
                    candidate_unit = _human_string_from_table(strings, prefix[index + 1])
                    if candidate_unit:
                        unit = candidate_unit
                        break
        if unit is None:
            for value in prefix[start:marker]:
                candidate_unit = _human_string_from_table(strings, value)
                if candidate_unit and re.match(r"^\d{2}\s+", candidate_unit):
                    unit = candidate_unit
                    break
        context = {"start": marker, "child": child, "unit": unit}
        if context not in contexts:
            contexts.append(context)
    return contexts


def _parse_encoded_upcoming_events(data):
    if not isinstance(data, list):
        return []
    string_table_index, strings = _encoded_string_table(data)
    if string_table_index is None:
        return []
    event_class = _encoded_class_ref(strings, "se.tempus.common.shared.wrapper.CalendarEvent/")
    date_class = _encoded_class_ref(strings, "se.tempus.common.date.DateOnly/")
    timestamp_class = _encoded_class_ref(strings, "java.sql.Timestamp/")
    child_class = _encoded_class_ref(strings, "se.tempus.common.shared.wrapper.HomeChild/")
    enrollment_class = _encoded_class_ref(strings, "se.tempus.common.shared.wrapper.Enrollment/")
    if event_class is None or date_class is None or timestamp_class is None:
        return []
    prefix = data[:string_table_index]
    rows = []
    contexts = (
        _encoded_child_contexts(
            prefix,
            strings,
            child_class=child_class,
            enrollment_class=enrollment_class,
        )
        if child_class is not None
        else []
    )
    if not contexts:
        contexts = [{"start": 0, "child": None, "unit": None}]
    for position, context in enumerate(contexts):
        end = contexts[position + 1]["start"] if position + 1 < len(contexts) else len(prefix)
        for record in _encoded_event_records(prefix, event_class, date_class, start=context["start"], end=end):
            event = _parse_encoded_event_record(
                record,
                strings,
                date_class=date_class,
                timestamp_class=timestamp_class,
            )
            if event is None:
                continue
            event["child"] = context["child"]
            event["unit"] = context["unit"]
            rows.append(event)
    return rows


def _has_upcoming_overview_shape(data):
    if isinstance(data, list):
        _, strings = _encoded_string_table(data)
        return any(value.startswith("se.limesaudio.tempushome.shared.wrappers.HomeOverviewData/") for value in strings)
    return any(
        "calendarEvents" in raw or "calendar_events" in raw
        for raw in _walk_dicts(data)
    )


def _string_from_table(strings, ref):
    if not isinstance(ref, int) or ref <= 0 or ref > len(strings):
        return None
    return strings[ref - 1]


def _human_string_from_table(strings, ref):
    value = _string_from_table(strings, ref)
    if not value or value.startswith(("java.", "se.", "[L")):
        return None
    return value


def _parse_encoded_pickups(data):
    if not isinstance(data, list):
        return []
    string_table_index = next(
        (
            index
            for index, value in enumerate(data)
            if isinstance(value, list) and all(isinstance(item, str) for item in value)
        ),
        None,
    )
    if string_table_index is None:
        return []

    strings = data[string_table_index]
    pickup_class = next(
        (index + 1 for index, value in enumerate(strings) if value.startswith("se.tempus.common.shared.wrapper.Pickup/")),
        None,
    )
    integer_class = next(
        (index + 1 for index, value in enumerate(strings) if value.startswith("java.lang.Integer/")),
        None,
    )
    if pickup_class is None or integer_class is None:
        return []

    records = []
    prefix = data[:string_table_index]
    if len(prefix) >= 3 and prefix[-2:] == [0, 1]:
        prefix = prefix[:-3]
    index = 0
    while index + 1 < len(prefix):
        if prefix[index] != 0 or prefix[index + 1] != 0:
            index += 1
            continue
        end = index + 2
        while end < len(prefix):
            if end + 1 < len(prefix) and prefix[end] == 0 and prefix[end + 1] == 0:
                break
            end += 1
        record = prefix[index + 2 : end]
        if pickup_class in record:
            record = record[: len(record) - list(reversed(record)).index(pickup_class)]
        if len(record) >= 6 and record[-1] == pickup_class:
            records.append(record)
        index = end

    pickups = []
    for record in records:
        phone = _string_from_table(strings, record[0])
        name = _string_from_table(strings, record[1])
        pickup_id = record[2] if isinstance(record[2], int) and record[2] > len(strings) else None
        children = []
        raw_children = []
        pickup_child_ids = []
        owner_name = _string_from_table(strings, record[3]) if len(record) > 3 else None
        for child_index in range(3, len(record) - 2):
            child_name = _string_from_table(strings, record[child_index])
            child_id = record[child_index + 1]
            if (
                child_name
                and not child_name.startswith(("java.", "se."))
                and isinstance(child_id, int)
                and record[child_index + 2] == integer_class
            ):
                children.append(child_name)
                raw_children.append({"name": child_name, "id": str(child_id)})
        for child_index in range(4, len(record) - 1):
            child_id = record[child_index]
            if isinstance(child_id, int) and record[child_index + 1] == integer_class:
                pickup_child_ids.append(str(child_id))
        pickup = {
            "id": str(pickup_id) if pickup_id is not None else None,
            "name": name,
            "phone": phone or None,
            "children": children,
            "_raw": {
                "encoded": record,
                "children": raw_children,
                "owner_name": owner_name,
                "pickup_child_ids": pickup_child_ids,
            },
        }
        if pickup["id"] or pickup["name"] or pickup["phone"]:
            pickups.append(pickup)
    return pickups


def parse_schemas(response):
    strings = _string_table(response)
    names = [s for s in strings if not s.startswith(("java.", "se.")) and not s.startswith("tempus-")]
    projects = [s for s in strings if s.startswith("tempus-")]
    # GWT scalar ids appear before string table in the observed response. Pair by reversed ids.
    prefix = response.split('["', 1)[0]
    nums = [int(n) for n in re.findall(r"\b\d+\b", prefix)]
    ids = list(reversed([n for n in nums if n not in (0,1,2,3,4,5,6,7,8,9,10,11,12,13,14)]))
    rows=[]
    for i, name in enumerate(names):
        rows.append({"id": ids[i] if i < len(ids) else None, "name": name, "project": projects[i] if i < len(projects) else None})
    return rows


def parse_identity_providers(response):
    strings = _string_table(response)
    useful = [s for s in strings if not s.startswith(("java.", "se."))]
    rows=[]
    for i, name in enumerate(useful):
        if i + 1 < len(useful):
            rows.append({"name": name, "option": useful[i+1]})
            break
    return rows


def parse_pickups(response):
    if not response.startswith("//OK"):
        raise RuntimeError("Tempus pickup response was not a successful GWT RPC response")
    data = _json_payload(response)
    if data is None:
        raise RuntimeError("Tempus pickup response could not be parsed")
    if data == []:
        return []

    pickups = []
    for raw in _walk_dicts(data):
        pickup = _normalize_pickup(raw)
        if pickup and pickup not in pickups:
            pickups.append(pickup)
    if not pickups:
        pickups = _parse_encoded_pickups(data)
    if not pickups:
        raise RuntimeError("Tempus pickup response did not contain recognized pickup data")
    return pickups


def parse_children_and_notifications(response):
    if not response.startswith("//OK"):
        raise RuntimeError("Tempus children response was not a successful GWT RPC response")
    data = _json_payload(response)
    if not isinstance(data, list):
        raise RuntimeError("Tempus children response could not be parsed")
    string_table_index = next(
        (
            index
            for index, value in enumerate(data)
            if isinstance(value, list) and all(isinstance(item, str) for item in value)
        ),
        None,
    )
    if string_table_index is None:
        raise RuntimeError("Tempus children response did not contain a string table")

    strings = data[string_table_index]
    child_class = next(
        (index + 1 for index, value in enumerate(strings) if value.startswith("se.tempus.common.shared.wrapper.Child/")),
        None,
    )
    if child_class is None:
        raise RuntimeError("Tempus children response did not contain child data")

    rows = []
    seen = set()
    prefix = data[:string_table_index]
    for index in range(0, max(0, len(prefix) - 4)):
        if prefix[index] != 0 or prefix[index + 1] != 0:
            continue
        child_id = prefix[index + 2]
        name_ref = prefix[index + 3]
        name = _string_from_table(strings, name_ref)
        if (
            not isinstance(child_id, int)
            or not name
            or name.startswith(("java.", "se.", "[L"))
            or child_class not in prefix[index + 4 : index + 12]
        ):
            continue
        key = (str(child_id), name)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"id": str(child_id), "name": name})
    if not rows:
        raise RuntimeError("Tempus children response did not contain recognized child rows")
    return rows


def parse_upcoming_events(response):
    if not response.startswith("//OK"):
        raise RuntimeError("Tempus upcoming events response was not a successful GWT RPC response")
    data = _json_payload(response)
    if data is None:
        raise RuntimeError("Tempus upcoming events response could not be parsed")
    if data == []:
        return []

    rows = list(_extract_upcoming_events(data))
    if not rows:
        rows = _parse_encoded_upcoming_events(data)
    if not rows:
        if _has_upcoming_overview_shape(data):
            return []
        raise RuntimeError("Tempus upcoming events response did not contain recognized event data")
    rows.sort(
        key=lambda row: (
            row.get("start_date") or "",
            row.get("stop_date") or "",
            row.get("child") or "",
            row.get("unit") or "",
            row.get("message") or "",
            row.get("id") or "",
        )
    )
    return rows


def parse_week_schedule_assignment(response, pickup_date, child_id):
    if not response.startswith("//OK"):
        raise RuntimeError("Tempus week schedule response was not a successful GWT RPC response")
    data = _json_payload(response)
    if not isinstance(data, list):
        raise RuntimeError("Tempus week schedule response could not be parsed")
    string_table_index = next(
        (
            index
            for index, value in enumerate(data)
            if isinstance(value, list) and all(isinstance(item, str) for item in value)
        ),
        None,
    )
    if string_table_index is None:
        raise RuntimeError("Tempus week schedule response did not contain a string table")

    prefix = data[:string_table_index]
    strings = data[string_table_index]
    try:
        requested = date.fromisoformat(pickup_date)
    except ValueError as exc:
        raise RuntimeError("Tempus week schedule parser requires YYYY-MM-DD date") from exc
    iso_year, iso_week, iso_weekday = requested.isocalendar()
    child_id_text = str(child_id)

    starts = [
        index
        for index in range(0, max(0, len(prefix) - 3))
        if prefix[index] == iso_year
        and prefix[index + 1] == iso_week
        and prefix[index + 2] == iso_weekday
    ]
    if not starts:
        raise RuntimeError("Tempus week schedule response did not contain requested date")

    date_start = starts[0]
    next_start = next(
        (
            index
            for index in range(date_start + 1, max(date_start + 1, len(prefix) - 3))
            if prefix[index] == iso_year
            and isinstance(prefix[index + 1], int)
            and 1 <= prefix[index + 2] <= 7
        ),
        len(prefix),
    )
    record = prefix[date_start:next_start]
    child_seen = any(str(value) == child_id_text for value in record)
    if not child_seen:
        raise RuntimeError("Tempus week schedule response did not contain requested child/date")
    time_class = next(
        (index + 1 for index, value in enumerate(strings) if value.startswith("se.tempus.common.date.TimeOnly/")),
        None,
    )
    pickup_class = next(
        (index + 1 for index, value in enumerate(strings) if value.startswith("se.tempus.common.shared.wrapper.Pickup/")),
        None,
    )
    schedule_id = None
    start_ms = None
    end_ms = None
    if time_class is not None:
        for index in range(4, max(4, len(record) - 4)):
            if record[index + 1] == time_class and record[index + 3] == time_class:
                end_ms = record[index]
                start_ms = record[index + 2]
                if isinstance(record[index + 4], int):
                    schedule_id = record[index + 4]
                break
    pickup_id = None
    if pickup_class in record:
        pickup_index = record.index(pickup_class)
        for index in range(max(0, pickup_index - 16), max(0, pickup_index - 3)):
            pickup_phone = _human_string_from_table(strings, record[index])
            pickup_name = _human_string_from_table(strings, record[index + 1])
            candidate_id = record[index + 2]
            owner = _human_string_from_table(strings, record[index + 3])
            if owner and pickup_name and pickup_phone and isinstance(candidate_id, int) and candidate_id > len(strings):
                pickup_id = str(candidate_id)
                break
    write_supported = schedule_id is not None and start_ms is not None and end_ms is not None

    return {
        "date": pickup_date,
        "child_id": child_id_text,
        "pickup_id": pickup_id,
        "assignment_id": None,
        "version": None,
        "write_token": None,
        "write_supported": write_supported,
        "block_reason": None if write_supported else "assignment_write_method_unavailable",
        "schedule_id": str(schedule_id) if schedule_id is not None else None,
        "start_ms": str(start_ms) if start_ms is not None else None,
        "end_ms": str(end_ms) if end_ms is not None else None,
    }


def parse_pickup_assignment(response):
    if not response.startswith("//OK"):
        raise RuntimeError("Tempus pickup assignment response was not a successful GWT RPC response")
    data = _json_payload(response)
    if data is None:
        raise RuntimeError("Tempus pickup assignment response could not be parsed")
    raw = None
    for item in _walk_dicts(data):
        if "assignment" in item and isinstance(item["assignment"], dict):
            raw = item["assignment"]
            break
        if {"date", "childId", "assignmentId"}.issubset(item):
            raw = item
            break
    if raw is None:
        raise RuntimeError("Tempus pickup assignment response did not contain recognized assignment data")
    assignment = _normalize_assignment(raw)
    if assignment is None:
        raise RuntimeError("Tempus pickup assignment response missed required assignment fields")
    return assignment


def parse_assignment_write_response(response):
    if not response.startswith("//OK"):
        raise RuntimeError("Tempus pickup assignment write response was not a successful GWT RPC response")
    if response.strip() == "//OK[]":
        return {"success": True}
    data = _json_payload(response)
    if data is None:
        raise RuntimeError("Tempus pickup assignment write response could not be parsed")
    raw = _first_dict(data)
    if raw is None:
        strings = next(
            (
                value
                for value in data
                if isinstance(value, list) and all(isinstance(item, str) for item in value)
            ),
            [],
        )
        if any(value.startswith("se.tempus.common.shared.wrapper.DaySchedule/") for value in strings):
            return {"success": True}
        raise RuntimeError("Tempus pickup assignment write response did not contain recognized result data")
    success = raw.get("success")
    if success is False:
        code = raw.get("errorCode") or "server_validation"
        message = raw.get("message") or "Tempus rejected pickup assignment"
        raise RuntimeError(f"Tempus pickup assignment write failed: {code}: {message}")
    if success is not True:
        raise RuntimeError("Tempus pickup assignment write response did not confirm success")
    return {
        "success": True,
        "assignment_id": str(raw["assignmentId"]) if raw.get("assignmentId") is not None else None,
        "version": str(raw["version"]) if raw.get("version") is not None else None,
    }
