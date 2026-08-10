# Multi-Factor Note
### The institutional shot at a real edge — an honest null, and a market-structure insight worth more

*Diversified market-neutral multi-factor book · ~135 large-caps · 2004–2026 (~22y, yfinance) · $100M scale*

---

## The attempt

With the new long-history + broad-universe data, both forces a real cross-sectional factor edge needs are
finally present: **statistical power** (20 years → min-detectable Sharpe ≈ 0.6) and **breadth** (IR =
IC·√breadth). So this is the honest institutional shot — a **diversified, market-neutral, capacity-aware**
book combining the price-only factors that actually replicate: **momentum (12–1)**, **low-volatility**, and
**short reversal**, run through the full deployment stack (characteristic-neutral, market-β-hedged,
vol-targeted, turnover-controlled). Not a $1k covered-call gimmick — a $100M institutional book.

## The result — no variant clears the bar

| Book (market-neutral, gross) | Excess Sharpe | HAC t | Max DD | Market β |
|---|--:|--:|--:|--:|
| momentum | 0.16 | 0.7 | −33% | 0.00 |
| **low-vol** | **−0.76** | **−3.7** | **−67%** | −0.05 |
| reversal | 0.13 | 0.6 | −21% | +0.04 |
| mom + lowvol | −0.08 | −0.4 | −38% | −0.02 |
| **mom + lowvol + rev** | **0.17** | 0.8 | −16% | +0.01 |

Gauntlet: best is mom+lowvol+rev at HAC t 0.8 — **fails** the multiple-testing bar (min-detectable 0.61).
Out-of-sample (2006–2019, pre-registered) it's +0.08; the decay monitor calls it stable-to-improving. All
honest, all insignificant.

## The insight that's worth more than the null

The revealing failure is **low-vol: significantly *negative* (−0.76, −67% drawdown)** — which looks like
"the low-vol anomaly is dead," but is actually a **survivorship artifact**, and understanding *why* is the
senior-level result:

> The low-volatility premium is **paid by high-vol names that blow up.** A current-constituents universe
> (all yfinance gives for free) has **removed exactly those names**, leaving only the surviving high-vol
> *winners* (NVDA and friends) — which the low-vol factor *shorts*. So this universe is **structurally
> biased *against* low-vol** (you're short the survivors) and mildly *for* momentum (survivors trended up).

That's the non-obvious point most people miss: **survivorship bias doesn't inflate every factor — it
distorts them in *opposite* directions.** It flatters momentum and *destroys* low-vol. Which means a
survivorship-biased universe can neither confirm nor fairly test these premia.

## The honest conclusion

Price-based factors on liquid large-caps are decayed to insignificance even over 20 years, *and* free
survivorship-biased data distorts them, so it can't answer the question. **A survivorship-free feed isn't a
nicety here — it's the requirement**, and it's the one thing standing between this rigorous, capacity-aware,
institutional-scale machine and a factor premium you could size with conviction. The point-in-time
universe machinery (`universe.py`) is already built for the day that data arrives.

## What this demonstrates

- **The institutional construction is right** — diversified, market-neutral, β-hedged, capacity-aware, and
  judged by a selection-aware gauntlet across a pre-registered hold-out. This is how a desk builds a factor
  book, not how a retail account sells calls.
- **Diagnosing *why* the data can't answer is the skill.** "Low-vol is negative *because* survivorship
  removed the blow-ups the premium is paid by" is precisely the kind of data-quality reasoning that
  separates a researcher from someone who'd have reported the −0.76 as a finding.

Reproduce with `python run_multifactor.py` (free yfinance data; see [`REPRODUCE.md`](REPRODUCE.md)); factor
logic is unit-tested in `tests/test_multifactor.py`.
