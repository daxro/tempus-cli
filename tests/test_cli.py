import json

import requests
from stockholm_freja import FrejaError

from tempus_cli.cli import build_parser, main

TEST_PERSONNUMMER = "0" * 12


def test_help_lists_only_working_commands(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "usage: tempus" in out

    subparsers = next(action for action in build_parser()._actions if hasattr(action, "choices") and action.choices)
    assert set(subparsers.choices) == {"status", "setup", "schemas", "providers", "login"}


def test_status_runs(capsys):
    assert main(["status"]) == 0
    out = capsys.readouterr().out
    assert "configured:" in out
    assert "session:" in out
    assert "authenticated:" in out


def test_status_json_has_stable_shape(monkeypatch, capsys, tmp_path):
    from tempus_cli import cli as cli_module

    config_file = tmp_path / "config.env"
    session_file = tmp_path / "session.json"
    config_file.write_text(f"TEMPUS_PERSONNUMMER={TEST_PERSONNUMMER}\n")
    monkeypatch.setattr(cli_module, "default_config_path", lambda: config_file)
    monkeypatch.setattr(cli_module, "default_session_path", lambda: session_file)

    assert main(["status", "--json"]) == 0

    data = json.loads(capsys.readouterr().out)
    assert data == {
        "configured": True,
        "session": "none",
        "authenticated": False,
        "reason": None,
        "config_path": str(config_file),
        "session_path": str(session_file),
    }


def test_setup_no_input_uses_env_writes_config_and_saves_session(monkeypatch, capsys, tmp_path):
    from tempus_cli import cli as cli_module

    config_file = tmp_path / "config.env"
    session_file = tmp_path / "session.json"
    fake_session = object()
    calls = {}
    monkeypatch.setenv("TEMPUS_PERSONNUMMER", TEST_PERSONNUMMER)
    monkeypatch.setattr(cli_module, "default_config_path", lambda: config_file)
    monkeypatch.setattr(cli_module, "default_session_path", lambda: session_file)
    monkeypatch.setattr(
        cli_module,
        "login",
        lambda **kwargs: calls.update(login=kwargs) or fake_session,
    )
    monkeypatch.setattr(cli_module, "save_session_opt_in", lambda session, path: calls.update(session=session, path=path))

    assert main(["setup", "--no-input", "-q"]) == 0

    assert config_file.read_text() == f"TEMPUS_PERSONNUMMER={TEST_PERSONNUMMER}\n"
    assert calls == {
        "login": {
            "personnummer": TEST_PERSONNUMMER,
            "quiet": True,
            "freja_timeout": 180.0,
            "allow_prompt": False,
        },
        "session": fake_session,
        "path": session_file,
    }
    assert capsys.readouterr().err == ""


def test_setup_no_input_requires_personnummer_before_login(monkeypatch, capsys, tmp_path):
    from tempus_cli import cli as cli_module
    from tempus_cli import session as session_module

    calls = []
    monkeypatch.delenv("TEMPUS_PERSONNUMMER", raising=False)
    monkeypatch.setattr(session_module, "default_config_path", lambda: tmp_path / "missing.env")
    monkeypatch.setattr(cli_module, "login", lambda **kwargs: calls.append(kwargs))

    assert main(["setup", "--no-input"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "TEMPUS_PERSONNUMMER" in captured.err
    assert calls == []


def test_setup_does_not_write_config_when_login_fails(monkeypatch, tmp_path):
    from tempus_cli import cli as cli_module

    config_file = tmp_path / "config.env"
    monkeypatch.setenv("TEMPUS_PERSONNUMMER", TEST_PERSONNUMMER)
    monkeypatch.setattr(cli_module, "default_config_path", lambda: config_file)
    monkeypatch.setattr(cli_module, "login", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("login failed")))

    assert main(["setup", "--no-input", "-q"]) == 1
    assert not config_file.exists()


def test_setup_help_includes_examples_and_safety(capsys):
    assert main(["setup", "--help"]) == 0
    out = capsys.readouterr().out
    assert "TEMPUS_PERSONNUMMER" in out
    assert "Freja" in out
    assert "does not write Tempus data" in out


def test_schemas_json_has_stable_shape(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    rows = [{"id": 12, "name": "Example", "project": "tempus-example"}]

    class FakeApi:
        def schemas(self, area_id):
            assert area_id == 12
            return rows

    monkeypatch.setattr(cli_module, "TempusApi", FakeApi)

    assert main(["schemas", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == rows


def test_providers_json_has_stable_shape(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    rows = [{"name": "Example login", "option": "EXAMPLE"}]

    class FakeApi:
        def identity_providers(self, schema_id):
            assert schema_id == 399
            return rows

    monkeypatch.setattr(cli_module, "TempusApi", FakeApi)

    assert main(["providers", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == rows


def test_login_no_input_fails_before_login(monkeypatch, capsys, tmp_path):
    from tempus_cli import cli as cli_module
    from tempus_cli import session as session_module

    calls = []
    monkeypatch.delenv("TEMPUS_PERSONNUMMER", raising=False)
    monkeypatch.setattr(session_module, "default_config_path", lambda: tmp_path / "missing.env")
    monkeypatch.setattr(cli_module, "login", lambda **kwargs: calls.append(kwargs))

    assert main(["login", "--no-input"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "TEMPUS_PERSONNUMMER" in captured.err
    assert calls == []


def test_unexpected_failure_has_no_traceback(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    class FakeApi:
        def schemas(self, area_id):
            raise Exception("boom")

    monkeypatch.setattr(cli_module, "TempusApi", FakeApi)

    assert main(["schemas"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unexpected failure: boom" in captured.err
    assert "Traceback" not in captured.err


def test_freja_error_is_redacted_without_unexpected_prefix(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    class FakeApi:
        def schemas(self, area_id):
            raise FrejaError("failed for https://example.test/?SAMLTRANSACTIONID=secret")

    monkeypatch.setattr(cli_module, "TempusApi", FakeApi)

    assert main(["schemas"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unexpected failure" not in captured.err
    assert "SAMLTRANSACTIONID=%5BREDACTED%5D" in captured.err
    assert "secret" not in captured.err


def test_request_exception_is_redacted_without_unexpected_prefix(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    class FakeApi:
        def schemas(self, area_id):
            raise requests.TooManyRedirects("https://example.test/?SAMLTRANSACTIONID=secret")

    monkeypatch.setattr(cli_module, "TempusApi", FakeApi)

    assert main(["schemas"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unexpected failure" not in captured.err
    assert "SAMLTRANSACTIONID=%5BREDACTED%5D" in captured.err
    assert "secret" not in captured.err


def test_keyboard_interrupt_returns_130(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    class FakeApi:
        def schemas(self, area_id):
            raise KeyboardInterrupt

    monkeypatch.setattr(cli_module, "TempusApi", FakeApi)

    assert main(["schemas"]) == 130
    assert capsys.readouterr().err == "Interrupted.\n"
