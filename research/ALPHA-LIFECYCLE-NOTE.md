# Alpha-Lifecycle Note
### A structural edge, and the monitor that tells you when it's dying (or was never alive)

*Structural OPEX effect + alpha-decay/crowding monitor · SPY/QQQ/IWM · 2020-07 – 2026-07*

---

## The thesis

No edge is permanent, and a large institution doesn't survive on one durable signal — it runs a *factory*
of many small, individually-decaying edges and wins by **detecting decay early, sizing to capacity, and
retiring edges before they bleed.** The durable asset isn't the signal; it's the **control system** that
manages the alpha lifecycle. This note builds that control system and stress-tests it on a genuinely
*structural* edge candidate.

## Why OPEX is a structural (not statistical) candidate

Options dealers hedge **mechanically, not by choice**: when net long gamma they sell strength / buy
weakness — damping volatility and pinning the underlying toward large-open-interest strikes into monthly
expiry; when that gamma **rolls off** the third Friday, the damping vanishes. Because the hedging is a
*mandate*, not a bet, the price footprint doesn't arbitrage away the way a statistical pattern does. The
clean, backtestable handle is the **OPEX calendar phase** (needs only daily prices). *(True dealer Gamma
Exposure needs option open interest by strike, which the free feed lacks — so the repo computes the
Black–Scholes-gamma methodology and a volume-proxy concentration for illustration, clearly labeled, not as
a backtest input.)*

## Three honest findings, stacked

**[1] The effect is real but the textbook sign REVERSED.** Return by OPEX phase, 2020–26:

| Phase | SPY | QQQ | IWM |
|---|--:|--:|--:|
| opex_week | −3.2%/yr (t−0.3) | +2.3% (t+0.1) | −4.9% (t−0.3) |
| **post_opex** | **+35.8%/yr (t+2.8)** | **+45.0% (t+2.6)** | **+34.1% (t+1.9)** |
| rest | +17.7% (t+1.7) | +17.3% | +16.8% |

The literature documents post-OPEX *weakness* (gamma-support roll-off). In this sample it's the **strongest**
phase — the anomaly decayed and **inverted** as it crowded (once everyone shorts post-OPEX, the effect
flips: McLean–Pontiff post-publication decay, in miniature). With ~72 monthly cycles and three phases ×
three indices, this is suggestive, not established — the honest read is "regime-dependent, sign-unstable."

**[2] So the textbook trade LOSES.** Trading the published version — flat in the post-OPEX week — on SPY:

| | Excess Sharpe | Ann. ret | Max DD |
|---|--:|--:|--:|
| OPEX-timing (flat post-OPEX) | 0.44 | +8.8% | −26.7% |
| Always-long (buy & hold) | **0.80** | +16.1% | −24.5% |

Sitting out the (now-strongest) phase underperforms — a live lesson in why you never trade a published edge
on faith.

**[3] The monitor makes the decisive catch: it's beta, not alpha.** Running the timing overlay through the
alpha-decay/crowding monitor:

- No decay signature (bucketed Sharpe is noisy but not trending down) — a naive read would call it "robust."
- But the **crowding detector** flags the real problem: the overlay is **+0.90 correlated to SPY and rising
  (t+30)**. What looks like a timing edge is **market exposure wearing an alpha costume** — a long-equity
  book with a small calendar tilt, not an independent source of return.

> **Monitor verdict:** *BETA-DOMINATED — +0.90 correlation to the factor and rising: this is market
> exposure wearing an alpha costume, not an independent edge.*

## The monitor (`mds/decaymonitor.py`) — the actual deliverable

Given any strategy's returns (and an optional factor to test crowding against), it reports the **alpha
health**: bucketed-Sharpe **decay slope** and t-stat, an estimated **half-life** (∞ if not decaying) and
**sessions-to-zero**, first-half vs. second-half Sharpe, **IC decay** for signal-based edges, and the
**crowding trend** (rising correlation to a known factor). It answers the only question that matters before
deploying capital — *"will this still be here in six months, and is it even real?"* — with evidence.

## Why this is the standout

Most candidates show a backtest and hope it holds. This shows the **discipline institutions actually run
on**: a real structural hypothesis, an honest measurement that it *decayed and inverted*, a demonstration
that trading it naively loses, and a monitor that catches a false positive (beta masquerading as alpha)
that would have fooled a naive researcher. **Finding an edge is half the job; proving what *isn't* one —
and knowing when a real one is dying — is the other half.** That is the risk-prevention mindset a desk hires
for, and it's the part almost no junior project demonstrates.

Reproduce with `python run_opex.py` (see [`REPRODUCE.md`](REPRODUCE.md)); the calendar, gamma, and monitor
math are pure and unit-tested in `tests/test_opex.py` and `tests/test_decaymonitor.py`.
