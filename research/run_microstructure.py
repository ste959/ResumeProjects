"""Microstructure ML study: can order-book features predict the next mid move, and does the
edge survive the spread?

Runs the model zoo (linear → gradient boosting → small neural net) with walk-forward
out-of-sample validation over a recorded L2 session, then the cost-aware acid test. The point
is the gross-vs-net gap, not a headline Sharpe.

    python run_microstructure.py [session-label] [product]   # taker study of one session
    python run_microstructure.py --validate                  # ground-truth vs real comparison
    python run_microstructure.py --maker [label] [product]   # maker execution: spread vs adverse selection

Examples:
    python run_microstructure.py 2026-07-06 BTC-USD
    python run_microstructure.py signal SYNTH-USD

Note: `study_one` samples the book every 20 events, so on the short synthetic sessions it shows
only a weak IC. The headline synthetic numbers (noise IC≈0, signal IC≈0.9) come from `--validate`,
which samples every event — and, importantly, the signal "recovery" there is a PLUMBING check, not
proof of modeling (the generator writes the signal as the feature). See `--validate`'s own output,
which contrasts it with a non-circular latent-signal test where the model earns a modest, honest IC.
"""

from __future__ import annotations

import sys
import warnings

from mds import lob, maker, models

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
    print("  (IC t/CI: Fisher-z on the overlap-adjusted effective sample. Two caveats keep this "
          "honest: the t is an UPPER bound — adjacent book events are serially dependent — AND it "
          "is the max over 3 models with NO selection correction (unlike the DSR/PBO on the equity")
    print("   side). So the verdict rests on the gross-vs-net gap, not on IC significance.)")
    print(f"\nVerdict: {verdict(results)}")
    print("\n(Sharpe on event-spaced samples is a proxy; the gross-vs-net gap in bps — and the maker "
          "study (--maker) — are the unambiguous results. Costs = half-spread + 1bp fee per trade.)")


def validate(real_label: str = "2026-07-06", real_product: str = "BTC-USD") -> None:
    """The full pipeline on known ground truth vs. real data — the trust check for 5b/5c/5d."""
    print("Validation: full pipeline (harness -> zoo -> cost-aware backtest) on ground truth vs real\n")
    sessions = [
        ("SYNTH noise  (alpha=0)", "noise", "SYNTH-USD", 1),
        ("SYNTH signal (alpha=2.5)", "signal", "SYNTH-USD", 1),
        (f"REAL {real_product}", real_label, real_product, 20),
    ]
    print(f"  {'session':<26} {'best IC':>8} {'IC t':>7} {'gross bps':>10} {'net bps':>10}  verdict")
    for name, label, product, sample_every in sessions:
        _, results = _study(label, product, sample_every)
        b = _best(results)
        v = ("no signal (correct)" if b["ic_spearman"] < 0.03
             else "SURVIVES costs" if b["net_ret_bps"] > 0 else "dies after spread")
        print(f"  {name:<26} {b['ic_spearman']:>+8.3f} {b['ic_t']:>+7.1f} {b['gross_ret_bps']:>+10.0f} "
              f"{b['net_ret_bps']:>+10.0f}  {v}")

    # Non-circular ground truth: latent signal, NOISY INDIRECT features (see docstring).
    latent = lob.synthetic_latent_panel()
    lat = models.evaluate(latent, folds=5, fee_bps=1.0, horizon=1)
    lb = _best(lat)
    ceiling = float(latent["ceiling_ic"].iloc[0])
    print(f"  {'SYNTH latent (indirect)':<26} {lb['ic_spearman']:>+8.3f} {lb['ic_t']:>+7.1f} "
          f"{lb['gross_ret_bps']:>+10.0f} {lb['net_ret_bps']:>+10.0f}  earns < ceiling IC {ceiling:.2f}")

    print("\nReads as — two DIFFERENT kinds of synthetic check:")
    print(" • SYNTH noise/signal are a PLUMBING + false-positive test: the generator writes the")
    print("   signal AS the feature (imbalance ≡ the planted skew), so noise→IC≈0 is meaningful but")
    print("   the +0.92 'recovery' is tautological — it proves no-leakage/scaler discipline, not")
    print("   that a model finds signal it wasn't handed. IC t≈90 there is inflated by serial")
    print("   dependence and is an UPPER bound, not a confidence statement.")
    print(" • SYNTH latent is the honest MODELING test: the label is driven by a hidden state and")
    print("   the features are noisy indirect proxies, so the model must denoise several weak views.")
    print(f"   It earns a modest IC below the {ceiling:.2f} ceiling — real extraction, not a tautology.")
    print(" • REAL BTC has a genuine signal that still DIES after the spread (edge < cost per trade).")
    print("   Significance is not tradability; what survives is low turnover (see run_crosssec.py).")


def maker_verdict(two: dict, split: dict) -> str:
    if two["n_fills"] == 0:
        return "No fills — spread too wide or path too short to post passively."
    base = (f"A two-sided maker earns only {two['spread_bps']:+.3f} bps of half-spread per fill and "
            f"pays {two['adverse_bps']:+.3f} bps of adverse selection → net {two['net_bps']:+.3f} bps/fill. ")
    lift = split["aligned_net_bps"] - split["contra_net_bps"]
    if lift > 0.03:
        discern = (f"The signal DOES have informational value — fills it endorsed net "
                   f"{split['aligned_net_bps']:+.3f} vs {split['contra_net_bps']:+.3f} bps for fills it "
                   f"warned against (+{lift:.3f} lift), i.e. it genuinely predicts which fills dodge "
                   "adverse selection. ")
    else:
        discern = (f"The signal barely discriminates (endorsed {split['aligned_net_bps']:+.3f} vs warned "
                   f"{split['contra_net_bps']:+.3f} bps). ")
    if split["aligned_net_bps"] <= 0:
        close = ("But BTC-USD is an effectively *locked* 1-tick market: there is almost no spread to "
                 "earn, so even the good fills stay net-negative. Untradable as a maker too — not "
                 "because the signal is empty, but because there is no spread to monetize it. The taker "
                 "died to fees; the maker dies to a locked book. Real signal, no microstructure edge.")
    else:
        close = ("And the endorsed fills clear adverse selection on net — worth a capacity/robustness "
                 "study with realistic queue and fees.")
    return base + discern + close


def maker_study(label: str, product: str) -> None:
    df = lob.build_panel(lob.capture_path(label), product=product, sample_every=1, horizon=1, depth=5)
    if df.empty:
        print(f"No data for '{label}' [{product}].")
        return
    mid, spr = df["mid"].to_numpy(), df["spread_bps"].to_numpy()
    print(f"Maker-execution study '{label}' [{product}]: {len(df)} events (every book change)\n")
    two = maker.maker_backtest(mid, spr, inv_cap=10)
    pred = models.walk_forward_predict(df, lob.FEATURES, models._model_factories()["ridge"],
                                       folds=5, embargo=1)
    split = maker.signal_split(two, pred)

    print(f"  two-sided maker: {two['n_fills']} fills | half-spread earned {two['spread_bps']:+.3f} bps"
          f" | adverse selection {two['adverse_bps']:+.3f} bps | NET {two['net_bps']:+.3f} bps/fill")
    print("  signal as a fill filter (does it predict which fills to keep?):")
    print(f"    fills the model ENDORSED   ({split['aligned_fills']:>7}): net {split['aligned_net_bps']:+.3f} bps")
    print(f"    fills the model WARNED of  ({split['contra_fills']:>7}): net {split['contra_net_bps']:+.3f} bps")
    print("  (per fill: half-spread EARNED + signed markout (adverse selection); crossed/locked books "
          "skipped. Fills ignore queue position — optimistic on volume, per-fill economics unaffected.)")
    print(f"\nVerdict: {maker_verdict(two, split)}")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--validate":
        validate(*args[1:3])
        return
    if args and args[0] == "--maker":
        rest = args[1:]
        maker_study(rest[0] if rest else "2026-07-06", rest[1] if len(rest) > 1 else "BTC-USD")
        return
    label = args[0] if len(args) > 0 else "2026-07-06"
    product = args[1] if len(args) > 1 else "BTC-USD"
    study_one(label, product)


if __name__ == "__main__":
    main()
