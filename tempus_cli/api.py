import requests

from . import gwt
from .transport import ReadOnlyTempusTransport

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X) tempus-cli/0.1"


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
            self.permutation = gwt.discover_permutation(self.session)
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

    def children(self):
        raise NotImplementedError("Authenticated child-list RPC is not discovered yet")

    def pickup(self, child, date):
        raise NotImplementedError("Authenticated pickup RPC is not discovered yet")
