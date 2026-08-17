"""Tamper-evident seals: intact verify, altered/added/removed/reordered detection with pinpointing,
timing/log changes tolerated, and HMAC authenticity."""

from __future__ import annotations

import copy

from harness.adapters import CallableAdapter
from harness.checks import MetricThreshold
from harness.integrity import Seal, seal_report, verify_report
from harness.runner import run_suite
from harness.scenario import Scenario, Suite


def _report():
    suite = Suite("s", [
        Scenario("a", CallableAdapter(lambda s: {"m": 10.0}), checks=[MetricThreshold("m", ">", 1)]),
        Scenario("b", CallableAdapter(lambda s: {"m": 20.0}), checks=[MetricThreshold("m", ">", 1)]),
    ])
    return run_suite(suite).to_dict()


def test_intact_report_verifies():
    rd = _report()
    seal = seal_report(rd)
    result = verify_report(rd, seal)
    assert result.ok and result.integrity_ok and result.tampered_at is None


def test_altered_metric_is_detected_and_pinpointed():
    rd = _report()
    seal = seal_report(rd)
    rd["results"][1]["metrics"]["m"] = 999.0             # fudge b's metric
    result = verify_report(rd, seal)
    assert not result.ok and not result.integrity_ok and result.tampered_at == "b"


def test_flipping_a_status_is_detected():
    rd = _report()
    seal = seal_report(rd)
    rd["results"][0]["status"] = "PASS"                  # (already PASS) — now really change a check
    rd["results"][0]["checks"][0]["ok"] = False
    assert not verify_report(rd, seal).integrity_ok


def test_removed_added_and_reordered_results_are_detected():
    rd = _report()
    seal = seal_report(rd)

    removed = copy.deepcopy(rd); removed["results"].pop()
    assert verify_report(removed, seal).tampered_at == "b"

    added = copy.deepcopy(rd); added["results"].append(copy.deepcopy(rd["results"][0]))
    added["results"][-1]["id"] = "c"
    assert verify_report(added, seal).tampered_at == "c"

    reordered = copy.deepcopy(rd); reordered["results"].reverse()
    assert not verify_report(reordered, seal).integrity_ok


def test_timing_and_log_changes_do_not_break_the_seal():
    rd = _report()
    seal = seal_report(rd)
    rd["results"][0]["duration_ms"] = 99999.0            # non-material fields
    rd["results"][0]["started_at"] = "2099-01-01T00:00:00Z"
    rd["results"][0]["stdout"] = "different logs"
    assert verify_report(rd, seal).ok                    # verdict unchanged → seal holds


def test_hmac_seal_authenticity():
    rd = _report()
    signed = seal_report(rd, key="s3cret")
    assert signed.signed and signed.algo == "hmac-sha256-chain"

    assert verify_report(rd, signed, key="s3cret").authenticity_ok is True
    wrong = verify_report(rd, signed, key="wrong")
    assert wrong.authenticity_ok is False and not wrong.ok  # forged/wrong key rejected

    no_key = verify_report(rd, signed)                       # integrity checkable, authenticity unknown
    assert no_key.authenticity_ok is None and no_key.integrity_ok


def test_seal_round_trips_through_disk(tmp_path):
    rd = _report()
    seal = seal_report(rd, key="k")
    path = seal.save(tmp_path / "seal.json")
    reloaded = Seal.load(path)
    assert reloaded.chain_head == seal.chain_head and reloaded.signature == seal.signature
    assert verify_report(rd, reloaded, key="k").ok
