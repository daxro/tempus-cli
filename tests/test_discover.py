import pytest

from tempus_cli.discover import record_request, write_discovery
from tempus_cli.errors import SafetyError


def test_record_request_redacts_query_and_extracts_rpc():
    rec = record_request("POST", "https://x/y?token=secret", "7|0|4|base|perm|svc|getSchemas|1|", "Cookie: a=b")
    assert rec["path"] == "/y"
    assert rec["rpc_method"] == "getSchemas"
    assert "Cookie: [REDACTED]" in rec["response_shape"]


def test_refuse_repo_output():
    with pytest.raises(SafetyError):
        write_discovery([], "tempus-discovery.json")
