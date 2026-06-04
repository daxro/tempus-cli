import argparse
import datetime as dt
import sys

from . import __version__
from .api import TempusApi
from .errors import TempusError
from .session import login, status_text

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

    sub.add_parser("children", help="List children (not enabled until read RPC is discovered)")

    pickup = sub.add_parser("pickup", help="Read pickup status for one date")
    pickup.add_argument("--child", required=True)
    pickup.add_argument("--date", required=True)

    return parser


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
            login(personnummer=args.personnummer)
            print("Inloggning klar. Sessionen sparades inte.")
            return 0
        if args.command == "children":
            raise TempusError("Barnlista är inte aktiverad än: autentiserad read-only RPC saknas.")
        if args.command == "pickup":
            dt.date.fromisoformat(args.date)
            raise TempusError("Pickup-läsning är inte aktiverad än: autentiserad read-only RPC saknas.")
        parser.print_help()
        return 0
    except ValueError:
        print("Fel: --date måste vara YYYY-MM-DD", file=sys.stderr)
        return 2
    except (TempusError, RuntimeError, NotImplementedError) as e:
        print(f"Fel: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
