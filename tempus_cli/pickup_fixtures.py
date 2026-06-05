import argparse
import json
import re
from pathlib import Path

from .redact import redact_text, redact_url
from .transport import rpc_method_from_payload

FIXTURE_TYPE = "tempus_pickup_date_assignment_capture"
FIXTURE_VERSION = 1
DEFAULT_OUTPUT_DIR = Path("tests/fixtures/pickup_date_assignment")

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-xsrf-token",
    "xsrf-token",
}

SENSITIVE_RE = re.compile(
    r"(?<!\d)(?:\d{8}[-+]?\d{4}|\d{6}[-+]?\d{4})(?!\d)|"
    r"(?<![A-Za-z0-9+/=_-])(?:[A-Fa-f0-9]{32,}|[A-Za-z0-9+/=_-]{40,})(?![A-Za-z0-9+/=_-])"
)


def _load_json(text):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _load_replacements(path):
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "replacements" in data:
        items = data["replacements"]
    elif isinstance(data, dict):
        items = [{"actual": actual, "placeholder": placeholder} for actual, placeholder in data.items()]
    else:
        items = data
    replacements = {}
    for item in items:
        actual = str(item.get("actual", ""))
        placeholder = str(item.get("placeholder", ""))
        if not actual or not placeholder:
            raise ValueError("replacement entries require actual and placeholder values")
        replacements[actual] = placeholder
    return replacements


def _apply_replacements(text, replacements):
    for actual, placeholder in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        text = text.replace(actual, placeholder)
    return text


def _sanitize_text(value, replacements):
    text = str(value)
    text = _apply_replacements(text, replacements)
    return redact_text(text)


def _sanitize_url(value, replacements):
    return redact_url(_sanitize_text(value, replacements))


def _sanitize_headers(headers, replacements):
    rows = []
    if isinstance(headers, dict):
        iterable = headers.items()
    else:
        iterable = [(row.get("name"), row.get("value")) for row in headers or [] if isinstance(row, dict)]
    for name, value in iterable:
        if not name:
            continue
        if str(name).lower() in SENSITIVE_HEADER_NAMES:
            rows.append({"name": str(name), "value": "[REDACTED]"})
        else:
            rows.append({"name": str(name), "value": _sanitize_text(value, replacements)})
    return rows


def _entry_from_har(entry, replacements):
    request = entry.get("request") or {}
    response = entry.get("response") or {}
    post_text = ((request.get("postData") or {}).get("text")) or ""
    response_text = (((response.get("content") or {}).get("text"))) or ""
    return {
        "request": {
            "method": _sanitize_text(request.get("method", ""), replacements),
            "url": _sanitize_url(request.get("url", ""), replacements),
            "headers": _sanitize_headers(request.get("headers"), replacements),
            "body": _sanitize_text(post_text, replacements),
            "gwt_rpc_method": rpc_method_from_payload(post_text),
        },
        "response": {
            "status": response.get("status"),
            "headers": _sanitize_headers(response.get("headers"), replacements),
            "body": _sanitize_text(response_text, replacements),
        },
    }


def _entries_from_capture(data, raw_text, replacements):
    if isinstance(data, dict) and isinstance(data.get("log"), dict):
        entries = data["log"].get("entries") or []
        return [_entry_from_har(entry, replacements) for entry in entries if isinstance(entry, dict)]
    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        return [
            {
                "raw": _sanitize_text(json.dumps(entry, ensure_ascii=False, sort_keys=True), replacements),
            }
            for entry in data["entries"]
        ]
    return [{"raw": _sanitize_text(raw_text, replacements)}]


def sanitize_pickup_assignment_capture(raw_text, replacements=None):
    replacements = dict(replacements or {})
    data = _load_json(raw_text)
    fixture = {
        "fixture_type": FIXTURE_TYPE,
        "version": FIXTURE_VERSION,
        "scope": "pickup_date_assignment",
        "entries": _entries_from_capture(data, raw_text, replacements),
        "write_enablement": {
            "enabled": False,
            "reason": "requires human review of sanitized date-assignment fixtures before payload code is added",
        },
    }
    assert_sanitized_fixture(fixture)
    return fixture


def assert_sanitized_fixture(fixture):
    text = json.dumps(fixture, ensure_ascii=False, sort_keys=True)
    if SENSITIVE_RE.search(text):
        raise ValueError("sanitized fixture still contains sensitive-looking identifier or token")
    for header in re.finditer(r'"name":\s*"(Authorization|Cookie|Set-Cookie|X-XSRF-Token|XSRF-Token)"', text, re.I):
        start = max(0, header.start() - 120)
        end = min(len(text), header.end() + 120)
        if "[REDACTED]" not in text[start:end]:
            raise ValueError("sanitized fixture still contains sensitive header value")
    return fixture


def write_sanitized_fixture(raw_text, output_path, replacements=None):
    fixture = sanitize_pickup_assignment_capture(raw_text, replacements=replacements)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return fixture


def build_parser():
    parser = argparse.ArgumentParser(description="Sanitize Tempus pickup date-assignment capture data.")
    parser.add_argument("--input", required=True, help="Raw capture file outside the repository")
    parser.add_argument("--output", required=True, help=f"Sanitized fixture path, usually under {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--replacements", help="JSON file mapping real names to generated placeholders")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    raw_text = Path(args.input).read_text(encoding="utf-8")
    replacements = _load_replacements(args.replacements)
    write_sanitized_fixture(raw_text, args.output, replacements=replacements)
    print(f"wrote sanitized fixture: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
