# Service Level Objectives — OMS order API

This document is the reliability contract for the OMS order API: what we promise, how we measure it, and
how we get told before we break it. It is deliberately small — two SLOs, an error budget, and a
burn-rate alerting policy — because a reliability contract only works if it's simple enough to act on.

## SLIs and SLOs

Both SLIs come from Micrometer's `http_server_requests_seconds` metric (actuator endpoints excluded, so
the objective reflects the API, not health scrapes). The objective window is a rolling **30 days**.

| SLO | SLI (how it's measured) | Target | Error budget |
|---|---|---|---|
| **Availability** | fraction of requests that are **not** `5xx` (a `4xx` is the client's fault, not ours, so it doesn't burn budget) | **99.9%** | 0.1% |
| **Latency** | fraction of requests served in **< 500 ms** (from the histogram `le="0.5"` bucket) | **99% < 500 ms** | 1% |

The **error budget** is the allowance of "bad" the target leaves us: 0.1% of requests over 30 days for
availability (~43 minutes of full outage-equivalent), 1% for latency. Spending budget is normal; the
alerts exist to catch us spending it *too fast to last the month*.

## Burn-rate alerting (multi-window, multi-burn-rate)

A **burn rate** is how many times faster than "even" we're spending the budget: `1x` exactly exhausts it
at the 30-day mark; `14.4x` would exhaust it in ~2 days. Following the Google SRE workbook, each alert
pairs a **long window** (is the burn sustained?) with a **short window** (is it still happening now?), so
a real problem fires fast and a blip doesn't. Both windows must exceed the threshold.

| Alert | Burn rate | Long / short window | Budget spent | Severity |
|---|---|---|---|---|
| `OMSAvailabilityErrorBudgetFastBurn` | 14.4x | 1h / 5m | ~2% in 1h | **page** |
| `OMSAvailabilityErrorBudgetMediumBurn` | 6x | 6h / 30m | ~5% in 6h | **page** |
| `OMSAvailabilityErrorBudgetSlowBurn` | 3x | 1d / 2h | ~10% in 1d | ticket |
| `OMSAvailabilityErrorBudgetSlowestBurn` | 1x | 3d / 6h | trending to miss | ticket |
| `OMSLatencyErrorBudgetFastBurn` | 14.4x | 1h / 5m | ~2% in 1h | **page** |
| `OMSLatencyErrorBudgetMediumBurn` | 6x | 6h / 30m | ~5% in 6h | **page** |

## Where it lives

- **SLI histogram** — enabled in `backend/src/main/resources/application.yml`
  (`management.metrics.distribution` publishes the latency buckets, including the exact `le="0.5"`).
- **Recording + alerting rules** — [`monitoring/rules/slo.rules.yml`](../monitoring/rules/slo.rules.yml),
  loaded by Prometheus via `rule_files` and mounted in `docker-compose.yml`.
- **Rule unit tests** — [`monitoring/rules/slo.rules.test.yml`](../monitoring/rules/slo.rules.test.yml),
  run with `make slo-rules` (`promtool test rules`): they assert the fast-burn page fires on a sustained
  5xx spike and stays quiet on healthy traffic, so the alerting logic itself is tested, not just asserted.
- **Dashboard** — `monitoring/grafana/dashboards/slo.json`: current SLI, error budget remaining, and the
  live burn rate against the 1x / 6x / 14.4x thresholds.

## Responding to a burn alert

1. Confirm scope on the **SLO dashboard** — availability vs latency, and how much budget is left.
2. A `page` means the budget is being spent fast enough to breach within hours to a day — mitigate first
   (roll back the last deploy, shed load, trip the venue circuit breaker), diagnose second.
3. A `ticket` means the trend will miss the SLO if unaddressed — fix within the budget's timescale.
4. If the budget is exhausted, the error-budget policy applies: freeze risk-bearing changes and spend the
   next cycle on reliability until the budget recovers.
