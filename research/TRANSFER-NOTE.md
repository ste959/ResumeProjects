# Implementation Alpha — the Transfer Coefficient
### The capstone: making a signal you already trust *deployable*, and catching the ones that are fakes

*Cross-sectional 12–1 momentum · 77 large-caps · industry-standard implementation stack · 2020-07 – 2026-07*

---

## The thesis (the résumé's core claim)

Grinold–Kahn's Fundamental Law of Active Management: **IR = IC · √breadth · TC.** Alpha *discovery* moves the
information coefficient (IC); *implementation* moves the **transfer coefficient (TC)** — the fraction of a
signal's theoretical performance that actually survives risk limits, transaction costs, turnover, and
unintended factor bets. For a junior without HFT infrastructure, **TC is where the realistic, defensible edge
is.** The pitch isn't "I found a signal you don't have" — it's *"give me a signal you trust and I'll make more
of it reach the book, and I'll tell you which of your signals are mirages."*

This takes a **standard, decayed signal** — cross-sectional 12–1 momentum on mega-caps — and layers the
techniques a quant trader actually uses, measuring each. **The signal never changes (IC fixed at +0.020); only
the implementation does.**

## The ablation (net of realistic cost)

| Stage | Gross Sh | Net Sh | Max DD | Turnover | Market β |
|---|--:|--:|--:|--:|--:|
| raw signal | 0.24 | 0.20 | −16.4% | 5× | +0.09 |
| + clean (winsor/z-score) | 0.19 | 0.15 | −16.4% | 5× | +0.07 |
| **+ neutralize (β, vol)** | **0.10** | 0.04 | **−10.5%** | 6× | +0.01 |
| + risk sizing (vol-target) | 0.09 | −0.07 | −16.0% | 11× | −0.02 |
| + beta hedge | 0.17 | 0.00 | −15.2% | 11× | +0.01 |
| + turnover control | 0.17 | 0.01 | −12.4% | 10× | +0.01 |

## The scorecard — three things implementation did, and this is the whole pitch

**① Diagnosis — catch the mirage.** Neutralizing the beta/vol tilt cut the *gross* Sharpe **0.24 → 0.10** —
**57% of the raw "alpha" was a hidden factor tilt, not momentum.** Deployed naively, that book is a market/
volatility bet dressed as a stock-selection signal, and it blows up in a factor reversal. Finding that *before*
capital is committed is the risk-prevention half of the job.

**② Deployability — the real wins.** Market beta **+0.09 → +0.01** (genuinely market-neutral, so a PM can size
it without timing the market), and max drawdown **−16% → −12%** (a 24% smaller tail — the neutralization
directly attacks the momentum-crash mechanism, Barroso–Santa-Clara).

**③ Honesty — you can't polish a dead signal.** Net Sharpe **0.20 → 0.01**: on mega-cap momentum (IC 0.020)
there is no real idiosyncratic alpha to transfer, and an honest analysis *says so* rather than curve-fitting a
number. Aggressive vol-targeting even *hurt* (it added turnover, hence cost) — a good implementer applies the
techniques a signal *needs*, not all of them reflexively.

## Why this is the strongest, most hireable demonstration in the project

It's the mature version of the whole pitch, and it's honest to a fault:

- **It's defensible and humble.** No claim of a unicorn. "I maximize the transfer coefficient" is a named,
  respected quantity a QR interviewer knows — it signals *domain mastery*, not modesty-spin.
- **It does both halves of the real job.** *Make good signals better* (market-neutral, smaller tail, cost-aware)
  **and catch the fakes** (57% of the raw Sharpe was a factor tilt) *before they cost the desk money.*
- **It won't oversell.** A senior trusts the candidate who reports "you can't manufacture return on a dead
  signal" far more than one who curve-fits a 2.0 Sharpe. This run *proves* that discipline.

Point the identical stack at a signal with genuine residual alpha and it preserves the alpha while adding the
same risk/execution benefits — which is exactly the value a desk buys: **more of your real edge, reaching the
book, with the mirages filtered out.**

Reproduce with `python run_transfer.py` (see [`REPRODUCE.md`](REPRODUCE.md)); the signal, neutralization, and
implementation layers are pure and unit-tested in `tests/test_implement.py`.
