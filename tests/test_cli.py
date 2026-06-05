from tempus_cli.cli import main
from tempus_cli.models import PickupStatus


def test_help_runs(capsys):
    assert main([]) == 0
    assert "usage: tempus" in capsys.readouterr().out


def test_status_runs(capsys):
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "configured:" in out
    assert "session:" in out
    assert "authenticated:" in out


def test_status_json_outputs_machine_readable_status(monkeypatch, capsys, tmp_path):
    import json
    from tempus_cli import cli as cli_module

    config_file = tmp_path / "config.env"
    session_file = tmp_path / "session.json"
    config_file.write_text("TEMPUS_PERSONNUMMER=198001011234\n")
    monkeypatch.setattr(cli_module, "default_config_path", lambda: config_file)
    monkeypatch.setattr(cli_module, "default_session_path", lambda: session_file)

    assert main(["status", "--json"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data["configured"] is True
    assert data["personnummer"] == "8001****1234"
    assert data["session"] == "none"
    assert data["authenticated"] is False
    assert data["config_path"] == str(config_file)
    assert data["session_path"] == str(session_file)


def test_setup_no_input_uses_env_writes_config_and_saves_session(monkeypatch, capsys, tmp_path):
    from tempus_cli import cli as cli_module

    config_file = tmp_path / "config.env"
    session_file = tmp_path / "session.json"
    fake_session = object()
    calls = {}
    monkeypatch.setenv("TEMPUS_PERSONNUMMER", "198001011234")
    monkeypatch.setattr(cli_module, "default_config_path", lambda: config_file)
    monkeypatch.setattr(cli_module, "default_session_path", lambda: session_file)
    monkeypatch.setattr(cli_module, "login", lambda personnummer=None, quiet=False, freja_timeout=180.0: calls.update(personnummer=personnummer, quiet=quiet, timeout=freja_timeout) or fake_session)
    monkeypatch.setattr(cli_module, "save_session_opt_in", lambda session, path: calls.update(session=session, path=path))

    assert main(["setup", "--no-input", "-q"]) == 0

    assert config_file.read_text() == "TEMPUS_PERSONNUMMER=198001011234\n"
    assert calls == {"personnummer": "198001011234", "quiet": True, "timeout": 180.0, "session": fake_session, "path": session_file}
    assert "Authenticated." not in capsys.readouterr().err


def test_setup_no_input_requires_personnummer(monkeypatch, capsys, tmp_path):
    from tempus_cli import cli as cli_module

    monkeypatch.delenv("TEMPUS_PERSONNUMMER", raising=False)
    monkeypatch.delenv("PERSONNUMMER", raising=False)
    monkeypatch.setattr(cli_module, "default_config_path", lambda: tmp_path / "config.env")

    assert main(["setup", "--no-input"]) == 2
    assert "TEMPUS_PERSONNUMMER" in capsys.readouterr().err


def test_setup_does_not_write_config_when_login_fails(monkeypatch, tmp_path):
    from tempus_cli import cli as cli_module

    config_file = tmp_path / "config.env"
    monkeypatch.setenv("TEMPUS_PERSONNUMMER", "198001011234")
    monkeypatch.setattr(cli_module, "default_config_path", lambda: config_file)
    monkeypatch.setattr(cli_module, "login", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("login failed")))

    assert main(["setup", "--no-input", "-q"]) == 1
    assert not config_file.exists()


def test_setup_help_includes_examples_and_safety(capsys):
    assert main(["setup", "--help"]) == 0
    out = capsys.readouterr().out
    assert "TEMPUS_PERSONNUMMER" in out
    assert "Freja" in out
    assert "session" in out.lower()


def test_pickup_help_says_writes_are_disabled(capsys):
    assert main(["pickup", "--help"]) == 0
    out = capsys.readouterr().out
    assert "writes disabled" in out


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
