"""SEC-EDGAR fundamentals layer — point-in-time value/quality/accruals/investment factors.

The cross-sectional price study (run_crosssec.py) could only test price/volume signals; the factors
that actually survive the academic literature — value, quality, accruals, investment — need company
fundamentals. This module pulls them from SEC EDGAR's XBRL "company facts" API (free, only a
User-Agent header required) and builds the factors the price-only feed could not.

The make-or-break is POINT-IN-TIME discipline. A fiscal-quarter number is NOT knowable on the day
the quarter ends — it becomes public only when the 10-Q/10-K is FILED, ~40–75 days later. Anchoring
a fundamental on its period `end` instead of its `filed` date is look-ahead that fabricates alpha
(you would be trading on numbers nobody had yet). Every panel here is forward-filled from the
`filed` date: the value on trading day t is the most recent value whose filing date ≤ t.

Flow items (EPS, gross profit, net income, operating cash flow, revenue) are made trailing-twelve-
month (sum of 4 distinct quarters, deriving Q4 = annual − first-three-quarters when only the 10-K
annual is reported); stock items (assets, equity) are point-in-time balance-sheet levels.

Network is lazy: nothing hits SEC at import; the cik map and each company's parsed facts are cached
under research/data/fundamentals/ so repeated studies read locally. Tests never touch the network.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import store
from .alpaca_data import UNIVERSE

# SEC asks every automated client to identify itself with a descriptive User-Agent (see
# https://www.sec.gov/os/webmaster-faq#developers); requests without one are refused.
USER_AGENT = "BondDesk Research research@bonddesk.example"
HEADERS = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
SEC_RATE_SLEEP = 0.15  # SEC caps automated access at ~10 req/s → ≥0.1s between calls

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

FUND_DIR = store.DATA_DIR / "fundamentals"
FACTS_DIR = FUND_DIR / "facts"
CIK_CACHE = FUND_DIR / "cik_map.json"

# us-gaap tags we extract, in fallback order (first present tag wins). Flow items are period flows
# (need a TTM); stock items are balance-sheet instants (point-in-time levels).
TAGS: dict[str, list[str]] = {
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "gross_profit": ["GrossProfit"],
    "assets": ["Assets"],
    "equity": ["StockholdersEquity"],
    "net_income": ["NetIncomeLoss"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities"],
    "revenues": ["Revenues"],
}
FLOW_FIELDS = {"eps", "gross_profit", "net_income", "ocf", "revenues"}
STOCK_FIELDS = {"assets", "equity"}


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# Network layer (lazy, cached). Nothing below runs at import.
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def cik_map(refresh: bool = False) -> dict[str, str]:
    """{TICKER: 10-digit zero-padded CIK} from SEC's company_tickers.json. Cached to JSON."""
    if CIK_CACHE.exists() and not refresh:
        return json.loads(CIK_CACHE.read_text())
    resp = requests.get(TICKERS_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    out = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in data.values()}
    _ensure(FUND_DIR)
    CIK_CACHE.write_text(json.dumps(out))
    return out


def fetch_companyfacts(cik: str, ticker: str, *, refresh: bool = False) -> dict[str, list[dict]]:
    """Fetch + parse one company's XBRL facts, keeping only the tags we need. Cached per ticker.

    Handles 404 (company has no XBRL facts) by caching an empty result so it is not re-requested,
    and 429 (rate limited) by backing off. Sleeps ~0.15s AFTER a live fetch to respect SEC's limit;
    cache hits do not sleep."""
    cache = FACTS_DIR / f"{ticker}.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())

    url = FACTS_URL.format(cik=cik)
    for attempt in range(4):
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 429:
            time.sleep(1.0 + attempt)
            continue
        if resp.status_code == 404:
            parsed: dict[str, list[dict]] = {}
            break
        resp.raise_for_status()
        parsed = _parse_companyfacts(resp.json())
        break
    else:
        parsed = {}

    _ensure(FACTS_DIR)
    cache.write_text(json.dumps(parsed))
    time.sleep(SEC_RATE_SLEEP)
    return parsed


def _parse_companyfacts(cf: dict) -> dict[str, list[dict]]:
    """Extract each needed field's observation list from a companyfacts JSON. Each observation keeps
    the fields that make point-in-time construction possible: val, end, start, filed, form, fp, fy."""
    gaap = cf.get("facts", {}).get("us-gaap", {})
    out: dict[str, list[dict]] = {}
    for field, tags in TAGS.items():
        chosen = next((t for t in tags if t in gaap), None)
        if chosen is None:
            out[field] = []
            continue
        obs: list[dict] = []
        for arr in gaap[chosen].get("units", {}).values():
            for o in arr:
                if o.get("val") is None or o.get("end") is None or o.get("filed") is None:
                    continue
                obs.append({"val": o["val"], "end": o["end"], "start": o.get("start"),
                            "filed": o["filed"], "form": o.get("form"), "fp": o.get("fp"),
                            "fy": o.get("fy")})
        out[field] = obs
    return out


def load_all_facts(tickers: list[str] | None = None) -> dict[str, dict]:
    """Parsed facts for every ticker that has a CIK. Fetches (once) then caches. Network is only
    hit on a cache miss; subsequent runs are fully local."""
    tickers = tickers or UNIVERSE
    cm = cik_map()
    out: dict[str, dict] = {}
    for t in tickers:
        cik = cm.get(t.upper())
        if not cik:
            continue
        parsed = fetch_companyfacts(cik, t)
        if parsed:
            out[t] = parsed
    return out


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# Point-in-time construction (pure; unit-tested offline).
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def _ttm(vals: list[float]) -> float | None:
    """Trailing-twelve-month value: sum of the 4 most recent quarterly values (None if <4)."""
    if len(vals) < 4:
        return None
    return float(sum(vals[-4:]))


def _duration_days(o: dict) -> int | None:
    """Period length in days for a flow observation; None for an instant (stock) observation."""
    if not o.get("start"):
        return None
    return (pd.Timestamp(o["end"]) - pd.Timestamp(o["start"])).days


def _flow_ttm_points(obs: list[dict]) -> list[tuple[str, str, float]]:
    """(filed, end, ttm_value) points for a flow field, anchored on FILED dates.

    Builds a clean quarterly (3-month) series — keeping the first-filed value per fiscal period end
    (the originally-reported number, the point-in-time truth) — then derives the missing Q4 as
    annual − (Q1+Q2+Q3) so a full four-quarter TTM exists even when only the 10-K annual is filed.
    Each rolling 4-quarter sum is stamped with its NEWEST quarter's filing date (when the TTM first
    became knowable). Raw annual (10-K) values are added directly as TTM points too."""
    quarters: dict[str, tuple[str, float]] = {}   # end -> (filed, 3-month value), first filed wins
    annual: list[dict] = []
    for o in sorted(obs, key=lambda x: x["filed"]):
        d = _duration_days(o)
        if d is None:
            continue
        if 80 <= d <= 100:                          # quarterly (3-month) flow
            quarters.setdefault(o["end"], (o["filed"], float(o["val"])))
        elif 350 <= d <= 380:                       # annual (12-month) flow
            annual.append(o)

    # Derive Q4 (the quarter the 10-K rarely reports on its own) = annual − first three quarters.
    for a in annual:
        aend = a["end"]
        if aend in quarters:
            continue
        prior = [e for e in sorted(quarters)
                 if e < aend and (pd.Timestamp(aend) - pd.Timestamp(e)).days <= 300]
        prior = prior[-3:]
        if len(prior) == 3:
            q4 = float(a["val"]) - sum(quarters[e][1] for e in prior)
            quarters[aend] = (a["filed"], q4)

    ends = sorted(quarters)
    points: list[tuple[str, str, float]] = []
    for i in range(3, len(ends)):
        window = ends[i - 3:i + 1]
        gaps = [(pd.Timestamp(window[k + 1]) - pd.Timestamp(window[k])).days for k in range(3)]
        if any(not (60 <= g <= 130) for g in gaps):   # require 4 *consecutive* quarters
            continue
        ttm = _ttm([quarters[e][1] for e in window])
        if ttm is None or not np.isfinite(ttm):
            continue
        filed = max(quarters[e][0] for e in window)    # knowable only once the newest quarter files
        points.append((filed, window[-1], ttm))

    for a in annual:                                   # 10-K annual is itself a TTM as-of its filing
        points.append((a["filed"], a["end"], float(a["val"])))
    return points


def _level_points(obs: list[dict]) -> list[tuple[str, str, float]]:
    """(filed, end, value) points for a stock/level field, keeping the first-filed value per period
    end (originally reported, no restatement look-ahead)."""
    by_end: dict[str, tuple[str, float]] = {}
    for o in sorted(obs, key=lambda x: x["filed"]):
        by_end.setdefault(o["end"], (o["filed"], float(o["val"])))
    return [(f, e, v) for e, (f, v) in by_end.items()]


def _naive_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def _pit_align(points: list[tuple[str, str, float]], trading_index: pd.DatetimeIndex) -> pd.Series:
    """Forward-fill filed-anchored points onto the trading calendar: value at t = the most recent
    point whose FILED date ≤ t (never before). When several points share a filed date, the one with
    the latest period end wins. This is the whole point-in-time guarantee, in one place."""
    if not points:
        return pd.Series(np.nan, index=trading_index, dtype=float)
    df = pd.DataFrame(points, columns=["filed", "end", "val"])
    df["filed"] = pd.to_datetime(df["filed"]).dt.normalize()
    df["end"] = pd.to_datetime(df["end"]).dt.normalize()
    df = df.sort_values(["filed", "end"]).drop_duplicates("filed", keep="last")
    ser = pd.Series(df["val"].to_numpy(dtype=float), index=pd.DatetimeIndex(df["filed"]))

    tnaive = _naive_dates(trading_index)
    combined = ser.reindex(ser.index.union(tnaive)).ffill()
    return pd.Series(combined.reindex(tnaive).to_numpy(dtype=float), index=trading_index)


def _field_panel(facts: dict[str, dict], field: str, trading_index: pd.DatetimeIndex,
                 tickers: list[str]) -> pd.DataFrame:
    """A point-in-time dates × symbols panel for one fundamental field (NaN column where missing)."""
    kind_flow = field in FLOW_FIELDS
    cols: dict[str, pd.Series] = {}
    for t in tickers:
        obs = (facts.get(t) or {}).get(field)
        if not obs:
            cols[t] = pd.Series(np.nan, index=trading_index, dtype=float)
            continue
        points = _flow_ttm_points(obs) if kind_flow else _level_points(obs)
        cols[t] = _pit_align(points, trading_index)
    return pd.DataFrame(cols).reindex(columns=tickers)


def fundamental_panels(px: pd.DataFrame, facts: dict[str, dict] | None = None
                       ) -> dict[str, pd.DataFrame]:
    """Point-in-time panels for every fundamental field, aligned to the price panel px."""
    tickers = list(px.columns)
    if facts is None:
        facts = load_all_facts(tickers)
    return {f: _field_panel(facts, f, px.index, tickers) for f in TAGS}


# ─────────────────────────────────────────────────────────────────────────────────────────────────
# Factors (each a dates × symbols frame; higher = long).
# ─────────────────────────────────────────────────────────────────────────────────────────────────
def _safe_div(num: pd.DataFrame, den: pd.DataFrame) -> pd.DataFrame:
    """num / den, but only where den > 0 (a zero or negative denominator → NaN, excluded that day).
    A negative book value or asset base makes the ratio economically meaningless, not just undefined."""
    return num.divide(den.where(den > 0))


def fundamental_signals(px: pd.DataFrame, facts: dict[str, dict] | None = None
                        ) -> dict[str, pd.DataFrame]:
    """The five fundamental factors, each a dates × symbols score (higher = long), aligned to px:

      * earnings_yield      EPS_ttm / price            — value (long cheap earnings)
      * gross_profitability GrossProfit_ttm / Assets   — Novy-Marx quality
      * roe                 NetIncome_ttm / Equity     — quality
      * accruals            −(NetIncome_ttm − OCF_ttm)/Assets — Sloan (long LOW accruals)
      * asset_growth        −(Assets/Assets_1yr − 1)   — Cooper-Gulen-Schill (long LOW growth)
    """
    p = fundamental_panels(px, facts)
    eps, gp, ni, ocf = p["eps"], p["gross_profit"], p["net_income"], p["ocf"]
    assets, equity = p["assets"], p["equity"]

    earnings_yield = _safe_div(eps, px)                                   # px > 0 always
    gross_profitability = _safe_div(gp, assets)
    roe = _safe_div(ni, equity)
    accruals = -_safe_div(ni - ocf, assets)                              # low accruals = long
    assets_1yr = assets.shift(252)                                       # ~1 trading year lag
    asset_growth = -( _safe_div(assets, assets_1yr) - 1.0)               # low growth = long

    return {
        "earnings_yield": earnings_yield,
        "gross_profitability": gross_profitability,
        "roe": roe,
        "accruals": accruals,
        "asset_growth": asset_growth,
    }
