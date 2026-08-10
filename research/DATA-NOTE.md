# Data Integrity Note
### Trust the inputs, and don't test only on survivors

*Platform sprint 4 · data-quality audit + point-in-time universe · 20 equities (mega-caps + post-2020 IPOs)*

---

## Why this exists

Two failures corrupt more backtests than any modeling error, and both are invisible in the Sharpe:

1. **Dirty data** — an unadjusted split reads as a −50% signal, a stale (repeated) price fakes a smooth
   return, a gap hides a loss. The model didn't find alpha; it found an artifact.
2. **Survivorship bias** — running on *today's* universe silently tests only the names that survived.
   Firms that delisted or went to zero aren't in the sample, so the strategy looks better than it could
   ever have traded.

This sprint adds the two defenses: a **data-quality gate** and a **point-in-time universe**.

## [1] Data-quality audit (`mds/dataquality.py`)

`audit_prices` checks every symbol for coverage, calendar gaps, stale (repeated-price) runs, extreme
one-day jumps (likely unadjusted corporate actions), non-positive prices, and duplicate timestamps, and
returns a boolean `clean` flag so a study can *gate* on it (`assert_clean`). On the real equity set:

```
20 equities → 4 flagged, 0 duplicate dates
  incomplete history (IPO/listing — handled by point-in-time): [COIN, RIVN]
  flagged for review (extreme move / stale / non-positive): [HOOD, RBLX]
```

The audit does exactly what an audit should: it **separates incomplete history** (IPOs — not a defect,
the PIT universe handles them) **from moves that need a human** (HOOD/RBLX tripped the jump check — which
here is genuine volatile-IPO price action, *not* an unadjusted split). An audit *flags for review*; it
doesn't silently drop or silently trust.

## [2] Point-in-time universe (`mds/universe.py`)

`PointInTimeUniverse` derives each name's listing/delisting from where its price history actually starts
and ends, exposes **as-of membership**, and carries a `delisting_return` the engine realizes on exit. The
engine (`run(..., universe=...)`) then:

- **masks weights to names listed as of each date** — it cannot look ahead and trade a name before it
  existed (no "I knew NVDA would 10×" via a universe chosen with hindsight);
- **realizes the delisting loss** when a held name exits, instead of the position silently vanishing.

Survivorship audit + PIT vs. naive backtest on the real set:

| | Names | Sharpe | Ann. return |
|---|--:|--:|--:|
| Naive **survivors-only** (13 full-history names, fixed) | 13 | **1.25** | +25.0% |
| **Point-in-time** (grows 15 → 20 as 7 IPOs list) | 20 | 0.90 | +26.9% |

The survivors-only book posts the *higher Sharpe* — the direction survivorship bias always pushes: drop
the messy entrants and the risk-adjusted number flatters. The PIT book earns slightly more return but at
more risk (the volatile IPOs), and only ever holds a name once it has actually listed.

## The honest gap (disclosed)

The exit side — **actually delisted names** — isn't in the free IEX feed, so the classic survivorship
return drag (bankruptcies, buyouts, index deletions) can't be measured here. The **mechanism is built and
unit-tested** (the engine realizes delisting losses; `tests/test_universe.py`), and it correctly handles
the *entry* side on real data. Populating the delisted side needs a paid point-in-time source — the top
item in [`ALPHA-DATA-ROADMAP.md`](ALPHA-DATA-ROADMAP.md). The infrastructure is ready for that data the
day it's available; that's the honest state of it.

## What this demonstrates

- **A data gate, not blind trust.** The audit catches the artifacts that fake alpha and, crucially,
  *distinguishes* incomplete history from real defects rather than lumping them.
- **Point-in-time discipline in the engine itself.** Membership and delisting are enforced in the
  backtest loop, so no strategy on the platform can accidentally trade on hindsight-selected survivors.

Reproduce with `python run_data.py` (see [`REPRODUCE.md`](REPRODUCE.md)); the audits are pure and
unit-tested in `tests/test_dataquality.py` and `tests/test_universe.py`.
