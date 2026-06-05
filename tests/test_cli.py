import json
from pathlib import Path

import requests
from stockholm_freja import FrejaError

from tempus_cli.cli import build_parser, main
from tempus_cli.gwt import parse_assignment_write_response, parse_pickup_assignment

TEST_PERSONNUMMER = "0" * 12
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pickup_date_assignment"


def _fixture(name):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_help_lists_only_working_commands(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert "usage: tempus" in out

    subparsers = next(action for action in build_parser()._actions if hasattr(action, "choices") and action.choices)
    assert set(subparsers.choices) == {"status", "setup", "schemas", "providers", "login", "pickup"}


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


class FakePickupApi:
    def __init__(self, rows=None, assignments=None, write_response=None):
        self.rows = rows if rows is not None else [
            {
                "id": "123",
                "name": "Example Guardian",
                "phone": "0700000000",
                "children": ["Example Child"],
                "_raw": {"children": [{"id": 101, "name": "Example Child"}], "opaque": "x"},
            }
        ]
        self.assignments = list(assignments or [parse_pickup_assignment(_fixture("read_before.json")["response_body"])])
        self.write_response = write_response or parse_assignment_write_response(_fixture("write_assignment.json")["response_body"])
        self.writes = []

    def pickups(self):
        return self.rows

    def pickup_assignment(self, pickup_date, child_id):
        assignment = self.assignments.pop(0) if len(self.assignments) > 1 else self.assignments[0]
        assert pickup_date == "2026-06-11"
        assert child_id == "101"
        return assignment

    def assign_pickup(self, assignment):
        self.writes.append(assignment)
        return self.write_response


def test_pickup_list_json_has_stable_shape(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi())

    assert main(["pickup", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == [
        {"id": "123", "name": "Example Guardian", "phone": "0700000000", "children": ["Example Child"]}
    ]


def test_pickup_list_filters_child(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi())

    assert main(["pickup", "--child", "example child", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1


def test_pickup_child_filter_no_match_fails(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi())

    assert main(["pickup", "--child", "Unknown", "--json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no pickup contacts matching child" in captured.err


def test_pickup_create_preview_json(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi([]))

    assert main(["pickup", "--child", "Example Child", "--name", "Example Guardian", "--phone", "0700000000", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["operation"] == "create"
    assert data["write_performed"] is False
    assert data["would_write_if_applied"] is True
    assert data["proposed_pickup"] == {
        "id": None,
        "name": "Example Guardian",
        "phone": "0700000000",
        "children": ["Example Child"],
    }


def test_pickup_update_preview_preserves_unspecified_fields(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi())

    assert main(["pickup", "--id", "123", "--phone", "0711111111", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["operation"] == "update"
    assert data["existing_pickup"]["name"] == "Example Guardian"
    assert data["proposed_pickup"] == {
        "id": "123",
        "name": "Example Guardian",
        "phone": "0711111111",
        "children": ["Example Child"],
    }


def test_pickup_update_noop_preview(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi())

    assert main(["pickup", "--id", "123", "--phone", "0700000000", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["would_write_if_applied"] is False


def test_pickup_remove_preview_requires_matching_name_to_unblock(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi())

    assert main(["pickup", "--id", "123", "--remove", "--name", "Wrong Name", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["operation"] == "remove"
    assert data["blocked"] is True
    assert data["block_reason"] == "name_confirmation_does_not_match"


def test_pickup_assign_by_id_preview_uses_fixture_backed_assignment_read(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi())

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {
        "mode": "preview",
        "operation": "assign",
        "date": "2026-06-11",
        "child": {"name": "Example Child", "id": "101"},
        "contact": {"id": "123", "name": "Example Guardian", "phone": "0700000000"},
        "existing_assignment": {
            "date": "2026-06-11",
            "child_id": "101",
            "pickup_id": "456",
            "assignment_id": "901",
            "version": "assignment-version-before",
            "write_token_present": True,
        },
        "proposed_assignment": {
            "date": "2026-06-11",
            "child_id": "101",
            "pickup_id": "123",
            "assignment_id": "901",
            "version": "assignment-version-before",
            "write_token_present": True,
        },
        "contact_write": None,
        "assignment_write": {
            "required": True,
            "method": "assignPickupForDate",
            "required_fields": ["date", "child_id", "pickup_id", "assignment_id", "version", "write_token"],
        },
        "write_performed": False,
        "would_write_if_applied": True,
        "blocked": False,
        "block_reason": None,
    }


def test_pickup_assign_by_name_requires_exact_unique_match(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi())

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--name", "Example Guardian", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["contact"]["id"] == "123"
    assert data["blocked"] is False


def test_pickup_assign_non_json_preview(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi())

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123"]) == 0
    captured = capsys.readouterr()
    assert "assign: preview" in captured.out
    assert "'date': '2026-06-11'" in captured.out
    assert "'pickup_id': '123'" in captured.out


def test_pickup_assign_by_name_rejects_ambiguous_match(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    rows = [
        {"id": "123", "name": "Example Guardian", "phone": "0700000000", "children": ["Example Child"]},
        {"id": "456", "name": "Example Guardian", "phone": "0711111111", "children": ["Example Child"]},
    ]
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi(rows))

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--name", "Example Guardian", "--json"]) == 2
    assert "matched multiple records; use --id" in capsys.readouterr().err


def test_pickup_assign_missing_named_contact_fails_until_contact_fixtures(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi([]))

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--name", "Example Guardian", "--json"]) == 2
    assert "contact creation requires sanitized Tempus write fixtures" in capsys.readouterr().err


def test_pickup_assign_invalid_date_fails_before_session(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    calls = []
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: calls.append(no_input))

    assert main(["pickup", "--date", "2026-02-30", "--child", "Example Child", "--id", "123", "--json"]) == 2
    assert calls == []
    assert "--date must be a valid YYYY-MM-DD date" in capsys.readouterr().err


def test_pickup_assign_requires_child_before_session(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    calls = []
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: calls.append(no_input))

    assert main(["pickup", "--date", "2026-06-11", "--id", "123", "--json"]) == 2
    assert calls == []
    assert "--child must not be empty" in capsys.readouterr().err


def test_pickup_assign_requires_id_or_name_before_session(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    calls = []
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: calls.append(no_input))

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--json"]) == 2
    assert calls == []
    assert "--date requires --id or --name" in capsys.readouterr().err


def test_pickup_assign_rejects_contact_update_flags_before_session(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    calls = []
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: calls.append(no_input))

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--phone", "0700000000"]) == 2
    assert calls == []
    assert "--date cannot be combined with --phone" in capsys.readouterr().err


def test_pickup_assign_rejects_remove_before_session(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    calls = []
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: calls.append(no_input))

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--remove"]) == 2
    assert calls == []
    assert "--date cannot be combined with --remove" in capsys.readouterr().err


def test_pickup_assign_rejects_id_and_name_before_session(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    calls = []
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: calls.append(no_input))

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--name", "Example Guardian"]) == 2
    assert calls == []
    assert "--date requires either --id or --name, not both" in capsys.readouterr().err


def test_pickup_assign_apply_re_reads_writes_and_verifies(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    fake = FakePickupApi(
        assignments=[
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
            parse_pickup_assignment(_fixture("read_after.json")["response_body"]),
        ]
    )
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: fake)

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--apply", "--confirm", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mode"] == "apply"
    assert data["write_performed"] is True
    assert data["verification"] == {"matched": True}
    assert data["verified_assignment"]["pickup_id"] == "123"
    assert fake.writes == [
        {
            "date": "2026-06-11",
            "child_id": "101",
            "pickup_id": "123",
            "assignment_id": "901",
            "version": "assignment-version-before",
            "write_token": "assignment-write-token-before",
        }
    ]


def test_pickup_assign_apply_noop_returns_exit_2(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    fake = FakePickupApi(assignments=[parse_pickup_assignment(_fixture("read_after.json")["response_body"])])
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: fake)

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--apply", "--confirm", "--json"]) == 2
    assert fake.writes == []
    assert "already in requested state" in capsys.readouterr().err


def test_pickup_assign_apply_refuses_stale_assignment(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    stale = parse_pickup_assignment(_fixture("read_before.json")["response_body"])
    stale["version"] = "assignment-version-stale"
    fake = FakePickupApi(
        assignments=[
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
            stale,
        ]
    )
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: fake)

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--apply", "--confirm", "--json"]) == 2
    assert fake.writes == []
    assert "preview assumptions changed" in capsys.readouterr().err


def test_pickup_assign_apply_verification_mismatch_returns_json_exit_1(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    fake = FakePickupApi(
        assignments=[
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
            parse_pickup_assignment(_fixture("verification_mismatch.json")["response_body"]),
        ]
    )
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: fake)

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--apply", "--confirm", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["write_performed"] is True
    assert data["verification"] == {"matched": False}
    assert data["verified_assignment"]["pickup_id"] == "999"


def test_pickup_assign_apply_verification_mismatch_checks_child_and_date(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    wrong_target = parse_pickup_assignment(_fixture("read_after.json")["response_body"])
    wrong_target["date"] = "2026-06-12"
    wrong_target["child_id"] = "999"
    fake = FakePickupApi(
        assignments=[
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
            wrong_target,
        ]
    )
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: fake)

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--apply", "--confirm", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["write_performed"] is True
    assert data["verification"] == {"matched": False}
    assert data["verified_assignment"]["date"] == "2026-06-12"
    assert data["verified_assignment"]["child_id"] == "999"


def test_pickup_assign_apply_post_write_read_failure_returns_partial_json(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    class FailingVerifyApi(FakePickupApi):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.assignment_reads = 0

        def pickup_assignment(self, pickup_date, child_id):
            self.assignment_reads += 1
            if self.assignment_reads == 3:
                raise RuntimeError("expired session")
            return super().pickup_assignment(pickup_date, child_id)

    fake = FailingVerifyApi(
        assignments=[
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
        ]
    )
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: fake)

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--apply", "--confirm", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["write_performed"] is True
    assert data["verification"] == {"matched": False, "error": "expired session"}


def test_pickup_assign_apply_post_write_network_failure_returns_partial_json(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    class FailingVerifyApi(FakePickupApi):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.assignment_reads = 0

        def pickup_assignment(self, pickup_date, child_id):
            self.assignment_reads += 1
            if self.assignment_reads == 3:
                raise requests.ReadTimeout("slow verification")
            return super().pickup_assignment(pickup_date, child_id)

    fake = FailingVerifyApi(
        assignments=[
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
            parse_pickup_assignment(_fixture("read_before.json")["response_body"]),
        ]
    )
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: fake)

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--apply", "--confirm", "--json"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["write_performed"] is True
    assert data["verification"] == {"matched": False, "error": "slow verification"}


def test_pickup_assign_requires_fixture_proven_child_id(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    rows = [{"id": "123", "name": "Example Guardian", "phone": "0700000000", "children": ["Example Child"], "_raw": {}}]
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi(rows))

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--json"]) == 2
    assert "fixture-proven server ID" in capsys.readouterr().err


def test_pickup_assign_rejects_ambiguous_child_id(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    rows = [
        {
            "id": "123",
            "name": "Example Guardian",
            "phone": "0700000000",
            "children": ["Example Child"],
            "_raw": {"children": [{"id": 101, "name": "Example Child"}, {"id": 102, "name": "Example Child"}]},
        }
    ]
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi(rows))

    assert main(["pickup", "--date", "2026-06-11", "--child", "Example Child", "--id", "123", "--json"]) == 2
    assert "matched multiple server IDs" in capsys.readouterr().err


def test_pickup_missing_confirm_fails_before_session(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    calls = []
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: calls.append(no_input))

    assert main(["pickup", "--child", "Example Child", "--name", "Example Guardian", "--phone", "0700000000", "--apply"]) == 2
    assert calls == []
    assert "--apply requires --confirm" in capsys.readouterr().err


def test_pickup_apply_is_gated_before_session(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    calls = []
    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: calls.append(no_input))

    assert main(["pickup", "--child", "Example Child", "--name", "Example Guardian", "--phone", "0700000000", "--apply", "--confirm"]) == 2
    assert calls == []
    assert "pickup contact writes require sanitized Tempus write fixtures" in capsys.readouterr().err


def test_pickup_target_not_found(monkeypatch, capsys):
    from tempus_cli import cli as cli_module

    monkeypatch.setattr(cli_module, "_get_authenticated_api", lambda no_input=False: FakePickupApi([]))

    assert main(["pickup", "--id", "123", "--phone", "0711111111", "--json"]) == 2
    assert "pickup contact 123 not found" in capsys.readouterr().err
