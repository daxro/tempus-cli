import argparse
import json
import os
import sys

from . import __version__
from .api import TempusApi
from .errors import TempusError
from .paths import default_config_path, default_session_path
from .redact import redact_text
from .session import login, read_config_personnummer, resolve_personnummer, status_text, verify_authenticated
from .session_store import load_session_opt_in, save_session_opt_in

AREA_IDS = {"stockholm": 12}


def build_parser():
    parser = argparse.ArgumentParser(
        prog="tempus",
        description="Unofficial read-only CLI for Tempus Home.",
        epilog="""examples:
  tempus status --json
  tempus schemas --area Stockholm --json
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
