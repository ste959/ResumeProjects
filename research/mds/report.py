"""Reporting — the trader/researcher-facing output: a self-contained HTML **tearsheet** and a strategy
**leaderboard**, generated from any `engine.StrategyResult`.

A number in a terminal is a result; a tearsheet is a *tool*. This turns the platform's evaluation, risk,
and attribution into one shareable page — equity curve, drawdown, rolling Sharpe, monthly-return heatmap,
the risk block (VaR/ES, sleeve risk contribution), and P&L attribution — with everything inlined (SVG
sparklines, CSS) so the file opens anywhere with no dependencies. The leaderboard ranks a set of
strategies through the same selection-aware gauntlet.

Pure string generation — no plotting library, no network. `run_report.py` writes the files.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import engine as eng
from . import evaluation as ev
from . import riskmgmt as rm

_ACCENT, _POS, _NEG, _INK, _MUTED, _BORDER = "#4f46e5", "#059669", "#dc2626", "#0f172a", "#64748b", "#e2e8f0"

_CSS = f"""
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:#fff; color:{_INK};
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
.wrap {{ max-width:920px; margin:0 auto; padding:40px 28px 64px; }}
h1 {{ font-size:26px; margin:0 0 2px; letter-spacing:-0.02em; }}
.sub {{ color:{_MUTED}; font-size:13px; margin-bottom:28px; }}
h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:0.08em; color:{_MUTED};
  margin:34px 0 12px; font-weight:600; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; }}
.card {{ border:1px solid {_BORDER}; border-radius:10px; padding:12px 14px; background:#fbfcfe; }}
.card .k {{ font-size:11px; color:{_MUTED}; text-transform:uppercase; letter-spacing:0.05em; }}
.card .v {{ font-size:20px; font-weight:650; margin-top:4px; font-variant-numeric:tabular-nums; }}
.panel {{ border:1px solid {_BORDER}; border-radius:10px; padding:16px; background:#fff; }}
svg {{ display:block; width:100%; height:auto; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; font-size:12.5px; }}
th,td {{ padding:5px 8px; text-align:right; border-bottom:1px solid {_BORDER}; }}
th:first-child, td:first-child {{ text-align:left; color:{_MUTED}; }}
th {{ color:{_MUTED}; font-weight:600; font-size:11px; text-transform:uppercase; letter-spacing:0.04em; }}
.pos {{ color:{_POS}; }} .neg {{ color:{_NEG}; }}
.mono {{ font-variant-numeric:tabular-nums; }}
.foot {{ color:{_MUTED}; font-size:12px; margin-top:36px; }}
.grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
@media (max-width:620px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
"""


def _sparkline(vals, w=860, h=150, stroke=_ACCENT, area=False, zero_line=False) -> str:
    """An inline SVG line/area chart from a numeric series (NaNs dropped). Self-contained, responsive."""
    v = [float(x) for x in vals if np.isfinite(x)]
    if len(v) < 2:
        return "<svg viewBox='0 0 860 150'></svg>"
    lo, hi = min(v), max(v)
    if zero_line:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    span = (hi - lo) or 1.0
    pad = 8
    xs = [pad + i * (w - 2 * pad) / (len(v) - 1) for i in range(len(v))]
    ys = [h - pad - (val - lo) / span * (h - 2 * pad) for val in v]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    parts = [f"<svg viewBox='0 0 {w} {h}' preserveAspectRatio='none'>"]
    if zero_line:
        yz = h - pad - (0.0 - lo) / span * (h - 2 * pad)
        parts.append(f"<line x1='{pad}' y1='{yz:.1f}' x2='{w-pad}' y2='{yz:.1f}' stroke='{_BORDER}' stroke-width='1'/>")
    if area:
        base = h - pad
        parts.append(f"<polygon points='{xs[0]:.1f},{base:.1f} {pts} {xs[-1]:.1f},{base:.1f}' "
                     f"fill='{stroke}' fill-opacity='0.10'/>")
    parts.append(f"<polyline points='{pts}' fill='none' stroke='{stroke}' stroke-width='2' "
                 f"stroke-linejoin='round' stroke-linecap='round'/>")
    parts.append("</svg>")
    return "".join(parts)


def _card(k, v, cls="") -> str:
    return f"<div class='card'><div class='k'>{k}</div><div class='v {cls}'>{v}</div></div>"


def _pct(x, d=1):
    return f"{x*100:+.{d}f}%"


def _monthly_table(net: pd.Series) -> str:
    m = ((1 + net).resample("ME").prod() - 1).to_frame("r")
    m["y"], m["mo"] = m.index.year, m.index.month
    piv = m.pivot_table(index="y", columns="mo", values="r")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    head = "<tr><th>Year</th>" + "".join(f"<th>{mn}</th>" for mn in months) + "<th>Year</th></tr>"
    rows = []
    for y, r in piv.iterrows():
        cells = []
        for mo in range(1, 13):
            val = r.get(mo, np.nan)
            if pd.isna(val):
                cells.append("<td></td>")
            else:
                cls = "pos" if val >= 0 else "neg"
                cells.append(f"<td class='{cls}'>{val*100:+.1f}</td>")
        yr = ((1 + net[net.index.year == y]).prod() - 1)
        cells.append(f"<td class='{'pos' if yr>=0 else 'neg'}'><b>{yr*100:+.1f}</b></td>")
        rows.append(f"<tr><td>{y}</td>{''.join(cells)}</tr>")
    return f"<div class='panel' style='overflow-x:auto'><table>{head}{''.join(rows)}</table></div>"


def tearsheet_html(result: eng.StrategyResult, prices: pd.DataFrame, rf: pd.Series | None = None,
                   sleeves: dict | None = None, rolling_window: int = 126, title: str | None = None) -> str:
    """Render a full, self-contained HTML tearsheet for one strategy result. The covariance for the
    ex-ante risk block is computed from the result's OWN symbols, so it always matches the weights."""
    net = result.net
    s = result.stats
    equity = (1 + net).cumprod()
    dd = equity / equity.cummax() - 1.0
    roll = (net.rolling(rolling_window).mean() / net.rolling(rolling_window).std() * np.sqrt(252)).dropna()
    cols = list(result.weights.columns)
    cov = prices[cols].pct_change().dropna().cov().to_numpy()      # daily cov aligned to this book's names

    cards = "".join([
        _card("Excess Sharpe", f"{s['sharpe']:.2f}"),
        _card("Ann. return", _pct(s["ann_return"]), "pos" if s["ann_return"] >= 0 else "neg"),
        _card("Ann. vol", f"{s['ann_vol']*100:.1f}%"),
        _card("Max drawdown", _pct(s["max_drawdown"]), "neg"),
        _card("Sortino", f"{s['sortino']:.2f}"),
        _card("Calmar", f"{s['calmar']:.2f}"),
        _card("HAC t-stat", f"{s['hac_t']:+.1f}"),
        _card("Avg gross", f"{result.avg_gross:.2f}×"),
    ])

    risk = rm.risk_report(net, weights=result.weights.iloc[-1].reindex(cols), cov=cov, sleeves=sleeves)
    risk_rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in [
        ("Ann. vol", f"{risk['ann_vol']*100:.1f}%"),
        ("VaR 95% (hist)", f"{risk['var_95_hist']*100:.2f}%"),
        ("VaR 95% (Cornish–Fisher)", f"{risk['var_95_cornish_fisher']*100:.2f}%"),
        ("VaR 99%", f"{risk['var_99_hist']*100:.2f}%"),
        ("Expected shortfall 95%", f"{risk['cvar_95']*100:.2f}%"),
    ])
    rc = risk.get("risk_contribution", {})
    rc_rows = "".join(f"<tr><td>{k}</td><td>{v*100:+.0f}%</td></tr>" for k, v in rc.items())

    attr = eng.attribution(result, prices, groups=sleeves)
    pnl = attr.get("per_group", attr["per_asset"])
    pnl_rows = "".join(f"<tr><td>{k}</td><td class='{'pos' if v>=0 else 'neg'}'>{v*100:+.1f}%</td></tr>"
                       for k, v in pnl.items())

    name = title or result.name
    span = f"{net.index[0].date()} → {net.index[-1].date()} · {s['n_days']} trading days"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{name} — tearsheet</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>{name}</h1><div class="sub">Strategy tearsheet · {span} · excess of cash</div>
<div class="cards">{cards}</div>

<h2>Equity curve (growth of $1)</h2><div class="panel">{_sparkline(equity, area=True)}</div>
<h2>Drawdown</h2><div class="panel">{_sparkline(dd, stroke=_NEG, area=True, zero_line=True)}</div>
<h2>Rolling {rolling_window}-day Sharpe</h2><div class="panel">{_sparkline(roll, zero_line=True)}</div>

<h2>Monthly returns (%)</h2>{_monthly_table(net)}

<div class="grid2">
<div><h2>Risk</h2><div class="panel"><table>{risk_rows}</table></div>
{"<h2>Risk contribution</h2><div class='panel'><table>"+rc_rows+"</table></div>" if rc_rows else ""}</div>
<div><h2>P&amp;L attribution</h2><div class="panel"><table>{pnl_rows}</table></div>
<h2>Activity</h2><div class="panel"><table>
<tr><td>Avg gross</td><td>{result.avg_gross:.2f}×</td></tr>
<tr><td>Annual turnover</td><td>{result.turnover_ann:.0f}×</td></tr>
<tr><td>Sharpe 95% CI</td><td>[{s['boot_lo']:.2f}, {s['boot_hi']:.2f}]</td></tr>
<tr><td>Skew</td><td>{s['skew']:+.2f}</td></tr></table></div></div>
</div>

<div class="foot">Generated by the quant platform · walk-forward, excess-of-cash, cost-aware · Sharpe reported
with a Newey–West t-stat and block-bootstrap CI. Not investment advice.</div>
</div></body></html>"""


def leaderboard_html(results: list[eng.StrategyResult], gauntlet: dict, title: str = "Strategy leaderboard") -> str:
    """Rank a set of strategies (best excess Sharpe first) with the selection-aware gauntlet verdict."""
    rows = []
    for r in sorted(results, key=lambda x: x.stats["sharpe"], reverse=True):
        s = r.stats
        rows.append(
            f"<tr><td>{r.name}</td><td>{s['sharpe']:.2f}</td><td>{s['hac_t']:+.1f}</td>"
            f"<td class='{'pos' if s['ann_return']>=0 else 'neg'}'>{s['ann_return']*100:+.1f}%</td>"
            f"<td>{s['ann_vol']*100:.1f}%</td><td class='neg'>{s['max_drawdown']*100:.1f}%</td>"
            f"<td>{s['sortino']:.2f}</td><td>{r.avg_gross:.2f}×</td></tr>")
    g = gauntlet
    clears = abs(g["best_hac_t"]) >= g["bonferroni_t"]
    verdict = (f"Best: <b>{g['best']}</b> (ann. Sharpe {g['best_sharpe_ann']}, HAC t {g['best_hac_t']}). "
               f"Multiple-testing bar |t|&gt;{g['bonferroni_t']} → <b>{'CLEARS' if clears else 'FAILS'}</b>. "
               f"Deflated Sharpe {g['deflated_sharpe']}, PBO {g['pbo']}, "
               f"min-detectable {g['min_detectable_sharpe']}.")
    head = ("<tr><th>Strategy</th><th>exSharpe</th><th>HAC t</th><th>Ann ret</th><th>Ann vol</th>"
            "<th>Max DD</th><th>Sortino</th><th>Gross</th></tr>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>{_CSS}</style></head><body><div class="wrap">
<h1>{title}</h1><div class="sub">{len(results)} strategies · one engine · one selection-aware gauntlet · excess of cash</div>
<div class="panel" style="overflow-x:auto"><table>{head}{''.join(rows)}</table></div>
<h2>Gauntlet</h2><div class="panel" style="line-height:1.7">{verdict}</div>
<div class="foot">Comparing N strategies on one history is multiple testing; the gauntlet deflates for it.</div>
</div></body></html>"""
