import argparse
import datetime as dt
import getpass
import json
import os
import re
import sys
from pathlib import Path


from . import __version__
from .api import TempusApi
from .discover import record_request, write_discovery
from .errors import TempusError
from .session import login, status_text, verify_authenticated
from .session_store import load_session_opt_in, save_session_opt_in
from .paths import default_config_path, default_session_path
from .redact import redact_text
from .models import assert_pickup_name, assert_viggo

AREA_IDS = {"stockholm": 12}


def build_parser():
    parser = argparse.ArgumentParser(prog="tempus")
    parser.add_argument("--version", action="version", version=f"tempus {__version__}")
    sub = parser.add_subparsers(dest="command")

    status = sub.add_parser("status", help="Check local Tempus session status")
    status.add_argument("--json", dest="json_output", action="store_true", help="Output status as JSON")

    setup = sub.add_parser(
        "setup",
        help="Configure Tempus Freja login and cache a session",
        description="Configure Tempus with a 12-digit personal number and save a verified session.",
        epilog="""examples:
  TEMPUS_PERSONNUMMER=200001011234 tempus setup --no-input
  tempus setup

safety:
  uses Freja eID+ through Stockholm; never QR
  stores config and session outside the repo with 0600 permissions""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    setup.add_argument("-q", "--quiet", action="store_true", help="Suppress progress messages on stderr")
    setup.add_argument("--no-input", action="store_true", help="Read TEMPUS_PERSONNUMMER/PERSONNUMMER from env instead of prompting")
    setup.add_argument("--freja-timeout", type=float, default=180.0, help=argparse.SUPPRESS)

    schemas = sub.add_parser("schemas", help="List public Tempus schemas/verksamheter")
    schemas.add_argument("--area", default="Stockholm")
    schemas.add_argument("--area-id", type=int)

    providers = sub.add_parser("providers", help="List public login providers for schema")
    providers.add_argument("--schema-id", type=int, default=399)

    login_p = sub.add_parser("login", help="Log in with Freja eID+ through Stockholm")
    login_p.add_argument("--personnummer", help=argparse.SUPPRESS)
    login_p.add_argument("--freja-timeout", type=float, default=180.0, help=argparse.SUPPRESS)

    children = sub.add_parser("children", help="List children (not enabled until read RPC is discovered)")
    children.add_argument("--personnummer", help=argparse.SUPPRESS)

    pickup = sub.add_parser(
        "pickup",
        help="Read/preview pickup status for one date; writes disabled",
        description="Read/preview pickup status for one date. Tempus writes disabled until a verified write RPC exists.",
    )
    pickup.add_argument("--child", required=True)
    pickup.add_argument("--date", required=True)
    pickup.add_argument("--personnummer", help=argparse.SUPPRESS)
    pickup.add_argument("--pickup", help="Preview a new pickup person; no write without --apply --confirm")
    pickup.add_argument("--overwrite", action="store_true")
    pickup.add_argument("--apply", action="store_true")
    pickup.add_argument("--confirm")

    discover = sub.add_parser("discover-auth", help="Record redacted authenticated Tempus read RPC metadata")
    discover.add_argument("--output", required=True)
    discover.add_argument("--allow-repo-output", action="store_true")
    discover.add_argument("--freja-timeout", type=float, default=180.0)
    discover.add_argument("--personnummer", help=argparse.SUPPRESS)

    return parser


def _dash(value):
    return value if value else "-"


def print_pickup_status(status):
    print(f"Barn: {status.child}")
    print(f"Datum: {status.date}")
    print(f"Lämning: {_dash(status.dropoff)}")
    print(f"Hämtning: {_dash(status.pickup_time)}")
    print(f"Hämtas av: {_dash(status.pickup_person)}")
    print(f"Låst: {'ja' if status.locked else 'nej'}")
    print(f"Källa: {status.source_method}")


def print_pickup_preview(status, pickup_name, confirm_text):
    print("Förhandsvisning, ingen ändring gjord.")
    print(f"Barn: {status.child}")
    print(f"Datum: {status.date}")
    print(f"Nuvarande hämtas av: {_dash(status.pickup_person)}")
    print(f"Ny hämtas av: {pickup_name}")
    print(f'För att skriva: lägg till --apply --confirm "{confirm_text}"')


def _mask_personnummer(personnummer):
    if not personnummer or len(personnummer) < 9:
        return personnummer
    return personnummer[2:6] + "****" + personnummer[8:]


def _read_config_personnummer(path=None):
    path = path or default_config_path()
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("TEMPUS_PERSONNUMMER="):
            return line.split("=", 1)[1].strip()
    return None


def _write_config_personnummer(personnummer, path=None):
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(f"TEMPUS_PERSONNUMMER={personnummer}\n")
    os.chmod(path, 0o600)


def _validate_personnummer(personnummer):
    if not re.fullmatch(r"\d{12}", personnummer or ""):
        raise ValueError("Personnummer måste vara 12 siffror (YYYYMMDDXXXX)")
    return personnummer


def _env_personnummer():
    return os.environ.get("TEMPUS_PERSONNUMMER") or os.environ.get("PERSONNUMMER")


def _status_dict(config_path=None, session_path=None):
    config_path = config_path or default_config_path()
    session_path = session_path or default_session_path()
    personnummer = _read_config_personnummer(config_path)
    status = {
        "configured": bool(personnummer),
        "personnummer": _mask_personnummer(personnummer) if personnummer else None,
        "session": None,
        "authenticated": False,
        "reason": None,
        "config_path": str(config_path),
        "session_path": str(session_path),
    }
    if not session_path.exists():
        status["session"] = "none"
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
    if status["personnummer"]:
        print(f"personnummer: {status['personnummer']}")
    print(f"config: {status['config_path']}")
    print(f"session: {status['session']}")
    print(f"session_path: {status['session_path']}")
    print(f"authenticated: {'yes' if status['authenticated'] else 'no'}")
    if status["reason"]:
        print(f"reason: {status['reason']}")


def _setup(args):
    personnummer = _env_personnummer() if args.no_input else getpass.getpass("Personnummer (12 siffror, visas inte): ").strip()
    if not personnummer and args.no_input:
        raise ValueError("TEMPUS_PERSONNUMMER env var krävs i non-interactive mode")
    if not personnummer:
        raise ValueError("Personnummer krävs")
    personnummer = _validate_personnummer(personnummer)
    session = login(personnummer=personnummer, quiet=args.quiet, freja_timeout=args.freja_timeout)
    _write_config_personnummer(personnummer)
    save_session_opt_in(session, default_session_path())
    if not args.quiet:
        print("Authenticated.", file=sys.stderr)
    print(status_text())


def main(argv=None):
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        if args.command == "status":
            status = _status_dict()
            if args.json_output:
                print(json.dumps(status, ensure_ascii=False, indent=2))
            else:
                _print_status(status)
            return 0
        if args.command == "setup":
            _setup(args)
            return 0
        if args.command == "schemas":
            area_id = args.area_id or AREA_IDS.get(args.area.lower())
            if not area_id:
                parser.error("unknown area; use --area-id")
            for row in TempusApi().schemas(area_id):
                print(f"{row.get('id')}: {row.get('name')} ({row.get('project')})")
            return 0
        if args.command == "providers":
            for row in TempusApi().identity_providers(args.schema_id):
                print(f"{row.get('name')}: {row.get('option')}")
            return 0
        if args.command == "login":
            login(personnummer=args.personnummer, freja_timeout=args.freja_timeout)
            print("Inloggning klar. Sessionen sparades inte.")
            return 0
        if args.command == "discover-auth":
            # Validate output location before asking for hidden Freja input.
            write_discovery([], args.output, allow_repo_output=args.allow_repo_output)
            session = login(personnummer=args.personnummer, freja_timeout=args.freja_timeout, quiet=True)
            records = [record_request("GET", "https://home.tempusinfo.se/tempusHome/")]
            write_discovery(records, args.output, allow_repo_output=True)
            print(f"Skrev redigerad discovery: {Path(args.output)}")
            return 0
        if args.command == "children":
            for child in TempusApi(session=login(personnummer=args.personnummer, quiet=True)).children():
                print(child)
            return 0
        if args.command == "pickup":
            dt.date.fromisoformat(args.date)
            assert_viggo(args.child)
            api = TempusApi(session=login(personnummer=args.personnummer, quiet=True))
            status = api.pickup(child=args.child, date=args.date)
            if args.pickup is None:
                print_pickup_status(status)
                return 0
            pickup_name = assert_pickup_name(args.pickup)
            if args.confirm and not args.apply:
                raise TempusError("--confirm används bara ihop med --apply")
            expected_confirm = f"{args.child} {args.date} {pickup_name}"
            if args.apply:
                if args.confirm != expected_confirm:
                    raise TempusError(f"--confirm måste vara exakt: {expected_confirm}")
                raise TempusError("Tempus-skrivning är inte aktiverad än: verifierad write-RPC saknas.")
            if status.locked:
                raise TempusError("Kan inte förhandsvisa: datumet är låst i Tempus.")
            if status.pickup_person and not args.overwrite:
                raise TempusError("Kan inte förhandsvisa: hämtas av är redan satt. Lägg till --overwrite för förhandsvisning.")
            print_pickup_preview(status, pickup_name, expected_confirm)
            return 0
        parser.print_help()
        return 0
    except ValueError as e:
        message = str(e) or "--date måste vara YYYY-MM-DD"
        if "Invalid isoformat" in message:
            message = "--date måste vara YYYY-MM-DD"
        print(f"Fel: {message}", file=sys.stderr)
        return 2
    except (TempusError, RuntimeError, NotImplementedError) as e:
        print(f"Fel: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
