from pathlib import Path

from platformdirs import user_config_dir

APP_NAME = "tempus-cli"

def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))

def default_session_path() -> Path:
    return config_dir() / "session.json"

def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
