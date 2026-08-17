"""Telemetry primitives: an environment fingerprint, a timer, and confidential-data redaction.

Comparable results need a record of *where* they were produced, so every run captures an environment
fingerprint (OS, arch, runtime, code version). And because captured stdout/stderr can carry secrets or
personal paths that must not leave the lab, all captured output is passed through a redactor before it
is stored — a first, deliberate cut at "protecting confidential data".
"""

from __future__ import annotations

import os
import platform
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def environment_fingerprint(*, include_host: bool = False) -> dict:
    """Where these results were produced — enough to make two runs comparable and a result reproducible.

    Host name is opt-in (``include_host``) and off by default, since it can identify a partner machine.
    """
    fp = {
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "runtime": sys.implementation.name,
        "cpu_count": os.cpu_count(),
        "git_commit": _git_commit(),
        "captured_at": now_iso(),
    }
    if include_host:
        fp["host"] = socket.gethostname()
    return fp


class Timer:
    """Context manager measuring wall-clock milliseconds. ``with Timer() as t: ...; t.ms``."""

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        self.ms = 0.0
        return self

    def __exit__(self, *exc) -> None:
        self.ms = (time.perf_counter() - self._start) * 1000.0


# ── confidential-data redaction ──────────────────────────────────────────────
# Deliberately conservative patterns: better to over-mask lab output than to leak a token. Extend per
# environment. Order matters — longer/more-specific patterns first.
_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    # PEM private-key blocks (multiline).
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "<redacted-private-key>"),
    # Any ALL-CAPS env var whose name CONTAINS key/secret/token/password (e.g. APCA_API_KEY_ID, where
    # KEY is a middle component) = value. Case-sensitive so ordinary prose like "monkey" isn't masked.
    (re.compile(r"\b[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|PWD|CREDENTIAL)[A-Z0-9_]*\s*[:=]\s*\S+"),
     "<redacted-credential>"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|token|password|passwd|pwd)\b\s*[:=]\s*\S+"),
     r"\1=<redacted>"),
    # Well-known vendor token shapes (no label needed).
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<redacted-aws-key>"),
    (re.compile(r"\b(?:gh[pousr]|xox[baprs])_[A-Za-z0-9_\-]{10,}"), "<redacted-token>"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"), "<redacted-jwt>"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<redacted-email>"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer <redacted>"),
    (re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"), "<redacted-ip>"),
]


def redact(text: str, *, home: str | None = None) -> str:
    """Mask common secrets/PII in captured output. ``home`` (defaults to the user's home dir) is
    replaced with ``~`` so absolute personal paths don't leak into stored results."""
    if not text:
        return text
    home = home if home is not None else os.path.expanduser("~")
    if home and home != "~":
        text = text.replace(home, "~")
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text
