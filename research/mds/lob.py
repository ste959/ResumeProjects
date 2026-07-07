"""Reconstruct a limit order book from the L2 capture and build a supervised,
leakage-free feature/label panel for microstructure machine learning.

The single most important property here is **no look-ahead**: every feature at sample
time t is computed from order-book and trade information observed up to and including t,
while the label is the *forward* mid return over the next `horizon` samples. The last
`horizon` rows (which have no observable future) are dropped. Getting this boundary right
is the difference between a real signal study and a backtest that lies to you.

Input is the same CSV the Java engine records / generates:
    seq, ts, product, kind(SNAP|UPD|TRD), side(B|A), price, size
so recorded crypto sessions and synthetic (known-signal) sessions flow through identically.
"""

from __future__ import annotations

import csv
import math
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURE_DIR = REPO_ROOT / "backend" / "market-data" / "l2"

# Cap the reconstructed book to near-touch levels (deep levels don't affect our features).
_CAP = 256
_KEEP = 64


def capture_path(label: str) -> Path:
    """Resolve an L2 session by label, e.g. 'signal' -> .../l2-signal.csv."""
    return CAPTURE_DIR / f"l2-{label}.csv"


def build_panel(csv_path, product: str | None = None, sample_every: int = 25,
                horizon: int = 20, depth: int = 5, rvol_window: int = 50) -> pd.DataFrame:
    """Replay an L2 session and emit a feature/label panel.

    A feature row is snapshotted every `sample_every` book-changing events (once the book
    is two-sided). Features use only information up to that instant; the label `fwd_ret`
    is the log mid-return `horizon` samples ahead.

    Returns a DataFrame indexed 0..N with columns:
        ts, mid, imbalance, micro_prem_bps, spread_bps, depth_imb, trade_flow, ret_1,
        rvol, fwd_ret
    """
    bids: dict[float, float] = {}
    asks: dict[float, float] = {}
    snap_seq = None
    in_snap = False

    rows = []            # feature dicts (label filled in afterwards)
    flow = 0.0           # signed trade volume accumulated since the last sample
    last_mid = None
    changes = 0          # count of book-changing events since program start

    def best():
        if not bids or not asks:
            return None
        bb = max(bids)
        ba = min(asks)
        return bb, ba, bids[bb], asks[ba]

    def topn(side_book: dict[float, float], n: int, reverse: bool) -> float:
        # Sum of size across the n best levels (reverse=True for bids: high→low).
        prices = sorted(side_book, reverse=reverse)[:n]
        return float(sum(side_book[p] for p in prices))

    with open(csv_path, newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        for r in reader:
            if len(r) < 7:
                continue
            _, ts, prod, kind, side, price, size = r
            if product is not None and prod != product:
                continue
            price = float(price)
            size = float(size)

            if kind == "SNAP":
                seq = r[0]
                if not in_snap or seq != snap_seq:
                    bids.clear()
                    asks.clear()
                    snap_seq = seq
                    in_snap = True
                (bids if side == "B" else asks)[price] = size
                continue

            snapshot_done = in_snap  # first non-SNAP event completes a fresh full book
            in_snap = False
            if kind == "TRD":
                # Classify by price vs. the last mid (robust to the feed's side field,
                # which for Coinbase is the maker side, not the aggressor).
                if last_mid is not None:
                    flow += size if price >= last_mid else -size
                if not snapshot_done:
                    continue  # a trade alone doesn't change the resting book
            elif kind == "UPD":
                book = bids if side == "B" else asks
                if size <= 0:
                    book.pop(price, None)
                else:
                    book[price] = size

            # Prune to near-touch levels. A real Coinbase snapshot carries thousands of
            # levels, but the top-of-book / top-N features only need the touch, so capping
            # keeps best()/topn() cheap without affecting any feature.
            if len(bids) > _CAP:
                bids = {p: bids[p] for p in sorted(bids, reverse=True)[:_KEEP]}
            if len(asks) > _CAP:
                asks = {p: asks[p] for p in sorted(asks)[:_KEEP]}

            # A book change: an incremental update, or the completion of a full snapshot
            # (which is how the synthetic feed and each reconnect deliver the book).
            changes += 1
            b = best()
            if b is None or changes % sample_every != 0:
                if b is not None:
                    last_mid = (b[0] + b[1]) / 2.0
                continue

            bb, ba, bbsz, basz = b
            mid = (bb + ba) / 2.0
            tot = bbsz + basz
            imbalance = (bbsz - basz) / tot if tot > 0 else 0.0
            micro = (bb * basz + ba * bbsz) / tot if tot > 0 else mid
            micro_prem_bps = (micro - mid) / mid * 1e4 if mid > 0 else 0.0
            spread_bps = (ba - bb) / mid * 1e4 if mid > 0 else 0.0
            bidN = topn(bids, depth, reverse=True)
            askN = topn(asks, depth, reverse=False)
            depth_imb = (bidN - askN) / (bidN + askN) if (bidN + askN) > 0 else 0.0
            ret_1 = math.log(mid / last_mid) if last_mid and last_mid > 0 else 0.0
            norm_flow = flow / (tot if tot > 0 else 1.0)

            rows.append({
                "ts": ts, "mid": mid, "imbalance": imbalance,
                "micro_prem_bps": micro_prem_bps, "spread_bps": spread_bps,
                "depth_imb": depth_imb, "trade_flow": norm_flow, "ret_1": ret_1,
            })
            flow = 0.0
            last_mid = mid

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Rolling realized vol of sampled mid returns (trailing, no look-ahead).
    df["rvol"] = df["ret_1"].rolling(rvol_window, min_periods=5).std().fillna(0.0)

    # Label: forward mid log-return `horizon` samples ahead. Drop the tail with no future.
    logmid = np.log(df["mid"].to_numpy())
    fwd = np.empty(len(df))
    fwd[:] = np.nan
    fwd[:-horizon] = logmid[horizon:] - logmid[:-horizon]
    df["fwd_ret"] = fwd
    return df.iloc[:-horizon].reset_index(drop=True)


FEATURES = ["imbalance", "micro_prem_bps", "spread_bps", "depth_imb", "trade_flow", "ret_1", "rvol"]


def information_coefficient(feature: np.ndarray, fwd_ret: np.ndarray) -> dict:
    """Pearson and Spearman (rank) correlation of a feature with the forward return."""
    x = np.asarray(feature, dtype=float)
    y = np.asarray(fwd_ret, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    if n < 3 or x.std() == 0 or y.std() == 0:
        return {"n": n, "pearson": float("nan"), "spearman": float("nan")}
    pearson = float(np.corrcoef(x, y)[0, 1])
    xr = pd.Series(x).rank().to_numpy()
    yr = pd.Series(y).rank().to_numpy()
    spearman = float(np.corrcoef(xr, yr)[0, 1])
    return {"n": n, "pearson": pearson, "spearman": spearman}


def ic_significance(r: float, n_eff: int) -> dict:
    """Significance of a correlation-style IC: two-sided t-stat and a 95% CI via the Fisher
    z-transform. Pass the EFFECTIVE sample size, not the raw count — when the label is a
    horizon-H forward return the samples overlap, so n_eff ≈ n / H (overlap inflates naive
    significance). Assumes roughly IID effective samples; residual autocorrelation still widens
    the true interval, so treat this as a floor on the error bar, not the last word."""
    if not np.isfinite(r) or n_eff < 4 or abs(r) >= 1.0:
        return {"t_stat": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
                "n_eff": int(max(n_eff, 0))}
    z = np.arctanh(r)
    se = 1.0 / np.sqrt(n_eff - 3)
    t = r * np.sqrt((n_eff - 2) / (1.0 - r * r))
    return {"t_stat": float(t), "ci_low": float(np.tanh(z - 1.96 * se)),
            "ci_high": float(np.tanh(z + 1.96 * se)), "n_eff": int(n_eff)}


def synthetic_latent_panel(n: int = 6000, feat_noise: float = 3.0, seed: int = 0):
    """A NON-circular ground-truth panel for testing the model + validation layer honestly.

    The L2 synthetic generator plants the signal *as the feature* (book imbalance == the planted
    skew == a transform of the next return), so a model 'recovering' it proves only the plumbing —
    recovery is tautological. Here instead a latent AR(1) fair-value signal `z` drives the forward
    return, and the observable features are noisy, INDIRECT proxies of `z` (never the label). A
    model must actually denoise several weak views to estimate `z`, so the achievable IC is modest
    and honestly earned — and bounded by the irreducible noise, exactly like real data.

    With fwd = c·z + noise, the ceiling IC (perfect recovery of z) is c/√(c²+1); the model gets
    less. This is the test that distinguishes 'the harness works' from 'the model finds signal it
    wasn't handed'."""
    rng = np.random.default_rng(seed)
    phi, c = 0.9, 0.15
    z = np.zeros(n)
    eps = rng.standard_normal(n)
    for t in range(1, n):
        z[t] = phi * z[t - 1] + eps[t]
    z = (z - z.mean()) / z.std()
    fwd = c * z + rng.standard_normal(n)                     # future return: latent + unpredictable noise
    df = pd.DataFrame({name: z + feat_noise * rng.standard_normal(n) for name in FEATURES})
    df["fwd_ret"] = fwd * 5e-4                                # ~5bp vol so bps accounting is sensible
    # spread_bps doubles as the cost column, so make it a strictly-positive noisy magnitude proxy
    # rather than a constant (a constant would be a dead feature that breaks correlation checks).
    df["spread_bps"] = 1.0 + 0.5 * np.abs(df["spread_bps"])
    df["ceiling_ic"] = c / np.sqrt(c * c + 1.0)              # best possible IC if z were observed
    return df


def walk_forward_splits(n: int, folds: int = 4, min_train: float = 0.4, embargo: int = 0):
    """Expanding-window walk-forward splits (train always precedes test in time).

    Yields (train_idx, test_idx) pairs. Never shuffles — shuffling a time series leaks the
    future into the past and is the classic way to fake a great backtest.

    `embargo` inserts a gap of that many samples between the end of train and the start of test
    AND purges the last `embargo` training rows. With a horizon-H forward-return label the last H
    training labels overlap the first test features, so setting `embargo ≥ H` removes that
    boundary leakage (purging + embargo, per López de Prado).
    """
    start = int(n * min_train)
    step = max(1, (n - start) // folds)
    for k in range(folds):
        tr_end = start + k * step
        te_start = tr_end + embargo          # embargo gap before the test block
        te_end = min(n, te_start + step)
        tr_purge_end = tr_end - embargo      # purge overlapping-label rows off the train tail
        if tr_purge_end <= 0 or te_end <= te_start:
            continue
        yield np.arange(0, tr_purge_end), np.arange(te_start, te_end)
