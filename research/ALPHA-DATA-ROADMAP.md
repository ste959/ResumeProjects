# Alpha Data Roadmap — where the edge actually lives

The research so far has been rigorous and honest, and its verdict is unambiguous: **on 123
survivorship-selected mega-caps with price/volume-only daily bars, no signal is distinguishable
from zero** (best Deflated Sharpe ≈ 0.09, PBO ≈ 0.06, nothing clears a Bonferroni-corrected
|t| > 2.9). That is not a failure of technique — the leakage-free harness, DSR/PBO, HAC/​bootstrap
significance, purge/embargo, and cost/impact realism are all in place. It is the **efficient-market
prior asserting itself on the easiest names with the weakest data.**

The signal is exhausted; the *data* is the constraint. This roadmap is the QR answer to "what next":
four data upgrades, ranked by expected value ÷ effort, each with a concrete free/cheap source, how
it slots into the existing DuckDB/Parquet warehouse, the signals it unlocks, and the point-in-time
discipline required so we don't reintroduce the look-ahead the current layer works so hard to avoid.

Every dataset below flows through the **same** validation gauntlet already built
(`mds/validation.py`, `run_crosssec.py`): leakage-free features, walk-forward with purge/embargo,
Newey–West + block-bootstrap significance, Deflated Sharpe / PBO across the trial family, cost +
impact + neutralization + regime + power. New data doesn't get a lower bar — it gets the same one.

---

## Priority ranking (EV ÷ effort)

| # | Upgrade | Unlocks | Cost | Effort | Priority |
|---|---|---|---|---|---|
| 1 | **Fundamentals (SEC EDGAR)** | value / quality / profitability / accruals — the factors that *actually* survive | **free** | med-high | ✅ **BUILT** — null on mega-caps (breadth-limited) |
| 2 | **Cross-asset macro overlays (FRED, VIX term)** | risk-on/off timing — fixes the regime dependence we found | **free** | low | ✅ **BUILT** — **halves market drawdown** (beta mgmt) |
| 3 | **Breadth (survivorship-free small/mid)** | statistical power + where anomalies actually live | free→$ | med (data-gated) | high — the fix for #1's null |
| 4 | **Crypto L2, wider-spread + cross-venue** | genuine microstructure inefficiency (OFI/VPIN/lead-lag) | **free** | med | high (different game) |
| 5 | **Options-implied (VRP, skew)** | forward-looking vol/sentiment | free live / $ hist | med | ✅ **BUILT (live)** — backtest OPRA-gated |

**Built so far (this batch):** #1 fundamentals (real, point-in-time — still null, the mega-cap/short-sample
ceiling), #2 the macro risk-off overlay (the one thing that materially helps: halves the long-book
drawdown), and #5 the live options surface (skew / IV−RV; historical backtest gated by OPRA). **The two
that remain — and matter most — are #3 breadth and #4 crypto-L2**, because #1's null is a *breadth* problem
(value/quality live in small/mid, not mega-caps) and #4 is where genuine inefficiency is freely observable.

---

## 1. Fundamentals — SEC EDGAR (free, biggest gap)

> **Status — BUILT** (`mds/edgar.py`, `run_fundamentals.py`). Point-in-time via **filing date** (not
> period-end), TTM flows, 123/123 names covered. Factors: earnings-yield, gross-profitability, ROE,
> accruals, asset-growth — all low-turnover (0.003–0.03). **Result: still null on this sample** —
> best is a beta+sector-neutral earnings-yield tilt (net +0.64, HAC t≈1.6), Deflated Sharpe 0.34,
> PBO 0.43; nothing clears the corrected bar. The factors are real in the literature; 123 efficiently-
> priced **mega-caps** over ~6y (≈23 quarterly filings/name) is simply too short and too selected to
> resolve value/quality. This is the honest ceiling — the fix is *breadth* (#3), not the factor.

**Why.** The factors that survive out-of-sample in real research are *fundamental* — value (Fama–
French HML), profitability/quality (Novy-Marx gross profitability, Fama–French RMW), accruals
(Sloan), investment/asset-growth (Cooper–Gulen–Schill). None are buildable from prices. This is the
single largest reason our price-only zoo is null.

**Source (free).** `data.sec.gov` XBRL APIs — `companyfacts` (all standardized us-gaap tags per
company) and `frames` (one tag across all filers for a period), plus the bulk **Financial Statement
Data Sets**. Map CIK↔ticker via SEC's `company_tickers.json`. Tags you need: `Revenues`,
`NetIncomeLoss`, `GrossProfit`, `Assets`, `StockholdersEquity`, `OperatingCashFlow`,
`LiabilitiesCurrent`/`AssetsCurrent`, `DepreciationDepletionAndAmortization`.

**Point-in-time discipline (the make-or-break).** Anchor every fundamental to its **filing date**
(`filed` in the XBRL response), *not* the period-end. Q4 numbers aren't knowable until the 10-K is
filed ~40–75 days later; using period-end is a look-ahead that manufactures fake alpha. Lag to
`filed` + a 1-day buffer, and never let a restatement overwrite the originally-filed value at that
as-of. This mirrors the discipline already in `lob.py`/`crosssec.py`.

**Signals to build.** `E/P, B/P, S/P, FCF/P` (fundamentals ÷ current price), `gross profitability =
GrossProfit/Assets`, `ROE`, `accruals = (ΔNWC − D&A)/Assets`, `asset growth`, `net-issuance`, and
a realized **earnings-surprise / SUE** and YoY-earnings-acceleration proxy (EDGAR gives the
history; no analyst feed needed for a realized version).

**Ingest.** New `mds/edgar.py` → parquet under `research/data/fundamentals/` keyed by (cik, tag,
period, filed), joined to the price panel on (ticker, as-of=filed-lagged). Reuse the DuckDB store.

**Caveat.** Requires a ticker↔CIK map and careful tag normalization (companies use variant tags);
budget time for the point-in-time join. Expected payoff is the highest of anything here.

---

## 2. Cross-asset macro overlays — FRED + VIX term (free, quick win)

> **Status — BUILT** (`mds/macro.py`, `run_macro.py`). Keyless FRED fetch of HY/IG credit OAS + VIX →
> a causal (shifted) risk-appetite score. **Result: the one thing that materially changes a book's
> risk profile** — timing a long-only equity book on the credit/VIX regime **roughly halves its max
> drawdown (−22.8% → −10.1%)** by cutting exposure in blowouts (April-2025 selloff flagged at score 0).
> Honest caveat: it is **beta/risk management, not alpha** — the Sharpe is ~flat (+0.92 → +0.96,
> running at ~0.54 avg exposure), and the timed book's significance is mostly the *equity risk premium*
> of a bull market, not the overlay. It does not help the beta-neutral book (nothing to de-risk).

**Why.** Our single most robust *negative* finding was **regime dependence** — momentum's sign
flipped across years, and vol-management didn't help because realized vol alone is a weak timer.
Forward-looking macro risk indicators are a better conditioning variable, and they're free.

**Source (free).** FRED (`fred.stlouisfed.org`, keyless CSV): **BofA/ICE credit OAS** (`BAMLH0A0HYM2`
HY, `BAMLC0A0CM` IG), Treasury curve (already fetched), `TEDRATE`/SOFR spreads, `VIXCLS`. CBOE/Yahoo
for **VIX futures term structure** (contango/backwardation). We already fetch the Treasury curve, so
the plumbing exists.

**Signals to build.** A **risk-off timer**: scale (or gate) equity gross exposure on HY-spread
*momentum* (widening spreads → de-risk) and on the **VIX term-structure slope** (backwardation →
de-risk) — both far better than the realized-vol `vol_managed` overlay we tested. Cross-sectionally,
condition momentum/quality on the credit regime (defensive factors in risk-off). Also **VRP / IV–RV**
once options land (#5).

**Ingest.** Extend `mds/sources.py` with a FRED fetcher → `research/data/macro/`. Wire as an
*overlay* in `portfolio.py` (a conditioning series), tested exactly like `vol_managed`.

**Why first.** Free, low-effort, and it attacks the exact weakness the current results exposed. Days,
not weeks.

---

## 3. Breadth — survivorship-free small/mid universe

**Why.** 123 mega-caps ≈ a handful of independent bets in the most-arbitraged names; the power
line already says we can't detect a Sharpe below ~1.3. Anomalies (value, low-vol, quality) are
*stronger* in small/mid where limits-to-arbitrage bind — but only measurable on a **point-in-time,
delisting-inclusive** universe. Today's list is pure survivorship bias.

**Source.** True survivorship-free US equities is the one genuinely data-gated item: **CRSP** (gold,
via WRDS/academic), or cheap vendors **Sharadar/Nasdaq Data Link** (~$/mo, survivorship-free with
delistings) or **Norgate/Tiingo**. Free IEX (Alpaca) has **no delisted names**, so it *cannot* fix
this. Interim, free step: expand the Alpaca universe to a few hundred current small/mid caps for more
breadth (still survivorship-biased — label it so).

**Discipline.** As-of index membership (enter at IPO/inclusion, exit at delisting), delisting returns
included, and point-in-time market cap for size buckets. Without delisted names, *every* backtest is
upward-biased — this is the one caveat the current study flags but cannot remove on free data.

**Signals.** The same factors (esp. the #1 fundamentals), now with power and in the regime where they
work; add a genuine **size** factor.

**Priority.** High value, but honest: the real version needs a paid/academic source. Sequence it
after #1 so the fundamentals machinery is ready to point at the broader universe.

---

## 4. Crypto L2 — wider-spread instruments + cross-venue (free, reuses our infra)

**Why.** The microstructure layer already showed BTC has a *real* order-book signal (IC t≈91) that
**can't be monetized** because BTC-USD is a locked 1-tick market with no spread to earn. The edge is
real; it needs venues/instruments where the spread is wide enough to capture — and crypto is the one
place genuine, less-efficient microstructure is *freely* observable at high frequency.

**Source (free).** The existing Java feed infra (`CoinbaseFeedClient`) already captures L2. Point it
at: **alt-coins** (mid-cap tokens with wider spreads), **multiple exchanges** for the same asset
(Coinbase / Binance / Kraken / OKX — free L2 websockets) for cross-venue work, and **Deribit** (free
API) for crypto *options* (a free options surface — bonus for #5).

**Signals.** The strong ones the current crude imbalance only gestures at: **OFI** (Cont–Kukanov–
Stoikov order-flow imbalance from L2 updates — the single best short-horizon predictor), **VPIN**
(flow toxicity / adverse-selection), **microprice/queue dynamics** (Stoikov fair value), **cross-
venue lead-lag** (Hasbrouck information share — monetizable when the lagging venue's spread is wide),
and **cross-asset lead-lag** (BTC → alts). All reuse `lob.py`'s book reconstruction and the maker
study's spread-vs-adverse-selection accounting.

**Monetization.** Wider-spread alts (there's a spread to earn) or cross-venue latency (capture the
lag). The maker/adverse-selection framework is already built to judge whether it survives.

**Caveat.** This is a different, HFT-adjacent game — latency and infra matter, and capacity is small.
But it reuses more of our existing code than anything else here, and the inefficiency is genuinely
there.

---

## 5. Options-implied — VRP, skew, positioning (mostly data-gated)

> **Status — BUILT (live signal)** (`mds/options.py`, `run_options.py`). Alpaca *does* serve options
> data: live snapshots (greeks + IV) fetched for **123/123** names → a cross-section of ATM IV, 25Δ
> put-call **skew**, and **IV−RV** (variance-risk-premium proxy; 63% of names show IV > RV). Highest
> fear (skew): SPGI/GIS/VZ; highest ATM IV: the semis (MU/KLAC/LRCX). The **backtest is the gap** — it's
> a point-in-time surface, and Alpaca's historical `/options/bars` is **OPRA-gated** (403 "OPRA agreement
> not signed") on the free tier. The free path to history is **accruing daily snapshots** (a scheduled
> capture, like the L2 tape) or signing the OPRA agreement. Live signal works today; backtest pending data.

**Why.** Options are *forward-looking* — the one dataset that isn't a lagged function of price.
Implied vol, skew, and the variance risk premium carry information prices don't.

**Source.** The gap: full, clean historical US equity option surfaces are largely paid (ORATS,
IVolatility, OptionMetrics; Alpaca options on paid tiers). **Free-ish:** CBOE end-of-day indices
(VIX, SKEW, put/call ratios), and **Deribit** for a genuinely free *crypto* options surface (pairs
with #4).

**Signals.** **Variance risk premium** (sell vol when IV ≫ RV — one of the most robust risk premia),
**skew / 25-delta put-call** as crash-risk/sentiment, **IV term structure**, **put/call flow** as
positioning, and cross-sectional **IV–RV** in equities. Feed the VIX term structure into the #2
risk-off timer.

**Priority.** High-information but the most data-gated for equities; start with the free crypto
options via Deribit (alongside #4) and CBOE indices, defer full equity surfaces until there's a data
budget.

---

## The through-line

Technique is no longer the bottleneck — it's built and honest. The next unit of research effort
should buy **better data, not more signals**: fundamentals first (free, biggest gap), free macro/
credit overlays for timing (this week), then the crypto microstructure that reuses our own infra.
Each plugs into the existing warehouse and faces the same DSR/PBO/HAC/purge gauntlet — so when
something finally clears that bar, it'll be believable, and `export_target_book.py` will hand it
straight to the (already-built, already-verified) paper-trading loop.

**Complement — make the most of the data you already have.** Alongside the data upgrades, the
**portfolio-construction stack** (`run_construction.py`: `factors` → `riskmodel` → `factortiming` →
`structuring` → `taxaware`, documented in `MARKET-REALISM.md` Phase 7) is the QR's other lever: when
standalone alpha is breadth-limited, the medium-to-long-horizon value is in *combining, risk-modelling,
timing, hedging, and tax-managing*. On the current mega-cap data it already earns its keep — the
risk-model optimizer delivers the same composite alpha at a third the drawdown and a tenth the turnover,
exposure-timing halves the directional drawdown, and HIFO tax management is worth real basis points —
none of which needs a significant standalone signal. Better data (#1–#5) raises the alpha; construction
converts whatever alpha exists into an investable, risk-controlled, after-tax book.
