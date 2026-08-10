# The Absent Buyer
### Finding edge in *regulation* — a creative structural idea, refuted, with the confound diagnosed

*Buyback-blackout study · 88 large-caps · SEC-EDGAR filing dates + repurchase facts · 2020-07 – 2026-07*

---

## The idea (edge in regulation — the differentiated part)

Corporate buybacks are the **largest, most price-insensitive buyer of US equities** (net repurchases have
exceeded household + institutional net buying for much of the last decade). But firms go **dark on
repurchases in the ~weeks before earnings** — a self-imposed blackout under insider-trading law / 10b5-1
practice. So on a predictable, recurring **quarterly schedule**, a stock with a large active buyback
program **loses its dominant price-insensitive buyer**, then gets it back. Prediction: stocks underperform
in their own blackout, and the drag grows with buyback intensity.

Looking for alpha in a *regulatory constraint* — not a price pattern — is the market knowledge most
candidates never bring. The build is real and point-in-time:
- **Blackout anchor = the SEC 10-Q/10-K filing date** (precise, free from EDGAR; a 10-Q is filed within days
  of the earnings release). Blackout window ≈ [filing − 50d, filing − 8d].
- **Buyback intensity = XBRL `PaymentsForRepurchaseOfCommonStock` ÷ market cap**, forward-filled from the
  filing date (no look-ahead).

## The result — refuted

| Buyback tercile | Return in blackout | out of blackout | gap (out − in) |
|---|--:|--:|--:|
| low | +12.9% | +19.7% | +6.7% |
| mid | +22.6% | +16.9% | −5.8% |
| high | +16.4% | +17.4% | +1.0% |

The drag is **not monotonic** in buyback intensity — noise, not the predicted signal. And the strategy
(short in-blackout, dollar-neutral, sized by program intensity) is **significantly *negative* gross**:

| | Excess Sharpe | HAC t | Turnover |
|---|--:|--:|--:|
| Gross (no cost) | **−1.04** | **−2.7** | 22× |
| Net (10 bps) | −1.38 | −3.6 | 22× |

Shorting in-blackout stocks *lost* — they held up rather than sagged. The thesis, naively implemented,
is refuted.

## The diagnosis — this is the skill

Why did a compelling structural idea fail? Not randomly — for identifiable reasons:

1. **Confound: the blackout window overlaps the pre-earnings run-up.** The blackout *ends just before
   earnings*, and stocks have a well-documented tendency to **drift up into earnings** (pre-announcement
   drift / positioning). That upward drift sits right on top of the blackout window and **dominates** any
   buyback-absence weakness — it even flips the sign. The two windows are entangled; the naive test
   measures their *sum*.
2. **Liquidity, again.** In mega-caps, the buyback is a small share of daily volume, so the buyer's absence
   barely moves price — the same *flow ÷ liquidity* argument that made SPY show no reversal in the
   [mechanical-flow study](MECHFLOW-NOTE.md). The effect, if it exists, lives in **mid-caps** where buybacks
   are a larger share of the tape.
3. **A raging bull (2020–26)** and an admittedly **weak buyback-intensity read** (median 1.6%/yr — the
   annual-only XBRL figure understates program size) blur the sort further.

The refinement it points to is concrete: **neutralize the pre-earnings-drift window** (regress it out, or
trade only the early part of the blackout that doesn't overlap the run-up) and **move down-cap**.

## What this demonstrates

- **Differentiated sourcing** — hunting edge in a *regulatory* constraint and building it point-in-time
  from raw SEC filings (blackout from filing dates, intensity from XBRL repurchase facts). Almost no junior
  project looks here.
- **The rarest skill: diagnosing a failure precisely.** A null is common; identifying that the signal
  window is *confounded with pre-earnings drift* and that the effect is *liquidity-gated to mid-caps* — and
  naming the exact refinement — is the researcher's actual job. Inventing the idea is the easy half.

Reproduce with `python run_buyback.py` (needs internet for EDGAR, cached after first run; see
[`REPRODUCE.md`](REPRODUCE.md)); the analytics are network-free and unit-tested in `tests/test_buyback.py`.
