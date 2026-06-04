import os
import requests

from tempus_cli.errors import SafetyError
from tempus_cli.session_store import load_session_opt_in, save_session_opt_in


def test_save_opt_in_0600_and_load(tmp_path):
    s = requests.Session()
    s.cookies.set("a", "b", domain="home.tempusinfo.se", path="/")
    path = tmp_path / "session.json"
    save_session_opt_in(s, path)
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    s2 = requests.Session()
    assert load_session_opt_in(s2, path) is True
    assert s2.cookies.get("a") == "b"


def test_missing_and_corrupt_return_false(tmp_path):
    s = requests.Session()
    assert load_session_opt_in(s, tmp_path / "missing.json") is False
    p = tmp_path / "bad.json"
    p.write_text("not json")
    assert load_session_opt_in(s, p) is False


def test_refuse_repo_session_file():
    s = requests.Session()
    try:
        save_session_opt_in(s, "session.json")
    except SafetyError:
        return
    raise AssertionError("expected SafetyError")
