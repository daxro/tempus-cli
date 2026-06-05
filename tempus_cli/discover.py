import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .errors import SafetyError
from .paths import repo_root
from .redact import redact_text
from .transport import rpc_method_from_payload


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def record_request(method, url, body=None, response=None):
    parts = urlsplit(url)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "path": parts.path,
        "rpc_method": rpc_method_from_payload(body or ""),
        "request_shape": redact_text(_shape(body)),
        "response_shape": redact_text(_shape(response)),
    }


def _shape(value):
    if value is None:
        return ""
    text = str(value)
    return text[:500]


def write_discovery(records, output, allow_repo_output=False):
    path = Path(output)
    if _inside(path, repo_root()) and not allow_repo_output:
        raise SafetyError("Refusing to write discovery output inside repo")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    return path
