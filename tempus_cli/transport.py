from urllib.parse import urlparse

from .errors import SafetyError

ALLOWED_HOSTS = {"home.tempusinfo.se", "login.tempusinfo.se", "login001.stockholm.se", "login003.stockholm.se"}
ALLOWED_HOME_PATHS = {"/tempusHome/", "/tempusHome/tempusHome/service", "/tempusHome/tempusHome/tempusHome.nocache.js"}
READ_ONLY_RPC_METHODS = {
    "getSchemas",
    "getApplyableSchemas",
    "getGrandIdIdentityProviders",
    "isCreateLoginCookieEnabled",
    "isUsernamePasswordEnabled",
}
WRITE_WORDS = ("save", "update", "delete", "set", "create", "add", "remove", "confirm", "approve", "submit", "apply", "write")


def rpc_method_from_payload(payload: str):
    parts = payload.split("|")
    for part in parts:
        if part.startswith("get") or part.startswith("is") or part.startswith("save") or part.startswith("set"):
            return part
    return None


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
        return self.session.post(url, data=data, **kwargs)

    def _check_url(self, method, url, allow_login=False):
        parsed = urlparse(url)
        if parsed.hostname not in ALLOWED_HOSTS:
            raise SafetyError(f"Blocked Tempus request to host: {parsed.hostname}")
        if parsed.hostname == "home.tempusinfo.se" and parsed.path not in ALLOWED_HOME_PATHS:
            raise SafetyError(f"Blocked Tempus path: {parsed.path}")
        if method == "POST" and parsed.path != "/tempusHome/tempusHome/service" and not allow_login:
            raise SafetyError("Form POSTs are only allowed inside login flow")

    def _check_rpc_method(self, method):
        if not method:
            raise SafetyError("Could not identify GWT RPC method")
        lower = method.lower()
        if any(word in lower for word in WRITE_WORDS):
            raise SafetyError(f"Blocked write-like Tempus RPC method: {method}")
        if method not in READ_ONLY_RPC_METHODS:
            raise SafetyError(f"Blocked unknown Tempus RPC method: {method}")
