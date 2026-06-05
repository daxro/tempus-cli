import pytest
import requests

from tempus_cli.errors import SafetyError
from tempus_cli.gwt import HOME_SERVICE, GWT_MODULE_BASE, TEMPUS_HOME_URL, payload_get_pickups, payload_get_schemas, payload_remove_pickup
from tempus_cli.net import TempusNetworkError
from tempus_cli.transport import ReadOnlyTempusTransport, rpc_method_from_payload


def test_rpc_method_from_payload():
    payload = payload_get_schemas("A" * 32, 12)
    assert rpc_method_from_payload(payload) == "getSchemas"


def test_rpc_method_from_payload_requires_observed_layout():
    payload = "7|0|5|https://evil.example/|" + "A" * 32 + f"|{HOME_SERVICE}|getSchemas|I|"
    assert rpc_method_from_payload(payload) is None


def test_rpc_method_from_payload_does_not_scan_for_first_get():
    payload = f"7|0|6|{GWT_MODULE_BASE}|{'A' * 32}|{HOME_SERVICE}|updateRecord|getSchemas|I|"
    assert rpc_method_from_payload(payload) == "updateRecord"


def test_blocks_write_like_rpc():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_rpc_method("updateRecord")


def test_allows_get_pickups_as_read_only_rpc():
    t = ReadOnlyTempusTransport(object())
    t._check_rpc_method("getPickups")


def test_allows_cookie_auth_and_heartbeat_as_read_only_rpc():
    t = ReadOnlyTempusTransport(object())
    t._check_rpc_method("authenticateUserWithCookies")
    t._check_rpc_method("heartbeat")


def test_generic_rpc_blocks_pickup_write():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError, match="write-like"):
        t._check_rpc_method("removePickup")


def test_pickup_write_path_allows_only_pickup_writes():
    t = ReadOnlyTempusTransport(object())
    t._check_pickup_write_rpc_method("removePickup")
    with pytest.raises(SafetyError, match="non-pickup"):
        t._check_pickup_write_rpc_method("updateRecord")


def test_pickup_write_path_recomputes_method_from_payload():
    class Session:
        def __init__(self):
            self.payload = None

        def post(self, url, data=None, headers=None, **kwargs):
            self.payload = data
            response = requests.Response()
            response.status_code = 200
            return response

    session = Session()
    t = ReadOnlyTempusTransport(session)
    t.post_pickup_write_rpc(
        "https://home.tempusinfo.se/tempusHome/tempusHome/service",
        payload_remove_pickup("A" * 32, 123),
    )
    assert rpc_method_from_payload(session.payload) == "removePickup"


def test_pickup_write_path_rejects_read_payload():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError, match="non-pickup"):
        t.post_pickup_write_rpc(
            "https://home.tempusinfo.se/tempusHome/tempusHome/service",
            payload_get_pickups("A" * 32),
        )


def test_blocks_unknown_rpc():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_rpc_method("getSecretThing")


def test_blocks_non_https():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_url("GET", "http://home.tempusinfo.se/tempusHome/")


def test_blocks_non_default_https_port():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError, match="non-default HTTPS port"):
        t._check_url("GET", "https://home.tempusinfo.se:8443/tempusHome/")


@pytest.mark.parametrize("path", [
    "/tempusHome/../admin",
    "/tempusHome/%2e%2e/admin",
    "/tempusHome/%2E%2E%2Fadmin",
])
def test_blocks_path_traversal(path):
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError, match="path traversal"):
        t._check_url("GET", f"https://home.tempusinfo.se{path}")


def test_network_timeout_is_reported_as_tempus_error():
    class TimeoutSession:
        def get(self, url, **kwargs):
            raise requests.exceptions.ReadTimeout("slow")

    t = ReadOnlyTempusTransport(TimeoutSession())
    with pytest.raises(TempusNetworkError, match="timed out"):
        t.get(TEMPUS_HOME_URL)


def test_blocks_login_post_with_unexpected_fields():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_login_form_data({"username": "x", "password": "y"})


def test_allows_saml_login_form_fields():
    t = ReadOnlyTempusTransport(object())
    t._check_login_form_data({"SAMLResponse": "x", "RelayState": "y"})


def test_allows_stockholm_freja_path():
    t = ReadOnlyTempusTransport(object())
    t._check_url("GET", "https://login001.stockholm.se/NECSadc/freja/b64startpage.jsp")
    t._check_url("GET", "https://login001.stockholm.se/NECSadcfreja/authenticate/NECSadcfreja")
