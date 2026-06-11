import argparse
import json
from pathlib import Path

from .pickup_fixtures import (
    _entries_from_capture,
    _load_json,
    _load_replacements,
    _reject_repo_source,
    assert_sanitized_fixture,
)

FIXTURE_TYPE = "tempus_upcoming_events_capture"
FIXTURE_VERSION = 1
DEFAULT_OUTPUT_DIR = Path("tests/fixtures/upcoming_events")


def sanitize_upcoming_events_capture(raw_text, replacements=None):
    fixture = {
        "fixture_type": FIXTURE_TYPE,
        "version": FIXTURE_VERSION,
        "scope": "upcoming_events",
        "entries": _entries_from_capture(_load_json(raw_text), raw_text, dict(replacements or {})),
    }
    assert_sanitized_fixture(fixture)
    return fixture


def write_sanitized_fixture(raw_text, output_path, replacements=None):
    fixture = sanitize_upcoming_events_capture(raw_text, replacements=replacements)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return fixture


def build_parser():
    parser = argparse.ArgumentParser(description="Sanitize Tempus upcoming-events capture data.")
    parser.add_argument("--input", required=True, help="Raw capture file outside the repository")
    parser.add_argument("--output", required=True, help=f"Sanitized fixture path, usually under {DEFAULT_OUTPUT_DIR}")
    parser.add_argument("--replacements", required=True, help="JSON file outside the repository mapping real names to generated placeholders")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    input_path = _reject_repo_source(args.input, "--input")
    replacements_path = _reject_repo_source(args.replacements, "--replacements")
    raw_text = input_path.read_text(encoding="utf-8")
    replacements = _load_replacements(replacements_path)
    write_sanitized_fixture(raw_text, args.output, replacements=replacements)
    print(f"wrote sanitized fixture: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
