import argparse
from datetime import date
import getpass
import json
import os
import re
import sys
import tempfile

import requests

from . import __version__
from .api import PICKUP_CONTACT_WRITES_DISABLED, TempusApi
from .errors import FrejaError, TempusError
from .paths import default_config_path, default_session_path
from .redact import redact_text
from .session import (
    login,
    read_config_personnummer,
    resolve_personnummer,
    status_text,
    validate_personnummer,
    verify_authenticated,
)
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
  tempus setup --personnummer YYYYMMDDNNNN

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
  tempus setup --personnummer YYYYMMDDNNNN

safety:
  requires human approval in Freja eID+
  stores config and session outside the repository with 0600 permissions
  does not write Tempus data""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    setup.add_argument("-q", "--quiet", action="store_true", help="Suppress progress messages on stderr")
    setup.add_argument("--personnummer", help="Personnummer to use for setup")
    setup.add_argument("--no-input", action="store_true", help="Disable prompts; require environment or --personnummer")
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
        help="List contacts, read date pickups, or preview guarded pickup changes",
        description="List pickup contacts, read date-specific pickup assignments, or preview guarded pickup changes.",
        epilog="""examples:
  tempus pickup
  tempus pickup --child CHILD_NAME --json
  tempus pickup --date YYYY-MM-DD --child CHILD_NAME --json
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
    pickup.add_argument("--date", help="Read or assign pickup for this local Tempus date (YYYY-MM-DD)")
    pickup.add_argument("--child", help="Filter contacts or read/assign this child name")
    pickup.add_argument("--id", dest="pickup_id", help="Pickup contact ID for update, remove, or date assignment")
    pickup.add_argument("--name", help="Pickup contact name")
    pickup.add_argument("--phone", help="Pickup contact phone number")
    pickup.add_argument("--remove", action="store_true", help="Preview removing an existing pickup contact")
    pickup.add_argument("--apply", action="store_true", help="Apply the previewed pickup change after safety checks")
    pickup.add_argument("--confirm", action="store_true", help="Required together with --apply")

    return parser


def _print_json(value):
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def _public_result(value):
    if isinstance(value, dict):
        return {key: _public_result(item) for key, item in value.items() if not key.startswith("_")}
    if isinstance(value, list):
        return [_public_result(item) for item in value]
    return value


def _write_private_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        os.fchmod(file.fileno(), 0o600)
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass


def _write_config_personnummer(personnummer, path=None):
    path = path or default_config_path()
    _write_private_text(path, f"TEMPUS_PERSONNUMMER={personnummer}\n")


def _persist_setup_state(personnummer, session):
    config_path = default_config_path()
    session_path = default_session_path()
    previous_config = config_path.read_text() if config_path.exists() else None
    try:
        _write_config_personnummer(personnummer, config_path)
        save_session_opt_in(session, session_path)
    except Exception:
        if previous_config is None:
            config_path.unlink(missing_ok=True)
        else:
            _write_private_text(config_path, previous_config)
        raise


def _resolve_setup_personnummer(personnummer=None, *, no_input=False):
    if personnummer is None and (no_input or not sys.stdin.isatty()):
        personnummer = os.environ.get("TEMPUS_PERSONNUMMER")
        if not personnummer:
            raise ValueError("TEMPUS_PERSONNUMMER is required when input is non-interactive")
    if personnummer is None:
        personnummer = getpass.getpass("Personal number for Freja (hidden): ").strip()
    return validate_personnummer(personnummer)


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


def _public_assignment(assignment):
    if assignment is None:
        return None
    return {
        "date": assignment.get("date"),
        "child_id": assignment.get("child_id"),
        "pickup_id": assignment.get("pickup_id"),
        "assignment_id": assignment.get("assignment_id"),
        "version": assignment.get("version"),
        "write_token_present": bool(assignment.get("write_token")),
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
            return "read_assignment"
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
    if args.apply and operation == "read_assignment":
        raise ValueError("--apply requires --id or --name")
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
        raise ValueError(f"pickup contact {pickup_id} not found")
    if len(matches) > 1:
        raise ValueError(f"pickup contact {pickup_id} matched multiple records")
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


def _find_pickup_optional(pickups, pickup_id):
    if pickup_id is None:
        return None
    matches = [pickup for pickup in pickups if str(pickup.get("id")) == str(pickup_id)]
    if len(matches) == 1:
        return matches[0]
    return None


def _child_rows_from_raw(raw):
    values = []
    if not isinstance(raw, dict):
        return values
    for key in ("children", "child", "homeChildren"):
        child_value = raw.get(key)
        if isinstance(child_value, dict):
            values.append(child_value)
        elif isinstance(child_value, list):
            values.extend(item for item in child_value if isinstance(item, dict))
    return values


def _child_id_matches_from_pickups(pickups, child_name):
    wanted = _validate_non_empty(child_name, "--child")
    wanted_lower = wanted.lower()
    exact_matches = set()
    partial_matches = set()
    for pickup in pickups:
        raw = pickup.get("_raw") or {}
        for child in _child_rows_from_raw(raw):
            name = child.get("name") or child.get("displayName") or child.get("fullName")
            child_id = child.get("id") or child.get("childId") or child.get("homeChildId")
            normalized_name = str(name or "").strip()
            if not normalized_name or child_id is None:
                continue
            if normalized_name.lower() == wanted_lower:
                exact_matches.add(str(child_id))
            elif wanted_lower in normalized_name.lower():
                partial_matches.add(str(child_id))
    return exact_matches or partial_matches


def _child_id_matches_from_directory(children, child_name):
    wanted = _validate_non_empty(child_name, "--child")
    wanted_lower = wanted.lower()
    exact_matches = {
        str(child["id"])
        for child in children
        if str(child.get("name") or "").strip().lower() == wanted_lower and child.get("id") is not None
    }
    if exact_matches:
        return exact_matches
    return {
        str(child["id"])
        for child in children
        if wanted_lower in str(child.get("name") or "").strip().lower() and child.get("id") is not None
    }


def _resolve_child_id(api, pickups, child_name):
    wanted = _validate_non_empty(child_name, "--child")
    matches = _child_id_matches_from_pickups(pickups, wanted)
    if not matches:
        matches = _child_id_matches_from_directory(api.children_and_notifications(), wanted)
    if not matches:
        raise ValueError(f"child '{wanted}' did not resolve to a fixture-proven server ID")
    if len(matches) > 1:
        raise ValueError(f"child '{wanted}' matched multiple server IDs")
    return next(iter(matches))


def _assignment_write_fields(assignment, pickup):
    raw = pickup.get("_raw") or {}
    owner_name = raw.get("owner_name")
    if not owner_name:
        raise ValueError("pickup assignment missed required owner field")
    return {
        "date": assignment["date"],
        "child_id": assignment["child_id"],
        "pickup_id": str(pickup["id"]),
        "pickup_name": pickup["name"],
        "pickup_phone": pickup["phone"] or "",
        "owner_name": owner_name,
        "pickup_child_ids": raw.get("pickup_child_ids") or [assignment["child_id"]],
        "schedule_id": assignment["schedule_id"],
        "start_ms": assignment["start_ms"],
        "end_ms": assignment["end_ms"],
    }


def _assignment_preview(args, pickups, api):
    pickup = _find_pickup(pickups, args.pickup_id) if args.pickup_id else _find_pickup_by_name(pickups, args.name)
    contact = _public_pickup(pickup)
    child_name = _validate_non_empty(args.child, "--child")
    child_id = _resolve_child_id(api, pickups, child_name)
    pickup_date = _validate_pickup_date(args.date)
    assignment = api.pickup_assignment(pickup_date, child_id)
    if assignment.get("date") != pickup_date or assignment.get("child_id") != child_id:
        raise ValueError("pickup assignment read did not match requested child/date")
    existing = _public_assignment(assignment)
    proposed = dict(existing)
    proposed["pickup_id"] = contact.get("id")
    changed = existing.get("pickup_id") != contact.get("id")
    block_reason = assignment.get("block_reason")
    blocked = bool(block_reason)
    return {
        "mode": "preview",
        "operation": "assign",
        "date": pickup_date,
        "child": {"name": child_name, "id": child_id},
        "contact": {
            "id": contact.get("id"),
            "name": contact.get("name"),
            "phone": contact.get("phone"),
        },
        "existing_assignment": existing,
        "proposed_assignment": proposed,
        "contact_write": None,
        "assignment_write": {
            "required": True,
            "method": "updateSchedule",
            "required_fields": [
                "date",
                "child_id",
                "pickup_id",
                "pickup_name",
                "pickup_phone",
                "owner_name",
                "pickup_child_ids",
                "schedule_id",
                "start_ms",
                "end_ms",
            ],
            "blocked": blocked,
            "block_reason": block_reason,
        },
        "_contact_state": pickup,
        "_assignment_state": assignment,
        "write_performed": False,
        "would_write_if_applied": changed and not blocked,
        "blocked": blocked,
        "block_reason": block_reason or ("no_op" if not changed else None),
    }


def _assignment_read_preview(args, pickups, api):
    child_name = _validate_non_empty(args.child, "--child")
    child_id = _resolve_child_id(api, pickups, child_name)
    pickup_date = _validate_pickup_date(args.date)
    assignment = api.pickup_assignment(pickup_date, child_id)
    if assignment.get("date") != pickup_date or assignment.get("child_id") != child_id:
        raise ValueError("pickup assignment read did not match requested child/date")
    existing = _public_assignment(assignment)
    pickup = _find_pickup_optional(pickups, existing.get("pickup_id"))
    return {
        "mode": "preview",
        "operation": "read_assignment",
        "date": pickup_date,
        "child": {"name": child_name, "id": child_id},
        "pickup": _public_pickup(pickup) if pickup else None,
        "existing_assignment": existing,
        "_assignment_state": assignment,
        "write_performed": False,
        "would_write_if_applied": False,
        "blocked": False,
        "block_reason": None if pickup else "no_pickup_assigned",
    }


def _pickup_preview(operation, args, pickups, api=None):
    if operation == "assign":
        return _assignment_preview(args, pickups, api)
    if operation == "read_assignment":
        return _assignment_read_preview(args, pickups, api)

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


def _preview_assumptions(preview):
    assignment = preview["_assignment_state"]
    return {
        "contact_id": preview["contact"]["id"],
        "child_id": preview["child"]["id"],
        "existing_assignment": {
            "date": assignment["date"],
            "child_id": assignment["child_id"],
            "pickup_id": assignment["pickup_id"],
            "schedule_id": assignment["schedule_id"],
            "start_ms": assignment["start_ms"],
            "end_ms": assignment["end_ms"],
        },
    }


def _apply_assignment(args, api, preview):
    if preview.get("blocked"):
        raise ValueError(f"pickup assignment is blocked: {preview.get('block_reason')}")
    if not preview.get("_assignment_state", {}).get("write_supported"):
        raise ValueError(PICKUP_WRITES_DISABLED)
    if not preview.get("would_write_if_applied"):
        raise ValueError("pickup assignment is already in requested state")

    before = _preview_assumptions(preview)
    reread_pickups = api.pickups()
    reread = _assignment_preview(args, reread_pickups, api)
    after_reread = _preview_assumptions(reread)
    if after_reread != before:
        raise ValueError("pickup assignment preview assumptions changed; re-run preview")

    write_payload = _assignment_write_fields(reread["_assignment_state"], reread["_contact_state"])
    write_result = api.assign_pickup(write_payload)
    result = dict(reread)
    result["mode"] = "apply"
    result["write_performed"] = True
    result["write_result"] = write_result
    try:
        verified = api.pickup_assignment(reread["date"], reread["child"]["id"])
    except (TempusError, RuntimeError, OSError, requests.exceptions.RequestException) as exc:
        result["verification"] = {"matched": False, "error": str(exc)}
        return 1, result

    verified_public = _public_assignment(verified)
    result["verified_assignment"] = verified_public
    matched = (
        verified_public.get("date") == reread["date"]
        and verified_public.get("child_id") == reread["child"]["id"]
        and verified_public.get("pickup_id") == reread["contact"]["id"]
    )
    result["verification"] = {"matched": matched}
    if not matched:
        return 1, result
    result["existing_assignment"] = verified_public
    result["proposed_assignment"] = verified_public
    result["would_write_if_applied"] = False
    result["blocked"] = False
    result["block_reason"] = None
    return 0, result


def _pickup(args):
    operation = _validate_pickup_args(args)
    if args.apply and operation != "assign":
        raise ValueError(PICKUP_CONTACT_WRITES_DISABLED)

    api = _get_authenticated_api(no_input=args.no_input)
    pickups = api.pickups()
    if operation == "list":
        rows = [_public_pickup(pickup) for pickup in pickups if _child_matches(pickup, args.child)]
        if args.child and not rows:
            raise RuntimeError(
                f"no pickup contacts matching child '{args.child}'; "
                "to check who picks up on a date, use --date YYYY-MM-DD --child CHILD_NAME --json"
            )
        if args.json_output:
            _print_json(rows)
        else:
            _print_pickups(rows)
        return 0

    preview = _pickup_preview(operation, args, pickups, api=api)
    exit_code = 0
    if args.apply:
        exit_code, preview = _apply_assignment(args, api, preview)
    if args.json_output:
        _print_json(_public_result(preview))
    else:
        print(f"{operation}: {preview['mode']}")
        if preview.get("existing_pickup"):
            print(f"existing: {preview['existing_pickup']}")
        if preview.get("proposed_pickup"):
            print(f"proposed: {preview['proposed_pickup']}")
        if preview.get("existing_assignment"):
            print(f"existing: {preview['existing_assignment']}")
        if preview.get("proposed_assignment"):
            print(f"proposed: {preview['proposed_assignment']}")
        if preview.get("pickup"):
            print(f"pickup: {preview['pickup']}")
        if preview.get("verification"):
            print(f"verification: {preview['verification']}")
        if preview.get("blocked"):
            print(f"blocked: {preview.get('block_reason')}")
    return exit_code


def _setup(args):
    existing = read_config_personnummer()
    if existing and args.personnummer is None and not args.no_input and sys.stdin.isatty():
        resolve_personnummer(personnummer=existing, allow_prompt=False)
        print("Already configured.", file=sys.stderr)
        answer = input("Overwrite? [y/N] ").strip().lower()
        if answer != "y":
            return

    personnummer = _resolve_setup_personnummer(args.personnummer, no_input=args.no_input)
    session = login(
        personnummer=personnummer,
        quiet=args.quiet,
        freja_timeout=args.freja_timeout,
        allow_prompt=False,
    )
    _persist_setup_state(personnummer, session)
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
