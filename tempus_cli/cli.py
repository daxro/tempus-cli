import argparse
import datetime as dt
import sys
from pathlib import Path


from . import __version__
from .api import TempusApi
from .discover import record_request, write_discovery
from .errors import TempusError
from .session import login, status_text
from .models import assert_pickup_name, assert_viggo

AREA_IDS = {"stockholm": 12}


def build_parser():
    parser = argparse.ArgumentParser(prog="tempus")
    parser.add_argument("--version", action="version", version=f"tempus {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Check local Tempus session status")

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

    pickup = sub.add_parser("pickup", help="Read pickup status for one date")
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


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            print(status_text())
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
