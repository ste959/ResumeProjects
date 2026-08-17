"""Telemetry: fingerprint shape, timing, and confidential-data redaction."""

from __future__ import annotations

from harness.telemetry import Timer, environment_fingerprint, redact


def test_fingerprint_has_the_comparability_keys():
    fp = environment_fingerprint()
    for key in ("os", "arch", "python", "cpu_count", "captured_at"):
        assert key in fp
    assert "host" not in fp                    # off by default (partner privacy)
    assert "host" in environment_fingerprint(include_host=True)


def test_timer_measures_elapsed():
    with Timer() as t:
        sum(range(10000))
    assert t.ms >= 0.0


def test_redact_masks_secrets_and_pii():
    text = ("api_key=abc123 bearer eyJshhh contact ops@corp.com "
            "host 10.0.0.5 path /Users/alice/proj")
    out = redact(text, home="/Users/alice")
    assert "abc123" not in out and "eyJshhh" not in out
    assert "ops@corp.com" not in out and "10.0.0.5" not in out
    assert "/Users/alice" not in out and "~/proj" in out
    assert "<redacted-email>" in out


def test_redact_masks_project_and_vendor_key_formats():
    text = ("APCA_API_KEY_ID=PK12345ABCDE "                 # the repo's own env var (KEY is a middle part)
            "AKIAIOSFODNN7EXAMPLE ghp_abcdefghij1234567890 "
            "-----BEGIN PRIVATE KEY-----\nMIIsecretbytes\n-----END PRIVATE KEY-----")
    out = redact(text)
    assert "PK12345ABCDE" not in out
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "ghp_abcdefghij1234567890" not in out
    assert "MIIsecretbytes" not in out


def test_redact_does_not_mask_ordinary_words():
    assert "monkey" in redact("the monkey ate a banana")   # case-sensitive env-var rule, not prose


def test_redact_is_a_noop_on_empty():
    assert redact("") == ""
