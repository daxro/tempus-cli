import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

from .errors import SafetyError
from .paths import repo_root


SESSION_VERSION = 2
SESSION_KIND = "home_api"


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def session_lock(path, timeout=15):
    return FileLock(str(Path(path)) + ".lock", timeout=timeout)


def load_token(path):
    path = Path(path)
    if not path.exists():
        return None, "none"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "unreadable"
    if isinstance(value, list):
        return None, "legacy"
    if not isinstance(value, dict) or value.get("version") != SESSION_VERSION or value.get("kind") != SESSION_KIND:
        return None, "unreadable"
    token = value.get("jwt")
    if not isinstance(token, str) or not 32 <= len(token) <= 16384 or any(ch.isspace() for ch in token):
        return None, "unreadable"
    return token, "persisted"


def save_token(path, token, *, destination_id=399):
    path = Path(path)
    if _is_inside(path, repo_root()):
        raise SafetyError("Refusing to save Tempus session inside repo")
    if not isinstance(token, str) or not 32 <= len(token) <= 16384 or any(ch.isspace() for ch in token):
        raise ValueError("Refusing to save invalid Tempus JWT")
    value = {
        "version": SESSION_VERSION,
        "kind": SESSION_KIND,
        "jwt": token,
        "destination_id": int(destination_id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        os.fchmod(file.fileno(), 0o600)
        json.dump(value, file, separators=(",", ":"))
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        try:
            os.unlink(temporary_path)
        except FileNotFoundError:
            pass
