"""Microstructure ML study: can order-book features predict the next mid move, and does
the edge survive the spread?

Runs the model zoo (linear → gradient boosting → small neural net) with walk-forward
out-of-sample validation over a recorded L2 session, then the cost-aware acid test. Prints
an honest verdict — the point of the exercise is the gross-vs-net gap, not a headline Sharpe.

    python run_microstructure.py [session-label] [product]
    e.g. python run_microstructure.py 2026-07-06 BTC-USD   (a recorded session)
         python run_microstructure.py signal SYNTH-USD     (the known-signal synthetic)
"""

from __future__ import annotations

import sys

from mds import lob, models


def verdict(results: dict) -> str:
    best = max(results.values(), key=lambda r: r["ic_spearman"])
    ic = best["ic_spearman"]
    gross, net = best["gross_ret_bps"], best["net_ret_bps"]
    if ic < 0.03:
        return ("No usable predictive signal in these features at this horizon "
                f"(best IC {ic:+.3f}). Honest negative result.")
    if net > 0 and gross > 0:
        return (f"Signal present (IC {ic:+.3f}) and it SURVIVES costs "
                f"(net {net:+.0f} bps). Worth deeper study — check capacity and robustness.")
    return (f"Signal present (IC {ic:+.3f}, gross {gross:+.0f} bps) but it DIES after the spread "
            f"(net {net:+.0f} bps). This is bid-ask bounce, not tradable alpha: the predicted "
            "move is smaller than the cost of crossing to capture it. Monetising it would require "
            "passive (maker) execution — which reintroduces adverse selection.")


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "2026-07-06"
    product = sys.argv[2] if len(sys.argv) > 2 else "BTC-USD"

    df = lob.build_panel(lob.capture_path(label), product=product,
                         sample_every=20, horizon=1, depth=5)
    print(f"Session '{label}' [{product}]: {len(df)} samples (next-move prediction)\n")

    results = models.evaluate(df, folds=5, fee_bps=1.0)
    header = f"  {'model':<7} {'IC(spear)':>10} {'gross bps':>10} {'net bps':>9} {'cost bps':>9} {'turnover':>9}"
    print(header)
    for name, r in results.items():
        print(f"  {name:<7} {r['ic_spearman']:>+10.3f} {r['gross_ret_bps']:>+10.0f} "
              f"{r['net_ret_bps']:>+9.0f} {r['cost_bps']:>9.0f} {r['avg_turnover']:>9.2f}")

    print(f"\nVerdict: {verdict(results)}")
    print("\n(Sharpe on event-spaced samples is a proxy; the gross-vs-net gap in bps is the "
          "unambiguous result. Costs = half-spread + 1bp fee per trade.)")


if __name__ == "__main__":
    main()
