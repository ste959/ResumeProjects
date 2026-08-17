# Validation Harness — a deterministic "readiness lab"

A small, dependency-free framework for validating a **system under test (SUT)** the way a hardware
readiness lab does: run packaged scenario collateral, drive the SUT through pluggable adapters, assert
checks, and emit **comparable, machine-readable results** — with deterministic execution and a CI exit
gate. Pure Python standard library; runs anywhere with a `python`.

```
 packaged suite ──▶  deterministic RUNNER  ──▶  adapter  ──▶ [ in-process function        ]
 (scenario                  │                       └─────▶ [ external command / device   ]
  collateral)               │                                   (drives it, collects LAB_RESULT)
                            ▼
        structured RESULTS + TELEMETRY  →  results.ndjson · junit.xml · report.json
                            │
                    exit code 0 / 1  →  CI quality gate
```

## What's here

| Piece | File | Role |
|---|---|---|
| **Schema** | `schema.py` | Versioned result/report types → NDJSON (telemetry), **JUnit XML** (CI), JSON (archival). |
| **Telemetry** | `telemetry.py` | Environment fingerprint (OS/arch/runtime/commit) for comparability; a timer; **confidential-data redaction** of captured output. |
| **Adapters** | `adapters.py` | The SUT seam: `CallableAdapter` (in-process) and `CommandAdapter` (external process; passes the seed in, collects `LAB_RESULT {json}` from stdout). |
| **Checks** | `checks.py` | Composable assertions: exit-zero, output-contains, metric-present, metric-threshold. |
| **Scenario/Suite** | `scenario.py` | Declarative collateral: SUT + checks + seed + skip precondition. |
| **Runner** | `runner.py` | Deterministic execution, fault isolation, status mapping, artifact writing, exit gate. |
| **CLI** | `__main__.py` | `python -m harness [--suite mod:attr] [--out DIR] [--tag TAG]`. |

## Design guarantees

- **Determinism** — scenarios run in declared order, each under a fixed seed; the seed is also passed to
  external SUTs (`LAB_SEED`) so they can seed themselves. A run is reproducible.
- **Fault isolation** — a scenario whose adapter crashes becomes an `ERROR` *result*; the suite finishes.
- **Correct status** — infra fault (couldn't run the SUT) → `ERROR`; ran but a check failed → `FAIL`;
  precondition not met → `SKIP`. Only `PASS`/`SKIP` are a clean run. This is what makes triage honest.
- **Comparable results** — every run carries an environment fingerprint, so two runs (two machines, two
  dates) can be compared meaningfully.
- **Confidential-data hygiene** — captured stdout/stderr is redacted (secrets, emails, IPs, home paths)
  before it's stored.

## Try it

```bash
python -m harness --out artifacts     # runs the example suite; writes ndjson/junit/json; exits 0/1
python -m pytest harness -q           # the harness's own tests (32)
```

The example suite (`suites/example.py`) drives real, deterministic work: a seeded Monte-Carlo estimate,
a hashing-throughput perf check, an external "station utility" subprocess that emits a result contract,
and an optional scenario that drives the **Java matching engine** as a subprocess when it's been built
(otherwise it `SKIP`s — the way a lab skips a device that isn't present).

## How this maps to a QRT / readiness-lab charter

| Charter need | Here |
|---|---|
| Packaged test collateral, consistent scenarios | `Scenario`/`Suite` — declarative, taggable, countable |
| Harness adapters, runners, result collectors | `CallableAdapter` / `CommandAdapter`; the runner; the `LAB_RESULT` contract |
| Deterministic test execution | fixed seeds (in-proc **and** propagated to external SUTs), ordered runs |
| Diagnostics / reproduction details | env fingerprint + captured (redacted) stdout/stderr + seed per result |
| Telemetry & reporting integrations | NDJSON stream + JUnit XML into CI (`.github/workflows/ci.yml`) |
| Prevent regressions | the exit gate today; golden baselines + perf thresholds next |
| Protect confidential data | output redaction |

## Next layers (the platform, built keystone-first)

This foundation is the schema everything else consumes:

1. **Reliability heart** — a determinism/flakiness gate (run a scenario *N* times, flag nondeterminism,
   quarantine) and **repro bundles** (seed + config + fingerprint + logs + exact re-run command).
2. **Quality gates** — golden-result baselines + performance-regression thresholds → fail CI on a delta.
3. **Config-matrix orchestration** — run the suite across a matrix of configurations, aggregate comparable
   results (the OEM/silicon/driver analog).
4. **Security depth** — tamper-evident, hash-chained run records so results can't be quietly altered.
