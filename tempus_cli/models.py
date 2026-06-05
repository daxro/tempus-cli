from dataclasses import dataclass


@dataclass(frozen=True)
class PickupStatus:
    child: str
    date: str
    dropoff: str | None
    pickup_time: str | None
    pickup_person: str | None
    locked: bool
    source_method: str


def assert_viggo(child: str) -> None:
    if child != "Viggo":
        raise ValueError("Endast exakt barnnamn Viggo stöds just nu")


def assert_pickup_name(name: str | None) -> str:
    value = (name or "").strip()
    if not value:
        raise ValueError("--pickup får inte vara tom")
    return value
