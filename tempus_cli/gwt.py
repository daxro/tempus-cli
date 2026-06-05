import json
import re

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
    m = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


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


def _string_from_table(strings, ref):
    if not isinstance(ref, int) or ref <= 0 or ref > len(strings):
        return None
    return strings[ref - 1]


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
        for child_index in range(3, len(record) - 2):
            child_name = _string_from_table(strings, record[child_index])
            if (
                child_name
                and not child_name.startswith(("java.", "se."))
                and isinstance(record[child_index + 1], int)
                and record[child_index + 2] == integer_class
            ):
                children.append(child_name)
        pickup = {
            "id": str(pickup_id) if pickup_id is not None else None,
            "name": name,
            "phone": phone or None,
            "children": children,
            "_raw": {"encoded": record},
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
