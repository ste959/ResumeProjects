"""The Absent Buyer — the buyback-blackout structural edge (finding alpha in regulation).

Corporate buybacks are the **largest, most price-insensitive buyer** of US equities. But firms voluntarily
(and effectively, under Rule 10b5-1 / insider-trading law) go **dark on repurchases in the ~weeks before
earnings** — the blackout window. So on a predictable, recurring quarterly schedule, a stock with a large
active buyback program **loses its dominant price-insensitive buyer**, then gets it back. The prediction:
stocks underperform during their blackout, and the effect is **stronger the larger the buyback program**.

The blackout is anchored to earnings; earnings are proxied by the **SEC 10-Q/10-K filing date** (precise and
free from EDGAR — a 10-Q is filed within days of the earnings release). Buyback intensity comes from the
XBRL `PaymentsForRepurchaseOfCommonStock` fact ÷ market cap. Both are point-in-time (known only as of the
`filed` date — no look-ahead). Reuses `edgar.py` for the CIK map and SEC rate-limiting. Pure logic +
EDGAR I/O; the analytics are network-free and unit-tested.
"""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import requests

from . import edgar as ed

BB_TAGS = ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"]
ANCHOR_TAGS = ["Assets", "Liabilities", "StockholdersEquity", "NetIncomeLoss", "Revenues"]
SHARE_TAGS = [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding")]
CACHE = ed.FUND_DIR / "buyback"


# ── EDGAR extraction (filings, repurchases, shares) ───────────────────────────────────────────────
def _fetch_raw(cik: str) -> dict:
    url = ed.FACTS_URL.format(cik=cik)
    for attempt in range(4):
        resp = requests.get(url, headers=ed.HEADERS, timeout=30)
        if resp.status_code == 429:
            time.sleep(1.0 + attempt)
            continue
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()
    return {}


def fetch_buyback_facts(ticker: str, cik: str, refresh: bool = False) -> dict:
    """Per-company: the set of 10-Q/10-K **filing dates** (blackout anchors), the **annual repurchase**
    dollar points (duration ~1yr, to avoid double-counting YTD 10-Q figures), and **shares outstanding** —
    each stamped with its filing date. Cached as a small JSON so the big companyfacts isn't re-downloaded."""
    ed._ensure(CACHE)
    cache = CACHE / f"{ticker}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())
    cf = _fetch_raw(cik)
    gaap = cf.get("facts", {}).get("us-gaap", {})
    dei = cf.get("facts", {}).get("dei", {})

    filings: dict[str, str] = {}                              # filed date → form (10-Q / 10-K)
    for tag in ANCHOR_TAGS:
        if tag in gaap:
            for arr in gaap[tag].get("units", {}).values():
                for o in arr:
                    if o.get("form") in ("10-Q", "10-K") and o.get("filed"):
                        filings[o["filed"]] = o["form"]
            if filings:
                break

    repos = []                                               # annual repurchase $ (duration ~365d)
    for tag in BB_TAGS:
        if tag in gaap:
            for arr in gaap[tag].get("units", {}).values():
                for o in arr:
                    if o.get("val") is None or not o.get("filed") or not o.get("start") or not o.get("end"):
                        continue
                    dur = (pd.Timestamp(o["end"]) - pd.Timestamp(o["start"])).days
                    if 330 <= dur <= 400:                    # keep the annual figure only (clean, no YTD overlap)
                        repos.append({"filed": o["filed"], "val": float(o["val"])})
            break

    shares = []
    for src, tag in SHARE_TAGS:
        d = (dei if src == "dei" else gaap)
        if tag in d:
            for arr in d[tag].get("units", {}).values():
                for o in arr:
                    if o.get("val") and o.get("filed"):
                        shares.append({"filed": o["filed"], "val": float(o["val"])})
            if shares:
                break

    out = {"filings": sorted(filings), "repurchases": repos, "shares": shares}
    cache.write_text(json.dumps(out))
    time.sleep(ed.SEC_RATE_SLEEP)
    return out


def load_buyback_facts(tickers: list[str], refresh: bool = False) -> dict[str, dict]:
    cik = ed.cik_map()
    out = {}
    for t in tickers:
        if t in cik:
            out[t] = fetch_buyback_facts(t, cik[t], refresh=refresh)
    return out


# ── Blackout windows & buyback intensity (network-free, unit-tested) ──────────────────────────────
def _pit_ffill(points: list[dict], index: pd.DatetimeIndex) -> pd.Series:
    """Forward-fill values from their filing dates onto the trading calendar (value at t = latest val whose
    `filed` ≤ t) — point-in-time, no look-ahead."""
    idx = index.tz_localize(None) if index.tz is not None else index
    if not points:
        return pd.Series(np.nan, index=index)
    s = pd.Series({pd.Timestamp(p["filed"]): p["val"] for p in points}).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    out = s.reindex(s.index.union(idx)).ffill().reindex(idx)
    out.index = index
    return out


def blackout_mask(index: pd.DatetimeIndex, filings: list[str], pre_days: int = 50,
                  gap_days: int = 8) -> pd.Series:
    """True on days inside a pre-earnings buyback blackout: for each 10-Q/10-K filing date f (≈ just after
    earnings), the window [f − pre_days, f − gap_days] (roughly 'earnings − 6wk' to 'just before earnings')."""
    idx = index.tz_localize(None) if index.tz is not None else index
    mask = np.zeros(len(idx), dtype=bool)
    days = idx.to_numpy()
    for f in filings:
        f = np.datetime64(pd.Timestamp(f))
        lo, hi = f - np.timedelta64(pre_days, "D"), f - np.timedelta64(gap_days, "D")
        mask |= (days >= lo) & (days <= hi)
    return pd.Series(mask, index=index)


def buyback_yield(facts: dict, price: pd.Series) -> pd.Series:
    """Annual repurchase $ ÷ market cap (price × shares), point-in-time — the intensity of the buyback
    program (0.05 = ~5% of the float bought back per year). The signal only cares about the *ranking*."""
    repo = _pit_ffill(facts.get("repurchases", []), price.index)
    shares = _pit_ffill(facts.get("shares", []), price.index)
    mktcap = price * shares
    return (repo / mktcap.replace(0, np.nan)).clip(lower=0)


def blackout_panel(px: pd.DataFrame, facts: dict[str, dict], **kw) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (blackout mask panel, buyback-yield panel) aligned to the price panel, for the names that
    have both filings and repurchase data."""
    names = [c for c in px.columns if c in facts and facts[c].get("filings") and facts[c].get("repurchases")]
    mask = pd.DataFrame({c: blackout_mask(px.index, facts[c]["filings"], **kw) for c in names})
    yld = pd.DataFrame({c: buyback_yield(facts[c], px[c]) for c in names})
    return mask, yld


# ── Mechanism test & strategy ─────────────────────────────────────────────────────────────────────
def mechanism_test(px: pd.DataFrame, mask: pd.DataFrame, yld: pd.DataFrame, n_tiles: int = 3) -> pd.DataFrame:
    """Is the blackout drag real, and stronger for bigger buyback programs? For each buyback-intensity
    tercile, the annualized mean return **in blackout** vs **out of blackout** and the gap (out − in). The
    thesis predicts a positive gap that grows with buyback intensity."""
    rets = px.pct_change()
    names = list(mask.columns)
    med_yld = yld[names].mean()                              # average intensity per name → tercile buckets
    ranks = med_yld.rank(pct=True)
    rows = []
    for tile in range(n_tiles):
        lo, hi = tile / n_tiles, (tile + 1) / n_tiles
        cols = [c for c in names if lo < ranks[c] <= hi or (tile == 0 and ranks[c] <= hi)]
        if not cols:
            continue
        r, m = rets[cols], mask[cols]
        in_bo = r.where(m).stack().mean() * 252
        out_bo = r.where(~m).stack().mean() * 252
        rows.append({"tile": f"{['low', 'mid', 'high'][tile] if n_tiles == 3 else tile}",
                     "n": len(cols), "in_blackout": round(in_bo, 4), "out_blackout": round(out_bo, 4),
                     "gap_out_minus_in": round(out_bo - in_bo, 4)})
    return pd.DataFrame(rows)


def backtest(px: pd.DataFrame, mask: pd.DataFrame, yld: pd.DataFrame, rebalance: int = 5,
             cost_bps: float = 10.0, rf: pd.Series | None = None) -> dict:
    """Cross-sectional, dollar-neutral: **short** stocks in blackout (weighted by buyback intensity — the
    bigger the absent buyer, the bigger the short), fund it long the rest. Rebalanced every `rebalance`
    days, cost-charged. Isolates the buyer-absence effect from market beta."""
    names = list(mask.columns)
    rets = px[names].pct_change()
    m = mask.reindex(rets.index).fillna(False)
    w_yield = yld[names].reindex(rets.index).ffill().fillna(0.0)
    raw = -(m.astype(float) * w_yield)                       # short in-blackout, sized by program intensity
    W = raw.sub(raw.mean(axis=1), axis=0)                    # dollar-neutral
    W = W.div(W.abs().sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    W = W.iloc[::rebalance].reindex(rets.index).ffill()      # hold between rebalances

    pnl = (W.shift(1) * rets).sum(axis=1)
    turn = (W - W.shift(1)).abs().sum(axis=1)
    net = (pnl - turn * cost_bps / 1e4).dropna()
    return {"net": net, "weights": W, "turnover_ann": round(float(turn[turn > 0].mean() or 0) *
            (252 / rebalance), 1) if (turn > 0).any() else 0.0}
