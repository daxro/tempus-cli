import pytest

from tempus_cli.errors import SafetyError
from tempus_cli.gwt import payload_get_schemas
from tempus_cli.transport import ReadOnlyTempusTransport, rpc_method_from_payload


def test_rpc_method_from_payload():
    payload = payload_get_schemas("A"*32, 12)
    assert rpc_method_from_payload(payload) == "getSchemas"


def test_blocks_write_like_rpc():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_rpc_method("savePickup")


def test_blocks_unknown_rpc():
    t = ReadOnlyTempusTransport(object())
    with pytest.raises(SafetyError):
        t._check_rpc_method("getSecretThing")
