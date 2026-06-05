import pytest

from tempus_cli.models import PickupStatus, assert_pickup_name, assert_viggo


def test_pickup_status_shape():
    status = PickupStatus(
        child="Viggo",
        date="2026-06-08",
        dropoff="08:30",
        pickup_time="15:30",
        pickup_person=None,
        locked=False,
        source_method="observedReadMethod",
    )
    assert status.child == "Viggo"
    assert status.pickup_person is None


def test_only_viggo_supported():
    assert_viggo("Viggo")
    with pytest.raises(ValueError):
        assert_viggo("Felix")


def test_pickup_name_must_not_be_empty():
    assert assert_pickup_name(" Farmor ") == "Farmor"
    with pytest.raises(ValueError):
        assert_pickup_name(" ")
