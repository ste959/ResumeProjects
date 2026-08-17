"""Result and report schema for the validation harness.

Every scenario a lab runs produces a :class:`ScenarioResult`; a whole run produces a
:class:`RunReport`. Both serialise to the formats a validation pipeline actually consumes:

* **NDJSON** — one result object per line, for streaming into a telemetry/log store.
* **JUnit XML** — the lingua franca of CI systems, so a run drops straight into any build dashboard.
* **JSON** — the full run report (results + environment fingerprint) for archival and diffing.

Keeping the schema explicit and versioned is what makes results *comparable* across machines and over
time — the whole point of a readiness lab.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from enum import Enum

SCHEMA_VERSION = 1

# Characters that are illegal in XML 1.0 even escaped; a binary-ish SUT emitting them would otherwise
# produce a junit.xml that the CI parser rejects.
_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xml_safe(text: str) -> str:
    return _XML_ILLEGAL.sub("", text or "")


class Status(str, Enum):
    PASS = "PASS"      # ran and every check passed
    FAIL = "FAIL"      # ran but a check failed (a real defect in the system under test)
    ERROR = "ERROR"    # the harness/adapter itself failed to run the scenario (infra fault)
    SKIP = "SKIP"      # deliberately not run (precondition not met — e.g. device absent)


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one assertion against a scenario's output."""
    name: str
    ok: bool
    detail: str = ""


@dataclass
class ScenarioResult:
    id: str
    status: Status
    duration_ms: float
    seed: int = 0
    attempts: int = 1
    metrics: dict[str, float] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    repro: str = ""            # how to reproduce this exact run (command or callable + seed)
    started_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class RunReport:
    run_id: str
    suite: str
    environment: dict
    results: list[ScenarioResult]
    started_at: str = ""
    duration_ms: float = 0.0
    schema_version: int = SCHEMA_VERSION

    # -- rollups -------------------------------------------------------------
    def counts(self) -> dict[str, int]:
        c = {s.value: 0 for s in Status}
        for r in self.results:
            c[r.status.value] += 1
        return c

    @property
    def passed(self) -> bool:
        """True only if there was at least one result and nothing failed or errored (skips are fine).
        An empty run is NOT a pass — a suite that loaded nothing (bad --suite, an over-aggressive
        --tag/--quarantine) must not exit 0 as a false green."""
        return bool(self.results) and all(r.status in (Status.PASS, Status.SKIP) for r in self.results)

    # -- serialisation -------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "suite": self.suite,
            "schema_version": self.schema_version,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "environment": self.environment,
            "counts": self.counts(),
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_ndjson(self) -> str:
        """One JSON object per line: a run header, then one line per scenario result."""
        header = {"type": "run", "run_id": self.run_id, "suite": self.suite,
                  "schema_version": self.schema_version, "environment": self.environment,
                  "counts": self.counts()}
        lines = [json.dumps(header, default=str)]
        for r in self.results:
            row = r.to_dict()
            row["type"] = "result"
            row["run_id"] = self.run_id
            lines.append(json.dumps(row, default=str))
        return "\n".join(lines) + "\n"

    def to_junit_xml(self) -> str:
        """A JUnit ``testsuite`` — FAIL → <failure>, ERROR → <error>, SKIP → <skipped>."""
        counts = self.counts()
        suite = ET.Element("testsuite", {
            "name": self.suite,
            "tests": str(len(self.results)),
            "failures": str(counts["FAIL"]),
            "errors": str(counts["ERROR"]),
            "skipped": str(counts["SKIP"]),
            "time": f"{self.duration_ms / 1000:.3f}",
        })
        for r in self.results:
            case = ET.SubElement(suite, "testcase", {
                "name": r.id, "classname": self.suite, "time": f"{r.duration_ms / 1000:.3f}",
            })
            if r.status is Status.FAIL:
                failed = [c for c in r.checks if not c.ok]
                msg = "; ".join(f"{c.name}: {c.detail}" for c in failed) or "check failed"
                ET.SubElement(case, "failure", {"message": _xml_safe(msg)}).text = _xml_safe(r.stderr[-2000:])
            elif r.status is Status.ERROR:
                ET.SubElement(case, "error", {"message": _xml_safe(r.error or "error")}).text = _xml_safe(r.stderr[-2000:])
            elif r.status is Status.SKIP:
                ET.SubElement(case, "skipped")
        return ET.tostring(suite, encoding="unicode")
