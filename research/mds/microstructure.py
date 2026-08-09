"""Microstructure alpha — an event-driven backtester and the honest question it answers.

The cross-sectional study (run_crosssec) came back null: on daily mega-cap candles there is no free
edge. Short-horizon **microstructure** is different — order flow genuinely predicts the next move
(Cont–Kukanov–Stoikov: order-flow imbalance is the single best short-horizon predictor). But a
predictive signal is not a tradable one: at tick horizons you pay the spread and market impact on
every decision, and a real information coefficient can die entirely to costs. That gap — between a
signal with IC and a strategy with P&L — is the whole game in microstructure trading, and it is what
this module measures with an **event-driven backtester** rather than a vectorised one that ignores
execution.

Everything is causal (a signal at t uses only information through t; it is traded into the t→t+1
move) and self-contained: `simulate` generates an order-flow tape with a *known* ground-truth
OFI→return relationship (the same honest "known-signal" framing as the project's synthetic market),
so the study demonstrates the infrastructure finds the edge when one exists — and then shows, under
realistic costs, whether it is worth trading. It ties directly to the exchange: same order-flow
imbalance, and the same lesson the exchange's locked one-tick book showed — a real signal needs
enough spread/edge to survive execution.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import validation as val

DEFAULT_OBS_PER_YEAR = 25_000    # decision points/yr for a fast intraday strategy (for annualising)


def simulate(n: int = 40_000, ic: float = 0.10, ret_vol_bps: float = 2.0, spread_bps: float = 1.0,
             ofi_noise: float = 1.0, seed: int = 0) -> pd.DataFrame:
    """Generate an order-flow tape with a *known* OFI→next-return relationship.

    Construction (population IC is exactly `ic`): a latent informed component drives both the
    observable order-flow imbalance and the next mid return, plus independent noise. Order-flow
    imbalance therefore predicts the one-step-ahead return with correlation `ic` — a realistic
    microstructure IC (a few percent). Returns a tick panel with the mid, the one-step forward
    return (the label), and the observable signals (OFI, a smoothed OFI, and a noisier queue
    imbalance). The last row's forward return is NaN (no observable future)."""
    rng = np.random.default_rng(seed)
    ofi = rng.standard_normal(n)                                   # observable order-flow imbalance
    ofi_z = (ofi - ofi.mean()) / ofi.std()
    sd = ret_vol_bps / 1e4
    eps = rng.standard_normal(n)
    fwd = ic * sd * ofi_z + np.sqrt(max(0.0, 1 - ic * ic)) * sd * eps   # corr(ofi_z, fwd) == ic
    fwd[-1] = np.nan                                               # no future for the last tick
    queue = 0.6 * ofi_z + np.sqrt(1 - 0.36) * rng.standard_normal(n)    # a weaker, noisier correlate

    logmid = np.concatenate([[0.0], np.cumsum(np.nan_to_num(fwd[:-1]))])
    mid = 100.0 * np.exp(logmid)
    panel = pd.DataFrame({
        "mid": mid,
        "fwd_ret": fwd,
        "ofi": ofi_z,
        "ofi_smooth": pd.Series(ofi_z).rolling(5, min_periods=1).mean().to_numpy(),
        "queue_imb": queue,
        "spread_bps": spread_bps,
    })
    return panel


def signals(panel: pd.DataFrame) -> dict[str, pd.Series]:
    """The observable microstructure signals a trader could act on (higher = expect price up)."""
    return {
        "ofi": panel["ofi"],
        "ofi_smooth": panel["ofi_smooth"],
        "queue_imb": panel["queue_imb"],
    }


def ic_by_horizon(panel: pd.DataFrame, signal: pd.Series, horizons=(1, 2, 3, 5, 10, 20, 50)) -> dict[int, float]:
    """Rank IC of the signal vs the forward mid return over each horizon — the signal-decay curve.
    A microstructure edge is strongest one step out and decays as the informative move is diluted by
    later noise (≈ IC/√h), so this shows how fast you must act to capture it."""
    logmid = np.log(panel["mid"])
    out = {}
    for h in horizons:
        fwd_h = logmid.shift(-h) - logmid
        m = signal.notna() & fwd_h.notna()
        out[int(h)] = float(signal[m].corr(fwd_h[m], method="spearman")) if m.sum() > 50 else float("nan")
    return out


def event_driven_backtest(panel: pd.DataFrame, signal: pd.Series, cost_bps: float,
                          obs_per_year: int = DEFAULT_OBS_PER_YEAR) -> dict:
    """Trade the signal through an event-driven simulation with realistic execution.

    Causal: the position for the t→t+1 move is decided from the signal at t (position = sign of the
    signal — a taker who crosses to get in). Every change in position pays `cost_bps` of round-trip
    execution cost (half-spread + impact). The point is that at tick frequency turnover is enormous,
    so even a real edge can be entirely eaten — `net` is the honest number.

    Returns gross/net per-tick information ratios and annualised Sharpes, total bps, the cost drag,
    hit rate, turnover, and the net return series (for significance testing)."""
    sig = signal.reindex(panel.index)
    fwd = panel["fwd_ret"]
    pos = np.sign(sig).fillna(0.0)
    gross = (pos * fwd).dropna()
    turnover = pos.diff().abs().fillna(pos.abs())
    cost = turnover * (cost_bps / 1e4)
    net = (pos * fwd - cost).dropna()

    def ir(x):
        s = x.std(ddof=0)
        return float(x.mean() / s) if s > 0 and len(x) else 0.0

    ann = np.sqrt(obs_per_year)
    return {
        "gross_ir": ir(gross), "net_ir": ir(net),
        "gross_sharpe": ir(gross) * ann, "net_sharpe": ir(net) * ann,
        "gross_bps": float(gross.sum() * 1e4), "net_bps": float(net.sum() * 1e4),
        "cost_bps": float(cost.sum() * 1e4), "avg_turnover": float(turnover.mean()),
        "hit_rate": float((gross > 0).mean()) if len(gross) else 0.0,
        "days": int(len(net)), "net_series": net,
    }


def study(n: int = 40_000, ic: float = 0.10, ret_vol_bps: float = 2.0,
          cost_grid=(0.0, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0), signal_name: str = "ofi",
          seed: int = 0) -> dict:
    """The full microstructure story: does the (real) signal survive realistic costs?

    Simulates a tape with a known OFI edge, measures the signal-decay curve, then sweeps the
    round-trip execution cost to find the break-even — the point where a genuinely predictive signal
    stops being tradable — and reports the honest verdict with overfitting-aware significance on the
    net returns at a representative cost."""
    panel = simulate(n=n, ic=ic, ret_vol_bps=ret_vol_bps, seed=seed)
    sig = signals(panel)[signal_name]

    decay = ic_by_horizon(panel, sig)
    realized_ic = decay.get(1, float("nan"))

    sweep = []
    breakeven = None
    for c in cost_grid:
        bt = event_driven_backtest(panel, sig, c)
        sweep.append({"cost_bps": float(c), "gross_sharpe": round(bt["gross_sharpe"], 3),
                      "net_sharpe": round(bt["net_sharpe"], 3), "net_bps": round(bt["net_bps"], 1),
                      "turnover": round(bt["avg_turnover"], 3)})
        if breakeven is None and bt["net_sharpe"] <= 0:
            breakeven = float(c)

    # Significance of the net edge at a representative (tight) cost.
    rep_cost = 0.5
    rep = event_driven_backtest(panel, sig, rep_cost)
    net = rep["net_series"].to_numpy()
    hac_t = val.newey_west_sharpe_tstat(net)
    gross = event_driven_backtest(panel, sig, 0.0)

    verdict = (
        f"On a **synthetic** tape with an **assumed** 1-step IC of {realized_ic:+.3f}, the event-driven "
        f"backtester recovers it — a plumbing check, so the high gross Sharpe ({gross['gross_sharpe']:.1f}, "
        f"annualized at tick frequency) is true *by construction*, not a measured edge. What is informative is "
        f"the tradability threshold: it only survives below ~{breakeven if breakeven is not None else '>'} bps "
        f"round-trip cost — at a realistic {rep_cost} bps the net Sharpe is {rep['net_sharpe']:.1f} "
        f"(HAC t {hac_t:+.1f}). Order-flow imbalance is well documented to predict short-horizon returns; the "
        f"point here is methodological — whether a predictive signal is *tradable* depends entirely on execution "
        f"cost. (Validating the IC on the project's real L2 book would make this an empirical finding, not an assumed one.)"
    )
    return {
        "params": {"n": n, "ic": ic, "ret_vol_bps": ret_vol_bps, "signal": signal_name},
        "ic_decay": [{"horizon": h, "ic": round(v, 4)} for h, v in decay.items()],
        "cost_sweep": sweep,
        "breakeven_cost_bps": breakeven,
        "gross_sharpe": round(gross["gross_sharpe"], 3),
        "representative": {"cost_bps": rep_cost, "net_sharpe": round(rep["net_sharpe"], 3),
                           "hac_t": round(hac_t, 2), "net_bps": round(rep["net_bps"], 1),
                           "turnover": round(rep["avg_turnover"], 3), "hit_rate": round(rep["hit_rate"], 4)},
        "verdict": verdict,
    }
