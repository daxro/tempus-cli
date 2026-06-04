from urllib.parse import urlparse

from .errors import SafetyError
from .gwt import GWT_MODULE_BASE, HOME_SERVICE

ALLOWED_HOSTS = {
    "home.tempusinfo.se",
    "login.tempusinfo.se",
    "login001.stockholm.se",
    "login003.stockholm.se",
}
ALLOWED_HOME_PREFIXES = (
    "/tempusHome/",
)
ALLOWED_LOGIN_PATH_PREFIXES = (
    "/login/",
)
ALLOWED_STOCKHOLM_PATH_PREFIXES = (
    "/affwebservices/",
    "/siteminderagent/",
)
READ_ONLY_RPC_METHODS = {
    "getSchemas",
    "getApplyableSchemas",
    "getGrandIdIdentityProviders",
    "isCreateLoginCookieEnabled",
    "isUsernamePasswordEnabled",
}
WRITE_WORDS = (
    "save",
    "update",
    "delete",
    "set",
    "create",
    "add",
    "remove",
    "confirm",
    "approve",
    "submit",
    "apply",
    "write",
)
LOGIN_FORM_FIELDS = {
    "SAMLRequest",
    "SAMLResponse",
    "RelayState",
    "SMENC",
    "SMLOCALE",
    "SMQUERYDATA",
    "postPreservationData",
}


def rpc_method_from_payload(payload: str):
    """Return the GWT RPC method using the observed HomeService wire layout.

    Public Tempus Home RPC payloads are shaped like:
    7|0|N|moduleBase|permutation|service|method|...

    This intentionally does not scan the whole payload for method-looking strings;
    scanning can pick a harmless string before a write method.
    """
    parts = payload.split("|")
    if len(parts) < 8:
        return None
    if parts[0] != "7" or parts[1] != "0":
        return None
    if parts[3] != GWT_MODULE_BASE:
        return None
    if parts[5] != HOME_SERVICE:
        return None
    return parts[6] or None


class ReadOnlyTempusTransport:
    def __init__(self, session):
        self.session = session

    def get(self, url, **kwargs):
        self._check_url("GET", url)
        return self.session.get(url, **kwargs)

    def post_rpc(self, url, payload, headers=None, **kwargs):
        self._check_url("POST", url)
        method = rpc_method_from_payload(payload)
        self._check_rpc_method(method)
        return self.session.post(url, data=payload, headers=headers, **kwargs)

    def post_login_form(self, url, data=None, **kwargs):
        self._check_url("POST", url, allow_login=True)
        self._check_login_form_data(data)
        return self.session.post(url, data=data, **kwargs)

    def _check_url(self, method, url, allow_login=False):
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise SafetyError("Blocked non-HTTPS Tempus request")
        if parsed.hostname not in ALLOWED_HOSTS:
            raise SafetyError(f"Blocked Tempus request to host: {parsed.hostname}")
        if parsed.hostname == "home.tempusinfo.se" and not parsed.path.startswith(ALLOWED_HOME_PREFIXES):
            raise SafetyError(f"Blocked Tempus path: {parsed.path}")
        if parsed.hostname == "login.tempusinfo.se" and not parsed.path.startswith(ALLOWED_LOGIN_PATH_PREFIXES):
            raise SafetyError(f"Blocked login path: {parsed.path}")
        if parsed.hostname in {"login001.stockholm.se", "login003.stockholm.se"} and not parsed.path.startswith(ALLOWED_STOCKHOLM_PATH_PREFIXES):
            raise SafetyError(f"Blocked Stockholm login path: {parsed.path}")
        if method == "POST" and parsed.hostname == "home.tempusinfo.se" and parsed.path != "/tempusHome/tempusHome/service":
            raise SafetyError("Only GWT RPC POSTs are allowed on Tempus Home")
        if method == "POST" and parsed.hostname != "home.tempusinfo.se" and not allow_login:
            raise SafetyError("Form POSTs are only allowed inside login flow")

    def _check_login_form_data(self, data):
        if data is None:
            return
        keys = set(data.keys()) if hasattr(data, "keys") else set()
        if not keys:
            raise SafetyError("Blocked empty login form POST")
        unknown = keys - LOGIN_FORM_FIELDS
        if unknown:
            raise SafetyError(f"Blocked unexpected login form fields: {', '.join(sorted(unknown))}")

    def _check_rpc_method(self, method):
        if not method:
            raise SafetyError("Could not identify GWT RPC method")
        lower = method.lower()
        if any(word in lower for word in WRITE_WORDS):
            raise SafetyError(f"Blocked write-like Tempus RPC method: {method}")
        if method not in READ_ONLY_RPC_METHODS:
            raise SafetyError(f"Blocked unknown Tempus RPC method: {method}")
