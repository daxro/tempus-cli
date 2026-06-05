import pytest

from tempus_cli.errors import FrejaError, FrejaRejectedError
from tempus_cli.freja import _ensure_12_digits, freja_login


class Resp:
    ok=True
    status_code=200
    def __init__(self, text="APPROVED"):
        self.text=text

class FakeSession:
    def __init__(self, statuses):
        self.statuses=list(statuses)
        self.posts=[]
        self.gets=[]
    def post(self, url, timeout=None, headers=None):
        self.posts.append((url, headers)); return Resp()
    def get(self, url, timeout=None, headers=None):
        self.gets.append((url, headers)); return Resp(self.statuses.pop(0))


def test_ensure_12_digits():
    assert len(_ensure_12_digits("8001011234")) == 12
    with pytest.raises(FrejaError):
        _ensure_12_digits("123")


def test_freja_approved_without_logging_pnr():
    s=FakeSession(["APPROVED"])
    freja_login(s, "https://login001.stockholm.se/NECSadc/freja/start?x=1", "198001011234", poll_interval=0, timeout=1)
    assert "action=init" in s.posts[0][0]
    assert "userInput=198001011234" in s.posts[0][0]
    assert "action=checkstatus" in s.gets[0][0]


def test_stockholm_necsadcfreja_init_includes_personnummer():
    s=FakeSession(["APPROVED"])
    freja_login(s, "https://login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja", "198001011234", poll_interval=0, timeout=1)

    assert s.posts[0][0] == "https://login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja?action=init&userInput=198001011234"


def test_freja_init_uses_ajax_headers():
    s=FakeSession(["APPROVED"])
    freja_login(s, "https://login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja", "198001011234", poll_interval=0, timeout=1)

    headers = s.posts[0][1]
    assert headers["X-Requested-With"] == "XMLHttpRequest"
    assert headers["Referer"] == "https://login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja"


def test_on_started_runs_after_init_before_poll():
    events=[]
    s=FakeSession(["APPROVED"])

    freja_login(
        s,
        "https://login003.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja",
        "198001011234",
        poll_interval=0,
        timeout=1,
        on_started=lambda: events.append(("started", len(s.posts), len(s.gets))),
    )

    assert events == [("started", 1, 0)]


def test_freja_rejected():
    with pytest.raises(FrejaRejectedError):
        freja_login(FakeSession(["CANCELED"]), "https://x/freja", "198001011234", poll_interval=0, timeout=1)


def test_freja_rejected_status_alias():
    with pytest.raises(FrejaRejectedError):
        freja_login(FakeSession(["REJECTED"]), "https://x/freja", "198001011234", poll_interval=0, timeout=1)
