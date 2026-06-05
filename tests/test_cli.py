from tempus_cli.cli import main
from tempus_cli.models import PickupStatus


def test_help_runs(capsys):
    assert main([]) == 0
    assert "usage: tempus" in capsys.readouterr().out


def test_status_runs(capsys):
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "session:" in out
    assert "authenticated:" in out


def test_pickup_requires_iso_date(capsys):
    assert main(["pickup", "--child", "Viggo", "--date", "imorgon"]) == 2
    assert "YYYY-MM-DD" in capsys.readouterr().err


def test_pickup_rejects_other_child(capsys):
    assert main(["pickup", "--child", "Felix", "--date", "2026-06-08"]) == 2
    assert "Viggo" in capsys.readouterr().err


def test_pickup_prints_read_result(monkeypatch, capsys):
    class FakeApi:
        def __init__(self, session=None):
            pass

        def pickup(self, child, date):
            return PickupStatus(child, date, "08:30", "15:30", None, False, "getPickupRead")

    monkeypatch.setattr("tempus_cli.cli.login", lambda personnummer=None, quiet=True: object())
    monkeypatch.setattr("tempus_cli.cli.TempusApi", FakeApi)

    assert main(["pickup", "--child", "Viggo", "--date", "2026-06-08"]) == 0
    out = capsys.readouterr().out
    assert "Barn: Viggo" in out
    assert "Hämtas av: -" in out
    assert "Källa: getPickupRead" in out


def test_pickup_passes_personnummer_to_login(monkeypatch, capsys):
    calls = {}

    class FakeApi:
        def __init__(self, session=None):
            pass

        def pickup(self, child, date):
            return PickupStatus(child, date, "08:30", "15:30", None, False, "getPickupRead")

    monkeypatch.setattr("tempus_cli.cli.login", lambda personnummer=None, quiet=True: calls.update(personnummer=personnummer) or object())
    monkeypatch.setattr("tempus_cli.cli.TempusApi", FakeApi)

    assert main(["pickup", "--child", "Viggo", "--date", "2026-06-08", "--personnummer", "198001011234"]) == 0
    assert calls["personnummer"] == "198001011234"


def test_pickup_preview_prints_no_change(monkeypatch, capsys):
    class FakeApi:
        def __init__(self, session=None):
            pass

        def pickup(self, child, date):
            return PickupStatus(child, date, "08:30", "15:30", None, False, "getPickupRead")

    monkeypatch.setattr("tempus_cli.cli.login", lambda personnummer=None, quiet=True: object())
    monkeypatch.setattr("tempus_cli.cli.TempusApi", FakeApi)

    assert main(["pickup", "--child", "Viggo", "--date", "2026-06-08", "--pickup", "Farmor"]) == 0
    out = capsys.readouterr().out
    assert "Förhandsvisning, ingen ändring gjord." in out
    assert "Ny hämtas av: Farmor" in out
    assert '--apply --confirm "Viggo 2026-06-08 Farmor"' in out


def test_pickup_apply_requires_exact_confirm(monkeypatch, capsys):
    class FakeApi:
        def __init__(self, session=None):
            pass

        def pickup(self, child, date):
            return PickupStatus(child, date, "08:30", "15:30", None, False, "getPickupRead")

    monkeypatch.setattr("tempus_cli.cli.login", lambda personnummer=None, quiet=True: object())
    monkeypatch.setattr("tempus_cli.cli.TempusApi", FakeApi)

    assert main([
        "pickup", "--child", "Viggo", "--date", "2026-06-08", "--pickup", "Farmor", "--apply", "--confirm", "fel"
    ]) == 1
    assert "--confirm måste vara exakt" in capsys.readouterr().err
