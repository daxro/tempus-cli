import argparse
from datetime import date
import json
import os
import re
import sys

import requests

from . import __version__
from .api import PICKUP_WRITES_DISABLED, TempusApi
from .errors import FrejaError, TempusError
from .paths import default_config_path, default_session_path
from .redact import redact_text
from .session import login, read_config_personnummer, resolve_personnummer, status_text, verify_authenticated
from .session_store import load_session_opt_in, save_session_opt_in

AREA_IDS = {"stockholm": 12}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tempus",
        description="Unofficial CLI for Tempus Home.",
        epilog="""examples:
  tempus status --json
  tempus schemas --area Stockholm --json
  tempus pickup --json
  TEMPUS_PERSONNUMMER=YYYYMMDDNNNN tempus setup --no-input

environment:
  TEMPUS_PERSONNUMMER  12-digit personal number used for Freja eID+ login

exit codes:
  0 success
  1 operational failure
  2 invalid or missing input
  130 interrupted""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"tempus {__version__}")
    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser(
        "status",
        help="Check local configuration and session status",
        description="Check local configuration and persisted-session status.",
    )
    status.add_argument("--json", dest="json_output", action="store_true", help="Output stable JSON")

    setup = sub.add_parser(
        "setup",
        help="Configure Freja login and save a local session",
        description="Verify Freja eID+ login, then save local config and session files.",
        epilog="""examples:
  tempus setup
  TEMPUS_PERSONNUMMER=YYYYMMDDNNNN tempus setup --no-input

safety:
  requires human approval in Freja eID+
  stores config and session outside the repository with 0600 permissions
  does not write Tempus data""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    setup.add_argument("-q", "--quiet", action="store_true", help="Suppress progress messages on stderr")
    setup.add_argument("--no-input", action="store_true", help="Disable prompts; require environment or saved config")
    setup.add_argument("--freja-timeout", type=float, default=180.0, help="Seconds to wait for Freja approval (default: 180)")

    schemas = sub.add_parser(
        "schemas",
        help="List public Tempus schemas",
        description="List public Tempus schemas for an area.",
    )
    schemas.add_argument("--area", default="Stockholm", help="Known area name (default: Stockholm)")
    schemas.add_argument("--area-id", type=int, help="Numeric area ID; overrides --area")
    schemas.add_argument("--json", dest="json_output", action="store_true", help="Output stable JSON")

    providers = sub.add_parser(
        "providers",
        help="List public login providers",
        description="List public login providers for a Tempus schema.",
    )
    providers.add_argument("--schema-id", type=int, default=399, help="Numeric schema ID (default: 399)")
    providers.add_argument("--json", dest="json_output", action="store_true", help="Output stable JSON")

    login_parser = sub.add_parser(
        "login",
        help="Verify Freja login without saving a session",
        description="Verify Freja eID+ login without saving config or session files.",
    )
    login_parser.add_argument("--no-input", action="store_true", help="Disable prompts; require environment or saved config")
    login_parser.add_argument("--freja-timeout", type=float, default=180.0, help="Seconds to wait for Freja approval (default: 180)")

    pickup = sub.add_parser(
        "pickup",
        help="List or preview guarded pickup contact changes",
        description="List pickup contacts or preview guarded pickup contact changes.",
        epilog="""examples:
  tempus pickup
  tempus pickup --child CHILD_NAME --json
  tempus pickup --child CHILD_NAME --name "Example Guardian" --phone "0700000000" --json
  tempus pickup --date YYYY-MM-DD --child CHILD_NAME --id PICKUP_ID --json
  tempus pickup --date YYYY-MM-DD --child CHILD_NAME --name "Example Guardian" --json

safety:
  default mode is read-only preview
  writes require --apply --confirm after fixture-backed enablement
  remove also requires --name EXACT_CURRENT_NAME""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    pickup.add_argument("--json", dest="json_output", action="store_true", help="Output stable JSON")
    pickup.add_argument("--no-input", action="store_true", help="Disable prompts; require saved session or environment")
    pickup.add_argument("--date", help="Assign pickup for this local Tempus date (YYYY-MM-DD)")
    pickup.add_argument("--child", help="Filter or assign to this child name")
    pickup.add_argument("--id", dest="pickup_id", help="Pickup contact ID for update, remove, or date assignment")
    pickup.add_argument("--name", help="Pickup contact name")
    pickup.add_argument("--phone", help="Pickup contact phone number")
    pickup.add_argument("--remove", action="store_true", help="Preview removing an existing pickup contact")
    pickup.add_argument("--apply", action="store_true", help="Apply the previewed pickup change after safety checks")
    pickup.add_argument("--confirm", action="store_true", help="Required together with --apply")

    return parser


def _print_json(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _write_config_personnummer(personnummer, path=None):
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(f"TEMPUS_PERSONNUMMER={personnummer}\n")
    os.chmod(path, 0o600)


def _status_dict(config_path=None, session_path=None):
    config_path = config_path or default_config_path()
    session_path = session_path or default_session_path()
    status = {
        "configured": bool(read_config_personnummer(config_path)),
        "session": "none",
        "authenticated": False,
        "reason": None,
        "config_path": str(config_path),
        "session_path": str(session_path),
    }
    if not session_path.exists():
        return status
    session = TempusApi().session
    if not load_session_opt_in(session, session_path):
        status["session"] = "unreadable"
        return status
    status["session"] = "persisted"
    try:
        verify_authenticated(session)
        status["authenticated"] = True
    except Exception as exc:
        status["reason"] = redact_text(str(exc))
    return status


def _print_status(status):
    print(f"configured: {'yes' if status['configured'] else 'no'}")
    print(f"config: {status['config_path']}")
    print(f"session: {status['session']}")
    print(f"session_path: {status['session_path']}")
    print(f"authenticated: {'yes' if status['authenticated'] else 'no'}")
    if status["reason"]:
        print(f"reason: {status['reason']}")


def _public_pickup(pickup):
    return {
        "id": pickup.get("id"),
        "name": pickup.get("name"),
        "phone": pickup.get("phone"),
        "children": list(pickup.get("children") or []),
    }


def _child_matches(pickup, child):
    if child is None:
        return True
    child_lower = child.lower()
    return any(child_lower in str(name).lower() for name in pickup.get("children") or [])


def _print_pickups(pickups):
    if not pickups:
        print("No pickup contacts found.")
        return
    for pickup in pickups:
        children = ", ".join(pickup.get("children") or [])
        suffix = f" ({children})" if children else ""
        phone = f" {pickup.get('phone')}" if pickup.get("phone") else ""
        print(f"{pickup.get('id')}: {pickup.get('name')}{phone}{suffix}")


def _get_authenticated_api(no_input=False):
    api = TempusApi()
    if load_session_opt_in(api.session, default_session_path()):
        return api
    personnummer = resolve_personnummer(allow_prompt=not no_input)
    session = login(personnummer=personnummer, allow_prompt=False)
    return TempusApi(session=session)


def _validate_pickup_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value) or int(value) <= 0:
        raise ValueError("--id must be a positive ASCII decimal ID")
    return value


def _validate_non_empty(value, flag):
    value = "" if value is None else value.strip()
    if not value:
        raise ValueError(f"{flag} must not be empty")
    return value


def _validate_pickup_date(value):
    value = _validate_non_empty(value, "--date")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("--date must be a valid YYYY-MM-DD date") from exc


def _pickup_operation(args):
    if args.date is not None:
        _validate_pickup_date(args.date)
        _validate_non_empty(args.child, "--child")
        if args.remove:
            raise ValueError("--date cannot be combined with --remove")
        if args.phone is not None:
            raise ValueError("--date cannot be combined with --phone until contact-create fixtures prove required fields")
        if args.pickup_id and args.name is not None:
            raise ValueError("--date requires either --id or --name, not both")
        if args.pickup_id:
            _validate_pickup_id(args.pickup_id)
        elif args.name is not None:
            _validate_non_empty(args.name, "--name")
        else:
            raise ValueError("--date requires --id or --name")
        return "assign"

    has_change = args.name is not None or args.phone is not None
    if args.remove:
        if not args.pickup_id:
            raise ValueError("--remove requires --id")
        _validate_pickup_id(args.pickup_id)
        if args.phone is not None or args.child is not None:
            raise ValueError("--remove cannot be combined with --phone or --child")
        if args.apply:
            _validate_non_empty(args.name, "--name")
        return "remove"
    if args.pickup_id:
        _validate_pickup_id(args.pickup_id)
        if not has_change and args.child is None:
            raise ValueError("--id requires --name, --phone, --child, or --remove")
        return "update"
    if has_change:
        _validate_non_empty(args.child, "--child")
        _validate_non_empty(args.name, "--name")
        _validate_non_empty(args.phone, "--phone")
        return "create"
    return "list"


def _validate_pickup_args(args):
    operation = _pickup_operation(args)
    if args.apply and operation == "list":
        raise ValueError("--apply requires a pickup change")
    if args.confirm and not args.apply:
        raise ValueError("--confirm requires --apply")
    if args.apply and not args.confirm:
        raise ValueError("--apply requires --confirm")
    if operation == "update" and args.name is not None:
        _validate_non_empty(args.name, "--name")
    if operation == "update" and args.phone is not None:
        _validate_non_empty(args.phone, "--phone")
    if operation == "update" and args.child is not None:
        _validate_non_empty(args.child, "--child")
    return operation


def _find_pickup(pickups, pickup_id):
    matches = [pickup for pickup in pickups if str(pickup.get("id")) == str(pickup_id)]
    if not matches:
        raise RuntimeError(f"pickup contact {pickup_id} not found")
    if len(matches) > 1:
        raise RuntimeError(f"pickup contact {pickup_id} matched multiple records")
    return matches[0]


def _find_pickup_by_name(pickups, name):
    name = _validate_non_empty(name, "--name")
    matches = [pickup for pickup in pickups if str(pickup.get("name") or "") == name]
    if not matches:
        raise ValueError(
            f"pickup contact named '{name}' not found; contact creation requires sanitized Tempus write fixtures"
        )
    if len(matches) > 1:
        raise ValueError(f"pickup contact name '{name}' matched multiple records; use --id")
    return matches[0]


def _assignment_preview(args, pickups):
    pickup = _find_pickup(pickups, args.pickup_id) if args.pickup_id else _find_pickup_by_name(pickups, args.name)
    contact = _public_pickup(pickup)
    child_name = _validate_non_empty(args.child, "--child")
    pickup_date = _validate_pickup_date(args.date)
    return {
        "mode": "preview",
        "operation": "assign",
        "date": pickup_date,
        "child": {"name": child_name, "id": None},
        "contact": {
            "id": contact.get("id"),
            "name": contact.get("name"),
            "phone": contact.get("phone"),
        },
        "existing_assignment": None,
        "proposed_assignment": {
            "date": pickup_date,
            "child_id": None,
            "pickup_id": contact.get("id"),
        },
        "contact_write": None,
        "assignment_write": {"required": True},
        "write_performed": False,
        "would_write_if_applied": False,
        "blocked": True,
        "block_reason": "date_assignment_read_unavailable",
    }


def _pickup_preview(operation, args, pickups):
    if operation == "assign":
        return _assignment_preview(args, pickups)

    if operation == "create":
        proposed = {
            "id": None,
            "name": _validate_non_empty(args.name, "--name"),
            "phone": _validate_non_empty(args.phone, "--phone"),
            "children": [_validate_non_empty(args.child, "--child")],
        }
        return {
            "mode": "preview",
            "operation": operation,
            "existing_pickup": None,
            "proposed_pickup": proposed,
            "write_performed": False,
            "would_write_if_applied": True,
            "blocked": False,
        }

    existing = _public_pickup(_find_pickup(pickups, args.pickup_id))
    if operation == "remove":
        blocked = args.name is not None and args.name != existing.get("name")
        result = {
            "mode": "preview",
            "operation": operation,
            "existing_pickup": existing,
            "proposed_pickup": None,
            "write_performed": False,
            "would_write_if_applied": not blocked,
            "blocked": blocked,
        }
        if blocked:
            result["block_reason"] = "name_confirmation_does_not_match"
        return result

    proposed = dict(existing)
    if args.name is not None:
        proposed["name"] = _validate_non_empty(args.name, "--name")
    if args.phone is not None:
        proposed["phone"] = _validate_non_empty(args.phone, "--phone")
    if args.child is not None:
        proposed["children"] = [_validate_non_empty(args.child, "--child")]
    changed = proposed != existing
    return {
        "mode": "preview",
        "operation": operation,
        "existing_pickup": existing,
        "proposed_pickup": proposed,
        "write_performed": False,
        "would_write_if_applied": changed,
        "blocked": False,
    }


def _pickup(args):
    operation = _validate_pickup_args(args)
    if args.apply:
        raise RuntimeError(PICKUP_WRITES_DISABLED)

    api = _get_authenticated_api(no_input=args.no_input)
    pickups = api.pickups()
    if operation == "list":
        rows = [_public_pickup(pickup) for pickup in pickups if _child_matches(pickup, args.child)]
        if args.child and not rows:
            raise RuntimeError(f"no pickup contacts matching child '{args.child}'")
        if args.json_output:
            _print_json(rows)
        else:
            _print_pickups(rows)
        return 0

    preview = _pickup_preview(operation, args, pickups)
    if args.json_output:
        _print_json(preview)
    else:
        print(f"{operation}: preview")
        if preview.get("existing_pickup"):
            print(f"existing: {preview['existing_pickup']}")
        if preview.get("proposed_pickup"):
            print(f"proposed: {preview['proposed_pickup']}")
        if preview.get("proposed_assignment"):
            print(f"proposed: {preview['proposed_assignment']}")
        if preview.get("blocked"):
            print(f"blocked: {preview.get('block_reason')}")
    return 0


def _setup(args):
    personnummer = resolve_personnummer(allow_prompt=not args.no_input)
    session = login(
        personnummer=personnummer,
        quiet=args.quiet,
        freja_timeout=args.freja_timeout,
        allow_prompt=False,
    )
    _write_config_personnummer(personnummer)
    save_session_opt_in(session, default_session_path())
    if not args.quiet:
        print("Authenticated and saved local session.", file=sys.stderr)
    print(status_text())


def _run_command(parser, args):
    if args.command == "status":
        status = _status_dict()
        if args.json_output:
            _print_json(status)
        else:
            _print_status(status)
        return 0

    if args.command == "setup":
        _setup(args)
        return 0

    if args.command == "schemas":
        area_id = args.area_id or AREA_IDS.get(args.area.lower())
        if not area_id:
            raise ValueError("unknown area; use --area-id")
        rows = [
            {"id": row.get("id"), "name": row.get("name"), "project": row.get("project")}
            for row in TempusApi().schemas(area_id)
        ]
        if args.json_output:
            _print_json(rows)
        else:
            for row in rows:
                print(f"{row.get('id')}: {row.get('name')} ({row.get('project')})")
        return 0

    if args.command == "providers":
        rows = [
            {"name": row.get("name"), "option": row.get("option")}
            for row in TempusApi().identity_providers(args.schema_id)
        ]
        if args.json_output:
            _print_json(rows)
        else:
            for row in rows:
                print(f"{row.get('name')}: {row.get('option')}")
        return 0

    if args.command == "login":
        personnummer = resolve_personnummer(allow_prompt=not args.no_input)
        login(personnummer=personnummer, freja_timeout=args.freja_timeout, allow_prompt=False)
        print("Login verified. Session was not saved.")
        return 0

    if args.command == "pickup":
        return _pickup(args)

    parser.print_help()
    return 0


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)

    try:
        return _run_command(parser, args)
    except (ValueError, EOFError) as exc:
        message = redact_text(str(exc)) or "invalid input"
        print(f"Error: {message}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except FrejaError as exc:
        message = redact_text(str(exc)) or "Freja authentication failed"
        print(f"Error: {message}", file=sys.stderr)
        return 1
    except requests.exceptions.RequestException as exc:
        message = redact_text(str(exc)) or exc.__class__.__name__
        print(f"Error: {message}", file=sys.stderr)
        return 1
    except (TempusError, RuntimeError, OSError) as exc:
        message = redact_text(str(exc)) or exc.__class__.__name__
        print(f"Error: {message}", file=sys.stderr)
        return 1
    except Exception as exc:
        message = redact_text(str(exc)) or exc.__class__.__name__
        print(f"Error: unexpected failure: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
