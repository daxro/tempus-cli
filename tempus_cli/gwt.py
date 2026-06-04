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


def noarg_rpc_payload(permutation, method):
    return f"7|0|4|{GWT_MODULE_BASE}|{permutation}|{HOME_SERVICE}|{method}|1|2|3|4|0|"


def payload_get_schemas(permutation, area_id):
    return int_rpc_payload(permutation, "getSchemas", area_id)


def payload_get_applyable_schemas(permutation):
    return noarg_rpc_payload(permutation, "getApplyableSchemas")


def payload_get_grand_id_identity_providers(permutation, schema_id):
    return int_rpc_payload(permutation, "getGrandIdIdentityProviders", schema_id)


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
