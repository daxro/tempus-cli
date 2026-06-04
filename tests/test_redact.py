from tempus_cli.redact import redact_text


def test_redacts_personnummer_and_tokens_and_cookies():
    text = "Cookie: a=b\nSet-Cookie: SID=secret; Path=/\n198001011234 abcdefabcdefabcdefabcdefabcdefab"
    out = redact_text(text)
    assert "[REDACTED_PNR]" in out
    assert "Cookie: [REDACTED]" in out
    assert "SID=[REDACTED]" in out
    assert "[REDACTED_TOKEN]" in out


def test_redacts_sensitive_query_values():
    out = redact_text("https://x/y?SAMLTRANSACTIONID=abc&schemaId=399&keep=ok")
    assert "SAMLTRANSACTIONID=%5BREDACTED%5D" in out
    assert "schemaId=%5BREDACTED%5D" in out
    assert "keep=ok" in out
