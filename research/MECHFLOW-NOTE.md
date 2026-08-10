# Shadow of the Machines
### A novel structural edge — invented, mechanistically confirmed, and then honestly refuted by my own monitor

*Overnight reversal of leveraged-ETF forced rebalancing · 9 underlyings with leveraged complexes · 2020-07 – 2026-07*

---

## The idea (original construction)

Stop forecasting other forecasters — **model the machines.** A growing share of volume is price-insensitive
and mechanical. Leveraged & inverse ETFs *must* rebalance to hold constant leverage, and every one of them
trades in the **same direction as the day's move** at the close: a k-times fund trades `k·(k−1)·AUM·r`, and
`k(k−1) > 0` for every k∉{0,1} (3× → 6, −3× → 12, 2× → 2). This forced flow pushes the closing print past
fair value with **no information behind it**, so the overshoot should **revert overnight** — and you get
paid to absorb it.

**The falsifiable, novel prediction:** the reversal should scale with **forced flow ÷ underlying liquidity** —
negligible in a deep name like SPY, large in semis/Nasdaq names whose leveraged complexes dwarf the tape.
And a durability thesis worth its own test: unlike a published anomaly, this edge's *source grows* as
markets get more passive — so it should resist crowding.

## [1] The mechanism is real

Regressing each underlying's overnight return on its own close-to-close move (negative β = reversal), sorted
by relative forced flow:

| Underlying | rel. flow | overnight β | t |
|---|--:|--:|--:|
| SOXX (semis) | 510 | −0.027 | −1.7 |
| QQQ | 378 | −0.005 | −0.3 |
| TLT | 331 | −0.034 | −1.8 |
| … | | | |
| **SPY** | **67** | **+0.000** | **0.0** |
| XLE | 11 | +0.047 | +2.9 |

**corr(relative flow, reversal strength) = +0.47** — the structural prediction holds: higher forced flow →
more overnight reversal. And the cleanest confirmation is **SPY: essentially zero reversal** — exactly as
predicted, because SPY is far too liquid for ETF rebalancing to move. The machines measurably move price,
and they move the *illiquid* ones.

## [2] …but it is not a tradable taker edge

A dollar-neutral overnight-reversal book, tilted to high-forced-flow names:

| | Excess Sharpe | HAC t | Turnover |
|---|--:|--:|--:|
| Gross (no cost) | −0.18 (CI [−1.00, +0.65]) | −0.4 | 336× |
| Net (3 bps) | −1.73 | −4.2 | 336× |

Gross is statistically **indistinguishable from zero**, and at 336×/yr turnover a taker crossing the spread
twice a night gives back far more than the effect — a textbook "real mechanism, not a tradable taker edge"
(the reversal belongs to whoever is already resting at the close, i.e. a market maker).

## [3] The decay monitor refuted my own durability thesis

I predicted the edge would *persist* because its source grows. The monitor said the opposite:

- First-half excess Sharpe **+0.61 → second-half −0.91**; decay slope **t −2.0**.
- Bucketed Sharpe: +0.20 → +1.07 → +0.53 → −0.26 → **−1.75** → −0.54.
- **VERDICT: DECAYED** — it worked in 2020–22 and was arbitraged out (even reversed) by 2023–26.

**Crowding outran the growing source.** My clever durability story was wrong, and the tool I built to police
exactly this caught it.

## Why this is the strongest thing in the project

It's the whole researcher's job compressed into one study:

1. **Invent** a genuinely novel, structural, falsifiable hypothesis (not a data-mined pattern) — modeling the
   forced flow of the machines.
2. **Confirm the mechanism** with a clean cross-sectional prediction that holds (reversal ∝ flow÷liquidity;
   SPY null as predicted).
3. **Refuse to fool yourself** — the tradable edge is null-to-costly, and, most importantly, I used my *own*
   decay monitor to **disprove my own optimistic thesis.**

A candidate who invents an edge is common. A candidate who invents one, finds real support for the
mechanism, and then *dismantles their own durability claim with a tool they built for it* — that is the risk-
prevention discipline a desk actually hires for. **Inventing the idea is easy; having the discipline to
disprove it is the job.**

Reproduce with `python run_mechflow.py` (see [`REPRODUCE.md`](REPRODUCE.md)); the mechanics are pure and
unit-tested in `tests/test_mechflow.py`.
