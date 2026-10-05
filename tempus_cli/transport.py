import requests
from urllib.parse import unquote, urlparse

from .errors import SafetyError
from .net import wrap_network_error

ALLOWED_HOSTS = {
    "login.tempusinfo.se",
    "login001.stockholm.se",
    "login003.stockholm.se",
}
ALLOWED_LOGIN_PATH_PREFIXES = (
    "/login/",
)
ALLOWED_STOCKHOLM_PATH_PREFIXES = (
    "/affwebservices/",
    "/siteminderagent/",
    "/NECSadc/",
    "/NECSadcfreja/",
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




class LoginTransport:
    def __init__(self, session):
        self.session = session

    def get(self, url, **kwargs):
        self._check_url("GET", url)
        try:
            return self.session.get(url, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise wrap_network_error(exc, "Tempus GET") from exc

    def post_login_form(self, url, data=None, **kwargs):
        self._check_url("POST", url, allow_login=True)
        self._check_login_form_data(data)
        try:
            return self.session.post(url, data=data, **kwargs)
        except requests.exceptions.RequestException as exc:
            raise wrap_network_error(exc, "Tempus login form POST") from exc

    def _check_url(self, method, url, allow_login=False):
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise SafetyError("Blocked non-HTTPS Tempus request")
        if parsed.port not in (None, 443):
            raise SafetyError(f"Blocked non-default HTTPS port: {parsed.port}")
        if parsed.hostname not in ALLOWED_HOSTS:
            raise SafetyError(f"Blocked Tempus request to host: {parsed.hostname}")
        decoded_path = unquote(parsed.path)
        if ".." in decoded_path.split("/"):
            raise SafetyError(f"Blocked path traversal: {parsed.path}")
        if parsed.hostname == "login.tempusinfo.se" and not parsed.path.startswith(ALLOWED_LOGIN_PATH_PREFIXES):
            raise SafetyError(f"Blocked login path: {parsed.path}")
        if parsed.hostname in {"login001.stockholm.se", "login003.stockholm.se"} and not parsed.path.startswith(ALLOWED_STOCKHOLM_PATH_PREFIXES):
            raise SafetyError(f"Blocked Stockholm login path: {parsed.path}")
        if method == "POST" and not allow_login:
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
