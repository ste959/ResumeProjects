# Reproducing the research

Every number in the research notes is regenerable from a single command, deterministically. This
document records how, and the discipline that makes the results reproducible rather than one-off.

## Determinism

The studies are deterministic given their inputs:

- **Data is cached.** The first run of a study fetches bars from Alpaca and writes them to a local
  Parquet cache; every subsequent run reads the cache, so the *inputs* don't change between runs.
  Re-fetch explicitly with `--refresh`. (Cached data lives under `research/data/` and is git-ignored —
  IEX market data isn't ours to redistribute — so reproduction needs your own free Alpaca keys once.)
- **Seeds are pinned.** The only stochastic step is the block-bootstrap confidence interval
  (`mds/validation.py: block_bootstrap_sharpe_ci`), which uses a fixed `seed=0`. Synthetic-data tests
  use fixed `numpy.random.default_rng(seed)` generators. There is no wall-clock or unseeded randomness
  in the analysis path.
- **No look-ahead.** All backtests are walk-forward: weights/signals at time *t* use only data through
  *t*, and returns are earned on *t → t+1*. This is asserted by tests, not just claimed.

## Commands

```bash
cd research
pip install -r requirements.txt                       # numpy, pandas, scipy, scikit-learn, ...

export ALPACA_KEY_ID=...      export ALPACA_SECRET_KEY=...   # free Alpaca keys (data feed only)

python run_assetalloc.py          # multi-asset allocation note (cached after first run)
python run_assetalloc.py --refresh  # force a re-fetch from Alpaca
python run_trend.py               # enhanced trend-following ablation (cached after first run)
python run_crosssec.py            # the equity factor "honest null" study
python run_microstructure.py --validate   # the microstructure plumbing/validation study

python -m pytest -q               # 179 tests: pure cores, no network, fully deterministic
```

## What "reproducible" means here

- Same keys + same date window → **byte-identical** study output (data cached, seeds fixed).
- The pure analytical cores (`mds/assetalloc.py`, `mds/validation.py`, `mds/portfolio.py`, …) are unit
  tested **without any network or live broker**, so the math reproduces even with no data access.
- Results are reported with confidence intervals and the full overfitting gauntlet, so "reproducible"
  means the *uncertainty* reproduces too — not just a point estimate that happened to land somewhere.
