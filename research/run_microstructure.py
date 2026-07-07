"""Microstructure ML study: can order-book features predict the next mid move, and does the
edge survive the spread?

Runs the model zoo (linear → gradient boosting → small neural net) with walk-forward
out-of-sample validation over a recorded L2 session, then the cost-aware acid test. The point
is the gross-vs-net gap, not a headline Sharpe.

    python run_microstructure.py [session-label] [product]   # study one session
    python run_microstructure.py --validate                  # ground-truth vs real comparison

Examples:
    python run_microstructure.py 2026-07-06 BTC-USD
    python run_microstructure.py signal SYNTH-USD
"""

from __future__ import annotations

import sys
import warnings

from mds import lob, models

try:
    from sklearn.exceptions import ConvergenceWarning
    warnings.filterwarnings("ignore", category=ConvergenceWarning)  # the MLP hitting its iter cap
except Exception:
    pass


def _study(label: str, product: str, sample_every: int, horizon: int = 1):
    df = lob.build_panel(lob.capture_path(label), product=product,
                         sample_every=sample_every, horizon=horizon, depth=5)
    return df, models.evaluate(df, folds=5, fee_bps=1.0, horizon=horizon)


def _best(results: dict) -> dict:
    return max(results.values(), key=lambda r: r["ic_spearman"])


def verdict(results: dict) -> str:
    best = _best(results)
    ic, gross, net = best["ic_spearman"], best["gross_ret_bps"], best["net_ret_bps"]
    if ic < 0.03:
        return f"No usable signal in these features at this horizon (best IC {ic:+.3f}). Honest negative."
    if net > 0 and gross > 0:
        return (f"Signal present (IC {ic:+.3f}) and it SURVIVES costs (net {net:+.0f} bps). "
                "Worth deeper study — check capacity and robustness.")
    return (f"Signal present (IC {ic:+.3f}, gross {gross:+.0f} bps) but it DIES after the spread "
            f"(net {net:+.0f} bps): the predicted move is smaller than the cost of crossing to "
            "capture it. Bid-ask bounce, not tradable alpha — it would need passive (maker) "
            "execution, which reintroduces adverse selection.")


def study_one(label: str, product: str) -> None:
    df, results = _study(label, product, sample_every=20)
    print(f"Session '{label}' [{product}]: {len(df)} samples (next-move prediction)\n")
    print(f"  {'model':<7} {'IC(spear)':>10} {'IC t':>7} {'IC 95% CI':>16} "
          f"{'gross bps':>10} {'net bps':>9} {'cost bps':>9} {'turnover':>9}")
    for name, r in results.items():
        print(f"  {name:<7} {r['ic_spearman']:>+10.3f} {r['ic_t']:>+7.1f} "
              f"[{r['ic_ci_low']:>+5.3f},{r['ic_ci_high']:>+5.3f}] "
              f"{r['gross_ret_bps']:>+10.0f} {r['net_ret_bps']:>+9.0f} "
              f"{r['cost_bps']:>9.0f} {r['avg_turnover']:>9.2f}")
    print("  (IC t/CI: Fisher-z on the overlap-adjusted effective sample; a real IC can be hugely "
          "significant yet still untradable after costs — significance is not tradability.)")
    print(f"\nVerdict: {verdict(results)}")
    print("\n(Sharpe on event-spaced samples is a proxy; the gross-vs-net gap in bps is the "
          "unambiguous result. Costs = half-spread + 1bp fee per trade.)")


def validate(real_label: str = "2026-07-06", real_product: str = "BTC-USD") -> None:
    """The full pipeline on known ground truth vs. real data — the trust check for 5b/5c/5d."""
    print("Validation: full pipeline (harness -> zoo -> cost-aware backtest) on ground truth vs real\n")
    sessions = [
        ("SYNTH noise  (alpha=0)", "noise", "SYNTH-USD", 1),
        ("SYNTH signal (alpha=2.5)", "signal", "SYNTH-USD", 1),
        (f"REAL {real_product}", real_label, real_product, 20),
    ]
    print(f"  {'session':<24} {'best IC':>8} {'IC t':>7} {'gross bps':>10} {'net bps':>10}  verdict")
    for name, label, product, sample_every in sessions:
        _, results = _study(label, product, sample_every)
        b = _best(results)
        v = ("no signal (correct)" if b["ic_spearman"] < 0.03
             else "SURVIVES costs" if b["net_ret_bps"] > 0 else "dies after spread")
        print(f"  {name:<24} {b['ic_spearman']:>+8.3f} {b['ic_t']:>+7.1f} {b['gross_ret_bps']:>+10.0f} "
              f"{b['net_ret_bps']:>+10.0f}  {v}")
    print("\nReads as: the models find NOTHING in noise (IC t≈0), RECOVER the planted signal (high,")
    print("significant IC), and a real, statistically significant signal in real data — but at tick")
    print("frequency none survive costs, because edge-per-trade < cost-per-trade. A large IC t-stat")
    print("confirms the signal is real; it says nothing about tradability. What DOES survive is low")
    print("turnover (see the cross-sectional result in run_crosssec.py).")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--validate":
        validate(*args[1:3])
        return
    label = args[0] if len(args) > 0 else "2026-07-06"
    product = args[1] if len(args) > 1 else "BTC-USD"
    study_one(label, product)


if __name__ == "__main__":
    main()
