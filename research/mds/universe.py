"""Point-in-time universe & survivorship-bias handling.

The most common way a backtest lies: it runs on *today's* names. Firms that went to zero or got delisted
aren't in the sample, so the strategy is quietly tested only on survivors — and looks better than it could
ever have traded. The honest fix is a **point-in-time universe**: at each date the strategy may only hold
names that were listed *and not yet delisted* on that date, and when a held name delists the book realizes
the **delisting loss** instead of the name silently vanishing.

`PointInTimeUniverse` derives listing/delisting from where each symbol's price history actually starts and
ends, exposes as-of membership, and carries a `delisting_return` the engine charges on exit. `survivorship_audit`
quantifies the exposure. Fully populating the *delisted* side needs a paid point-in-time source (disclosed
in `ALPHA-DATA-ROADMAP.md`); the mechanism here is exact, and it correctly prevents look-ahead into names
that hadn't listed yet on the free feed. Pure NumPy/pandas — no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PointInTimeUniverse:
    """A price panel plus as-of membership. `delisting_return` is realized on the day a held name exits
    (default −30%, a conservative delisting haircut; use −1.0 for go-to-zero)."""
    prices: pd.DataFrame                 # symbols × dates; NaN where the name is not (yet / no longer) listed
    delisting_return: float = -0.30

    def first_dates(self) -> pd.Series:
        return self.prices.apply(lambda c: c.first_valid_index())

    def last_dates(self) -> pd.Series:
        return self.prices.apply(lambda c: c.last_valid_index())

    def membership_mask(self) -> pd.DataFrame:
        """Boolean panel: True where a name is tradable (between its first and last valid price, inclusive).
        This is the as-of membership the engine consults so it never trades a name before it listed."""
        first, last = self.first_dates(), self.last_dates()
        idx = self.prices.index
        mask = pd.DataFrame(False, index=idx, columns=self.prices.columns)
        for sym in self.prices.columns:
            if first[sym] is not None and last[sym] is not None:
                mask.loc[first[sym]:last[sym], sym] = True
        return mask

    def members_asof(self, date) -> list[str]:
        """Symbols tradable on `date`."""
        row = self.membership_mask().loc[:date]
        return list(row.columns[row.iloc[-1].to_numpy()]) if len(row) else []

    def delistings(self) -> pd.Series:
        """Each name that exits before the panel ends, mapped to its last tradable date (a delisting proxy)."""
        last = self.last_dates()
        end = self.prices.index.max()
        return last[last < end]


def survivorship_audit(prices: pd.DataFrame) -> dict:
    """Quantify survivorship exposure: how much of the universe has full history (the survivors), how many
    names *enter* after the start (IPOs/listings — handled correctly by a PIT backtest), and how many *exit*
    before the end (delistings — the biased-away names). A 'survivors-only' equal-weight return vs. an
    'as-available' PIT equal-weight return estimates the bias where entries/exits exist."""
    u = PointInTimeUniverse(prices)
    first, last = u.first_dates(), u.last_dates()
    start, end = prices.index.min(), prices.index.max()
    entries = [s for s in prices.columns if first[s] is not None and first[s] > start]
    exits = [s for s in prices.columns if last[s] is not None and last[s] < end]
    full = [s for s in prices.columns if first[s] == start and last[s] == end]

    rets = prices.pct_change()
    mask = u.membership_mask()
    pit_ew = (rets.where(mask).mean(axis=1)).dropna()                 # as-available equal weight
    surv_ew = (rets[full].mean(axis=1)).dropna() if full else pd.Series(dtype=float)

    def ann(x):
        return float(x.mean() * 252) if len(x) else float("nan")

    return {
        "n_symbols": len(prices.columns),
        "n_full_history": len(full),
        "n_entries": len(entries), "entries": entries,
        "n_exits": len(exits), "exits": exits,
        "survivors_only_ann_return": round(ann(surv_ew), 4),
        "point_in_time_ann_return": round(ann(pit_ew), 4),
        "survivorship_bias_ann": round(ann(surv_ew) - ann(pit_ew), 4) if full else float("nan"),
    }
