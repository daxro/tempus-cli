import requests

from . import gwt
from .transport import ReadOnlyTempusTransport

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) tempus-cli/0.1"
PICKUP_WRITES_DISABLED = "pickup writes require sanitized Tempus write fixtures before --apply can be enabled"
DATE_ASSIGNMENT_READ_UNAVAILABLE = "date assignment reads require sanitized Tempus fixtures before assignment preview can be enabled"


def new_session():
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


class TempusApi:
    def __init__(self, session=None, permutation=None):
        self.session = session or new_session()
        self.transport = ReadOnlyTempusTransport(self.session)
        self.permutation = permutation

    def ensure_permutation(self):
        if not self.permutation:
            self.permutation = gwt.discover_permutation(self.transport)
        return self.permutation

    def schemas(self, area_id=12):
        perm = self.ensure_permutation()
        payload = gwt.payload_get_schemas(perm, area_id)
        resp = self.transport.post_rpc(gwt.GWT_SERVICE_URL, payload, headers=gwt.headers(perm), timeout=gwt.HTTP_TIMEOUT)
        resp.raise_for_status()
        return gwt.parse_schemas(resp.text)

    def identity_providers(self, schema_id=399):
        perm = self.ensure_permutation()
        payload = gwt.payload_get_grand_id_identity_providers(perm, schema_id)
        resp = self.transport.post_rpc(gwt.GWT_SERVICE_URL, payload, headers=gwt.headers(perm), timeout=gwt.HTTP_TIMEOUT)
        resp.raise_for_status()
        return gwt.parse_identity_providers(resp.text)

    def authenticate_user_with_cookies(self, use_nu_cookie=False, use_bearer_auth=False):
        perm = self.ensure_permutation()
        payload = gwt.payload_authenticate_user_with_cookies(
            perm,
            use_nu_cookie=use_nu_cookie,
            use_bearer_auth=use_bearer_auth,
        )
        resp = self.transport.post_rpc(gwt.GWT_SERVICE_URL, payload, headers=gwt.headers(perm), timeout=gwt.HTTP_TIMEOUT)
        resp.raise_for_status()
        if not resp.text.startswith("//OK"):
            raise RuntimeError("Tempus cookie authentication did not return a successful GWT RPC response")
        return True

    def heartbeat(self):
        perm = self.ensure_permutation()
        payload = gwt.payload_heartbeat(perm)
        resp = self.transport.post_rpc(gwt.GWT_SERVICE_URL, payload, headers=gwt.headers(perm), timeout=gwt.HTTP_TIMEOUT)
        resp.raise_for_status()
        if not resp.text.startswith("//OK"):
            raise RuntimeError("Tempus heartbeat did not return a successful GWT RPC response")
        return True

    def pickups(self):
        perm = self.ensure_permutation()
        self.authenticate_user_with_cookies()
        payload = gwt.payload_get_pickups(perm)
        resp = self.transport.post_rpc(gwt.GWT_SERVICE_URL, payload, headers=gwt.headers(perm), timeout=gwt.HTTP_TIMEOUT)
        resp.raise_for_status()
        return gwt.parse_pickups(resp.text)

    def create_pickup(self, name, phone, children):
        raise RuntimeError(PICKUP_WRITES_DISABLED)

    def update_pickup(self, pickup_id, name, phone, children, opaque_a="", opaque_b=""):
        raise RuntimeError(PICKUP_WRITES_DISABLED)

    def remove_pickup(self, pickup_id):
        raise RuntimeError(PICKUP_WRITES_DISABLED)

    def pickup_assignment(self, date, child_name):
        raise RuntimeError(DATE_ASSIGNMENT_READ_UNAVAILABLE)

    def assign_pickup(self, date, child_id, pickup_id):
        raise RuntimeError(PICKUP_WRITES_DISABLED)
