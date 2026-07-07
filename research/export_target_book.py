"""Export today's TARGET BOOK for the live executor — the research→execution handoff.

The alpha research lives in Python; the live OMS is Java. Real desks bridge them with a file: the
research writes a target portfolio (weights + reference prices), the executor reads it and trades
*toward* it. This writes `backend/target-book/target-book.json` from the beta+sector-neutral
momentum book on the latest date.

⚠️  This exists to validate the execution PLUMBING (does signal → order → fill → reconcile work),
NOT to deploy alpha: the research found NO statistically significant edge (Deflated Sharpe ≈0.11).
Sizing (gross capital, vol target) and risk limits live on the Java side.

    python export_target_book.py
"""

from __future__ import annotations

import json
from pathlib import Path

from mds import crosssec as xs

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = REPO_ROOT / "backend" / "target-book" / "target-book.json"


def main() -> None:
    px, rets = xs.returns_panel()
    mom = xs.signals(px, rets)["momentum"]
    # Beta- and sector-neutral, dollar-neutral, unit-gross weights on the most recent date.
    weights = xs.neutralized_weights(mom, rets)
    asof = weights.index[-1]
    w = weights.loc[asof]
    w = w[w.abs() > 1e-6]                       # drop ~zero weights
    prices = px.loc[asof]

    names = [
        {"symbol": s, "weight": round(float(w[s]), 6), "price": round(float(prices[s]), 4)}
        for s in w.index if s in prices.index and prices[s] == prices[s]  # price not NaN
    ]
    book = {
        "asOf": str(asof.date()),
        "strategy": "neutralized_momentum",
        "note": "PLUMBING TEST ONLY — no validated edge (Deflated Sharpe ~0.11). Not alpha.",
        "grossLong": round(float(w[w > 0].sum()), 4),   # ~+0.5 for a dollar-neutral unit-gross book
        "grossShort": round(float(w[w < 0].sum()), 4),  # ~-0.5
        "names": names,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(book, indent=2))
    print(f"Wrote {len(names)} target weights (asOf {book['asOf']}, long {book['grossLong']:+.2f} / "
          f"short {book['grossShort']:+.2f}) -> {OUT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
