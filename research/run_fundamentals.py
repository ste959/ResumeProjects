"""SEC-EDGAR fundamentals study — the value/quality/accruals/investment factors the price-only
study could not reach, tested with the SAME honest statistics (run_crosssec.py's harness).

The one thing that makes fundamentals honest is POINT-IN-TIME discipline: each factor uses the most
recent number whose 10-Q/10-K was FILED on or before the trading day (see mds/edgar.py). Using the
fiscal-period end date instead would leak ~40–75 days of look-ahead and manufacture alpha.

    python run_fundamentals.py     # fetches ~123 companies from SEC once, then reads local cache

Reporting mirrors run_crosssec.py: per-factor net Sharpe / HAC t / bootstrap CI / turnover, a
Bonferroni 'sig?' bar across the fundamental family, selection-aware Deflated Sharpe + PBO of the
best, and the beta+sector-neutralized version of the best (fundamentals should be tested
factor-neutral too)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mds import crosssec as xs
from mds import edgar
from mds import validation as val


def _daily_sharpe(net: pd.Series) -> float:
    r = net.dropna()
    s = r.std(ddof=0)
    return float(r.mean() / s) if s > 0 and len(r) else 0.0


def _coverage(panels: dict[str, pd.DataFrame]) -> tuple[int, dict[str, int]]:
    """How many names ever had a usable value for each field, and for any field (the real N)."""
    per = {f: int(p.notna().any(axis=0).sum()) for f, p in panels.items()}
    any_name = pd.concat([p.notna().any(axis=0) for p in panels.values()], axis=1).any(axis=1)
    return int(any_name.sum()), per


def verdict(results: dict, hac_t: dict, dsr: float, pbo: float, zbar: float,
            price_only: bool = True) -> str:
    passers = {nm: hac_t[nm] for nm in results if abs(hac_t[nm]) >= zbar}
    winners = {nm: t for nm, t in passers.items() if results[nm]["net_sharpe"] > 0}
    n = len(results)
    if winners and dsr > 0.95 and pbo < 0.3:
        best = max(winners, key=lambda nm: results[nm]["net_sharpe"])
        return (f"Fundamentals DO clear the bar where price-only did not: '{best}' passes Bonferroni "
                f"(|t|>{zbar:.2f} for {n} tests, t={hac_t[best]:+.2f}), Deflated Sharpe {dsr:.2f}, "
                f"PBO {pbo:.2f} — a defensible candidate given point-in-time discipline; validate live.")
    if passers:
        names = sorted(passers, key=lambda k: -abs(hac_t[k]))
        lst = ", ".join(f"{k} (t={hac_t[k]:+.2f})" for k in names)
        alllose = all(results[k]["net_sharpe"] < 0 for k in names)
        tail = (f" {len(names)} factor(s) clear the corrected bar |t|>{zbar:.2f} — {lst} — but "
                + ("ALL are LOSERS (a short-side effect / cost artefact), not tradable long edges."
                   if alllose else "the Deflated Sharpe/PBO still flag it as selection, not skill."))
    else:
        tail = (f" Applied symmetrically, NO factor — winner or loser — clears the Bonferroni bar "
                f"(|t|>{zbar:.2f} for {n} tests).")
    return (f"NO fundamental edge survives honest statistics on this sample — same verdict as the "
            f"price-only study. Deflated Sharpe of best {dsr:.2f} (needs >0.95), PBO {pbo:.2f}.{tail} "
            "The factors are real in the literature; this 123-name / ~5.9y mega-cap panel is simply "
            "too short and too selected (few independent quarterly obs) to resolve them.")


def main() -> None:
    px, rets = xs.returns_panel()
    print(f"Universe: {px.shape[1]} names, {px.shape[0]} days "
          f"({px.index.min().date()} .. {px.index.max().date()})")

    print("Fetching SEC-EDGAR company facts (cached after first run)…")
    facts = edgar.load_all_facts(list(px.columns))
    panels = edgar.fundamental_panels(px, facts=facts)
    n_any, per_field = _coverage(panels)
    print(f"Fundamentals coverage: {n_any}/{px.shape[1]} names have usable data. Per field: "
          + ", ".join(f"{f}={c}" for f, c in per_field.items()))

    sigs = edgar.fundamental_signals(px, facts=facts)
    results = {name: xs.backtest(sig, rets, cost_bps=5.0) for name, sig in sigs.items()}

    hac_t = {n: val.newey_west_sharpe_tstat(r["net"].dropna().to_numpy()) for n, r in results.items()}
    boot = {n: val.block_bootstrap_sharpe_ci(r["net"].dropna().to_numpy()) for n, r in results.items()}
    zbar = val.bonferroni_z(len(results))            # family-corrected |t| bar across the 5 factors

    print(f"\n  {'factor':<20} {'net Shrp':>9} {'HAC t':>7} {'boot 95% CI':>16} {'sig?':>5} "
          f"{'turnover':>9} {'days':>6}")
    for name, r in results.items():
        lo, hi = boot[name]
        s = "yes" if abs(hac_t[name]) >= zbar else "no"
        print(f"  {name:<20} {r['net_sharpe']:>+9.2f} {hac_t[name]:>+7.2f} "
              f"[{lo:>+5.2f},{hi:>+5.2f}] {s:>5} {r['avg_turnover']:>9.3f} {r['days']:>6}")
    print(f"  (HAC t: Newey–West. 'sig?' uses the BONFERRONI bar |t|>{zbar:.2f} for {len(results)} "
          "simultaneous tests, winners and losers alike. CI: moving-block bootstrap.)")

    # Selection-aware statistics across the fundamental family: Deflated Sharpe of best + PBO.
    from scipy.stats import kurtosis, skew

    net_mat = pd.DataFrame({n: r["net"] for n, r in results.items()}).dropna()
    daily_sh = {n: _daily_sharpe(results[n]["net"]) for n in results}
    var_trials = float(np.var(list(daily_sh.values()), ddof=1))
    best = max(results, key=lambda n: results[n]["net_sharpe"])
    b = results[best]["net"].dropna().to_numpy()
    dsr = val.deflated_sharpe(_daily_sharpe(results[best]["net"]), len(b),
                              float(skew(b)), float(kurtosis(b, fisher=False)),
                              n_trials=len(results), sharpe_var_across_trials=var_trials)
    pbo_res = val.pbo(net_mat.to_numpy(), n_splits=12)

    print(f"\nSelection-aware (across all {len(results)} fundamental factors):")
    print(f"  Deflated Sharpe of best ('{best}'): {dsr:.3f}   (prob. true Sharpe > 0 after deflating "
          "for multiple testing; >0.95 is the bar)")
    print(f"  PBO (prob. of backtest overfitting): {pbo_res['pbo']:.3f}   over {pbo_res['n_combos']} "
          "CPCV splits")

    # Factor-neutral test of the best: fundamentals should not merely re-express market/sector beta.
    sig = sigs[best]
    rw, nw = xs.raw_weights(sig), xs.neutralized_weights(sig, rets)
    raw_b = float(xs.book_beta(rw, rets).abs().mean())
    neu_b = float(xs.book_beta(nw, rets).abs().mean())
    nbt = xs.backtest(sig, rets, weights=nw)
    nt = val.newey_west_sharpe_tstat(nbt["net"].dropna().to_numpy())
    print(f"\nFactor-neutral best ('{best}'): mean |net market β| {raw_b:.3f} (dollar-neutral) → "
          f"{neu_b:.3f} (β + sector-neutral).")
    print(f"  Beta/sector-neutral net Sharpe {nbt['net_sharpe']:+.2f} (HAC t={nt:+.2f}) — whether the "
          "factor is more than disguised sector/beta exposure.")

    n_best = results[best]["days"]
    mds = val.min_detectable_sharpe(n_best)
    print(f"\nPower: with {n_best} active days this sample can only reliably detect (80% power) an "
          f"annualized Sharpe ≳ {mds:.2f}. Fundamentals update ~quarterly, so the number of "
          "INDEPENDENT observations is far smaller than the day count suggests.")

    print(f"\nVerdict: {verdict(results, hac_t, dsr, pbo_res['pbo'], zbar)}")
    print("\nCaveats: (1) 123 survivorship-selected MEGA-CAPS — the exact names for which value/"
          "quality are weakest (well-covered, efficiently priced). (2) ~5.9y is SHORT for quarterly "
          "fundamentals: ~23 filings/name → few independent obs, low power by construction (see the "
          "power line). (3) No analyst revisions/estimates (the strongest short-horizon fundamental "
          "signal) — SEC gives realised financials only. (4) Point-in-time via FILING date, not "
          "period end; first-filed values (no restatement look-ahead), but SEC XBRL tagging is "
          "imperfect and Q4 is derived (annual − 9mo). A real study needs a longer, delisting-"
          "inclusive, point-in-time fundamentals panel across the full cross-section, not mega-caps.")


if __name__ == "__main__":
    main()
