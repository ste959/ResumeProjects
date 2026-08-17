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


def test_redact_is_a_noop_on_empty():
    assert redact("") == ""
