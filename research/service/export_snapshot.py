"""Precompute the told-story snapshot (findings + construction) to service/snapshot.json.

The construction stack's walk-forward optimizer is ~45s, so it is not something to run in a request
handler; this bakes the results once. The FastAPI service serves this snapshot for /findings and
/construction (falling back to a live compute only if the file is absent), while /backtest stays
live and interactive. Re-run whenever the data or the research modules change.

    cd research && python -m service.export_snapshot
"""

from __future__ import annotations

import time

from . import compute


def main() -> None:
    t0 = time.time()
    print("Building research snapshot (findings + construction)… the optimizer stage is ~45s.")
    snap = compute.build_snapshot()
    dt = time.time() - t0
    f, c = snap["findings"], snap["construction"]
    print(f"  findings: {f['universe']['names']} names, best '{f['selection']['best']}' "
          f"DSR {f['selection']['deflated_sharpe']:.2f}")
    print(f"  construction: composite net Sharpe {c['composite']['net_sharpe']:+.2f}, "
          f"optimized {c['riskmodel'][2]['net_sharpe']:+.2f}")
    print(f"  wrote {compute.SNAPSHOT_PATH} in {dt:.0f}s")


if __name__ == "__main__":
    main()
