"""Capacity & crowding study — sizing and competition, the game-theoretic trader layer.

Two demonstrations on known ground truth (the model's behaviour is provable, so we validate it
the same way as the optimizer), then the honest read-across to the real signals.

    python run_capacity.py
"""

from __future__ import annotations

import numpy as np

from mds import capacity as cap


def demo_capacity_allocation() -> None:
    """Three signals with the SAME raw edge μ but very different impact λ (capacity). A naive
    allocator concentrates in one; the capacity-aware one spreads to where the money can work."""
    names = ["deep", "medium", "shallow"]
    mu = np.array([0.10, 0.10, 0.10])          # identical raw edge...
    lam = np.array([0.02, 0.10, 0.50])         # ...but very different market impact (capacity)
    budget = 3.0

    print("Capacity-aware sizing — 3 signals, equal edge (μ=0.10), different impact (λ):")
    print(f"  capacities C* = μ/2λ: " +
          ", ".join(f"{n} {c:.2f}" for n, c in zip(names, cap.optimal_capacity(mu, lam))))
    for label, alloc in [
        ("concentrate (naive)", cap.concentrate(mu, budget)),
        ("capacity-aware", cap.allocate_with_capacity(mu, lam, budget)),
    ]:
        profit = cap.total_profit(mu, lam, alloc)
        split = ", ".join(f"{n} {c:.2f}" for n, c in zip(names, alloc))
        print(f"  {label:<22} profit {profit:+.4f}   [{split}]")
    print("  -> dumping the budget into one signal saturates its capacity and pays impact past")
    print("     the point the edge is worth; water-filling earns more from the same capital.\n")


def demo_crowding() -> None:
    """One signal, K identical players. As the crowd grows, each best-responds — and aggregate
    profit falls even as total capital rises. The tragedy of the commons behind 'crowded factor'."""
    mu, lam = 0.10, 0.05
    print("Crowding — K players share one signal (μ=0.10, λ=0.05):")
    print(f"  {'players':>7} {'cap/each':>9} {'total cap':>10} {'rate':>8} {'aggregate P':>12}")
    for k in (1, 2, 4, 8, 16):
        e = cap.crowding_equilibrium(mu, lam, k)
        print(f"  {e['n_players']:>7} {e['capital_each']:>9.3f} {e['total_capital']:>10.3f} "
              f"{e['rate']:>8.4f} {e['aggregate_profit']:>12.4f}")
    print("  -> total capital rises but per-player edge and AGGREGATE profit fall: adding crowd")
    print("     members destroys the very alpha they are chasing. Capacity is a shared resource.\n")


def read_across_real() -> None:
    """Honest read-across: our real signals' net edges (μ = annual net return) and turnover, read
    LIVE from the cross-sectional backtest — not hand-transcribed. λ (impact) is still proxied from
    turnover: an ASSUMPTION, flagged as such. Skips gracefully if the equity cache isn't present."""
    try:
        from mds import crosssec as xs
        px, rets = xs.returns_panel()
        res = {n: xs.backtest(s, rets, cost_bps=5.0) for n, s in xs.signals(px, rets).items()}
    except Exception as e:  # noqa: BLE001 — the equity parquet may not be cached
        print(f"Read-across skipped (equity cache unavailable: {e}).\n")
        return
    signals = {n: (res[n]["ann_return"], res[n]["avg_turnover"]) for n in res}
    names = list(signals)
    mu = np.array([signals[n][0] for n in names])
    lam = np.array([signals[n][1] for n in names]) * 0.5  # impact ∝ turnover (assumed scale)
    # Size each alpha to its OWN capacity C*=μ/2λ (deployment is a choice, not a forced budget):
    # negative-edge signals get C*<0 → clipped to zero, so the loser book is simply not funded.
    alloc = np.clip(cap.optimal_capacity(mu, lam), 0.0, None)
    print("Read-across to real signals (μ, turnover read live from run_crosssec; λ proxied from turnover):")
    for n, c in zip(names, alloc):
        print(f"  {n:<14} edge {signals[n][0]:+.3f}  turnover {signals[n][1]:.2f}  -> capital {c:.2f}")
    print("  -> the capacity allocator funds only the positive-edge signals and refuses the")
    print("     money-losers — but none of those edges is statistically significant (see run_crosssec),")
    print("     so this sizes signals that aren't established alpha. Machinery, not a trade.\n")


def main() -> None:
    demo_capacity_allocation()
    demo_crowding()
    read_across_real()


if __name__ == "__main__":
    main()
