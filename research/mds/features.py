"""Microstructure & price features, incl. a signal computed over the recorder's capture."""

from __future__ import annotations

import numpy as np
import pandas as pd


def log_returns(prices: np.ndarray) -> np.ndarray:
    p = np.asarray(prices, dtype=float)
    return np.concatenate([[0.0], np.diff(np.log(p))])


def realized_vol(returns: np.ndarray, window: int, periods_per_year: float) -> np.ndarray:
    r = pd.Series(np.asarray(returns, dtype=float))
    return (r.rolling(window).std(ddof=0) * np.sqrt(periods_per_year)).to_numpy()


def imbalance_information_coefficient(capture: pd.DataFrame, product: str, horizon: int = 5) -> dict:
    """Does top-of-book imbalance predict the next moves in microprice?

    Computes the information coefficient (correlation) between the current order-book
    imbalance and the forward microprice log-return over `horizon` snapshots — a standard
    microstructure sanity check, run over the Java recorder's captured data.
    """
    df = capture[capture["product"] == product].sort_values("ts").reset_index(drop=True)
    if len(df) <= horizon + 1:
        return {"observations": len(df), "information_coefficient": float("nan")}
    micro = df["microprice"].to_numpy(dtype=float)
    fwd = np.log(np.roll(micro, -horizon)) - np.log(micro)
    fwd[-horizon:] = np.nan
    imb = df["imbalance"].to_numpy(dtype=float)
    mask = ~np.isnan(fwd)
    ic = float(np.corrcoef(imb[mask], fwd[mask])[0, 1]) if mask.sum() > 2 else float("nan")
    return {"observations": int(mask.sum()), "horizon": horizon, "information_coefficient": ic}
