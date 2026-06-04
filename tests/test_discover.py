import pytest

from tempus_cli.discover import record_request, write_discovery
from tempus_cli.errors import SafetyError
from tempus_cli.gwt import HOME_SERVICE, GWT_MODULE_BASE


def test_record_request_redacts_query_and_extracts_rpc():
    body = f"7|0|4|{GWT_MODULE_BASE}|{'A' * 32}|{HOME_SERVICE}|getSchemas|1|"
    rec = record_request("POST", "https://x/y?token=secret", body, "Cookie: a=b")
    assert rec["path"] == "/y"
    assert rec["rpc_method"] == "getSchemas"
    assert "Cookie: [REDACTED]" in rec["response_shape"]


def test_refuse_repo_output():
    with pytest.raises(SafetyError):
        write_discovery([], "tempus-discovery.json")
