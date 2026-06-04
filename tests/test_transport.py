import pytest

from tempus_cli.errors import SafetyError
from tempus_cli.gwt import HOME_SERVICE, GWT_MODULE_BASE, payload_get_schemas
from tempus_cli.transport import ReadOnlyTempusTransport, rpc_method_from_payload


def test_rpc_method_from_payload():
    payload = payload_get_schemas("A" * 32, 12)
    assert rpc_method_from_payload(payload) == "getSchemas"


def test_rpc_method_from_payload_requires_observed_layout():
    payload = "7|0|5|https://evil.example/|" + "A" * 32 + f"|{HOME_SERVICE}|getSchemas|I|"
    assert rpc_method_from_payload(payload) is None


def test_rpc_method_from_payload_does_not_scan_for_first_get():
    payload = f"7|0|6|{GWT_MODULE_BASE}|{'A' * 32}|{HOME_SERVICE}|savePickup|getSchemas|I|"
    assert rpc_method_from_payload(payload) == "savePickup"


def test_blocks_write_like_rpc():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_rpc_method("savePickup")


def test_blocks_unknown_rpc():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_rpc_method("getSecretThing")


def test_blocks_non_https():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_url("GET", "http://home.tempusinfo.se/tempusHome/")


def test_blocks_login_post_with_unexpected_fields():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_login_form_data({"username": "x", "password": "y"})


def test_allows_saml_login_form_fields():
    t = ReadOnlyTempusTransport(object())
    t._check_login_form_data({"SAMLResponse": "x", "RelayState": "y"})
