import http.cookiejar
import json
import os
from pathlib import Path

from .errors import SafetyError
from .paths import repo_root


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def save_session_opt_in(session, path):
    path = Path(path)
    if _is_inside(path, repo_root()):
        raise SafetyError("Refusing to save Tempus session inside repo")
    cookies = []
    for c in session.cookies:
        cookies.append({
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "secure": c.secure,
            "httponly": "HttpOnly" in c._rest,
        })
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(cookies, f)
    os.chmod(path, 0o600)


def load_session_opt_in(session, path) -> bool:
    path = Path(path)
    if not path.exists():
        return False
    try:
        cookies = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(cookies, list):
        return False
    for c in cookies:
        try:
            cookie = http.cookiejar.Cookie(
                version=0, name=c["name"], value=c["value"], port=None,
                port_specified=False, domain=c["domain"],
                domain_specified=bool(c["domain"]),
                domain_initial_dot=c["domain"].startswith("."),
                path=c.get("path", "/"), path_specified=bool(c.get("path")),
                secure=c.get("secure", False), expires=None, discard=True,
                comment=None, comment_url=None,
                rest={"HttpOnly": "HttpOnly"} if c.get("httponly") else {},
            )
        except (KeyError, TypeError):
            return False
        session.cookies.set_cookie(cookie)
    return True
