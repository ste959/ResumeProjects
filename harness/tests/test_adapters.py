"""Adapters: in-process capture + isolation, and subprocess exit/timeout/contract parsing."""

from __future__ import annotations

import sys

from harness.adapters import CallableAdapter, CommandAdapter


def test_callable_adapter_captures_metrics():
    out = CallableAdapter(lambda seed: {"seed": seed, "val": 3.0}).run(7)
    assert out.ok and out.exit_code == 0
    assert out.metrics == {"seed": 7, "val": 3.0}


def test_callable_adapter_isolates_exceptions():
    def boom(seed):
        raise RuntimeError("kaboom")
    out = CallableAdapter(boom).run(0)
    assert not out.ok and "kaboom" in out.error


def test_command_adapter_parses_result_contract_and_passes_seed():
    prog = ("import os, json;"
            "print('LAB_RESULT ' + json.dumps({'seed_echo': int(os.environ['LAB_SEED']), 'n': 5}))")
    out = CommandAdapter([sys.executable, "-c", prog]).run(123)
    assert out.ok and out.exit_code == 0
    assert out.metrics == {"seed_echo": 123, "n": 5}


def test_command_adapter_reports_nonzero_exit_but_still_ran():
    out = CommandAdapter([sys.executable, "-c", "import sys; sys.exit(3)"]).run(0)
    assert out.ok and out.exit_code == 3          # it ran; judging the exit code is a check's job


def test_command_adapter_missing_binary_is_infra_fault():
    out = CommandAdapter(["this_binary_does_not_exist_zzz"]).run(0)
    assert not out.ok and out.error


def test_command_adapter_timeout_is_infra_fault():
    out = CommandAdapter([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.3).run(0)
    assert not out.ok and "timeout" in out.error
