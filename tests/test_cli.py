from tempus_cli.cli import main


def test_help_runs(capsys):
    assert main([]) == 0
    assert "usage: tempus" in capsys.readouterr().out


def test_status_runs(capsys):
    assert main(["status"]) == 0
    assert "in-memory only" in capsys.readouterr().out


def test_pickup_requires_iso_date(capsys):
    assert main(["pickup", "--child", "Viggo", "--date", "imorgon"]) == 2
    assert "YYYY-MM-DD" in capsys.readouterr().err
