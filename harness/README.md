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

## Reliability heart: flakiness gate + repro bundles

A validation suite is only trustworthy if it's itself reliable, and a failure is only actionable if you
can reproduce it. Two capabilities cover that:

- **Determinism / flakiness gate** (`reliability.py`) — run each scenario *N* times under its seed and
  classify it: `stable_pass`, `stable_fail` (a real, reproducible defect — not flakiness), `flaky` (the
  verdict changed between runs — the enemy), or `skipped`. It also reports which *metrics* varied in
  value (a timing metric varying is expected; a computed result varying is a determinism bug), without
  failing the gate on that. Flaky scenarios are **quarantined** by tag rather than left to fail
  intermittently.
- **Repro bundles** (`repro.py`) — on any FAIL/ERROR, write a self-contained bundle: `bundle.json`
  (seed, config, environment fingerprint, which checks failed, metrics), the captured (**redacted**)
  `stdout.log`/`stderr.log`, and a `REPRODUCE.txt` with the exact seed-pinned command to re-run it.

```bash
python -m harness --out artifacts                  # run the suite; write ndjson/junit/json; exit 0/1
python -m harness --repro-dir repro                 # …and drop a repro bundle for each FAIL/ERROR
python -m harness --check-determinism --repeats 5   # flakiness gate: fail if any verdict is unstable
python -m harness --quarantine flaky                # skip scenarios tagged 'flaky'
python -m pytest harness -q                          # the harness's own tests (57)
```

## Quality gates: golden baselines + regression thresholds

Capture a run as a **baseline**, then gate later runs against it (`baseline.py`). Three regression
kinds, judged by what's actually portable:

- **Status** — a scenario that passed now fails. Gated everywhere.
- **Accuracy** (`exact` rule) — a deterministic metric drifted beyond an absolute tolerance. Gated
  everywhere, because a seeded computation must reproduce on any machine.
- **Performance** (`higher`/`lower` rule) — a throughput/latency metric moved the wrong way beyond a
  relative tolerance. **Gated only on comparable hardware:** a perf baseline from one CPU can't fairly
  judge a run on another, so across a hardware mismatch these become *drift notes*, not failures.

That split is the honest core of "comparable results across a hardware ecosystem" — status and accuracy
travel, raw performance doesn't, and the gate says so instead of pretending. A per-suite `POLICY`
(metric → rule) travels with the suite.

```bash
python -m harness --capture-baseline baseline.json   # snapshot the golden results
python -m harness --baseline baseline.json           # gate a later run; regression → non-zero exit
```

## Configuration matrix

Run one suite across a matrix of configurations (`matrix.py`) — the OEM / silicon / driver / power-mode
analog — and aggregate the runs into a comparable grid. A configuration is injected as environment
variables for the duration of its run (saved and restored around it), so it reaches both external SUTs
(subprocesses inherit the environment) and in-process ones, with no change to any scenario.

The grid's most valuable output is the set of **config-dependent failures** — scenarios that pass under
some configurations and fail under others. Those are exactly the findings a matrix exists to surface:

```
  scenario            default     fast      safe
  ------------------------------------------------
  probe                 PASS      PASS      PASS
  needs_high_budget     FAIL      FAIL      PASS    ◀ diverges
```

```bash
python -m harness --matrix                            # run across a MATRIX beside the suite
python -m harness --matrix mymod:MATRIX --out out     # explicit matrix; write matrix.json
python run_matrix.py                                  # self-contained demo (comparable metrics + divergence)
```

## Tamper-evident results

When a partner runs the suite on their hardware and submits results, those results have to be
trustworthy. A run can be **sealed** (`integrity.py`): each result's material verdict (id, status, seed,
metrics, checks — not timing or logs) is hashed and hash-chained, and the chain head is recorded.
Re-verifying recomputes the chain and, on a mismatch, **pinpoints the first altered result**.

Two honestly-distinct levels:

- **Integrity** (`sha256-chain`) — any altered / added / removed / reordered result is detected, *if the
  seal is anchored somewhere the tamperer can't also rewrite* (published, or held by the verifier).
- **Authenticity** (`hmac-sha256-chain`, opt-in) — the seal is HMAC-signed with a secret `LAB_SEAL_KEY`
  (environment only, never committed), so a party without the key can't forge a valid seal over altered
  results.

```bash
python -m harness --out artifacts --seal              # write artifacts/seal.json (signed if LAB_SEAL_KEY set)
python -m harness --verify artifacts/report.json      # recompute + check; non-zero exit if tampered
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

1. ~~**Reliability heart** — determinism/flakiness gate + repro bundles.~~ **Built** (see above).
2. ~~**Quality gates** — golden baselines + performance-regression thresholds.~~ **Built** (see above).
3. ~~**Config-matrix orchestration** — run the suite across a matrix of configurations.~~ **Built** (see above).
4. ~~**Security depth** — tamper-evident, hash-chained run records.~~ **Built** (see above). *Roadmap complete.*
