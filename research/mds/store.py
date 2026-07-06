"""Columnar research warehouse: Parquet files queried with DuckDB.

This is the analytical store the research layer reads from. Raw capture (the Java
recorder's append log) is ETL'd here into partitioned Parquet, and historical candles
are cached as Parquet so repeated studies don't re-hit the exchange API. DuckDB gives
us SQL over the columnar files with zero server.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CANDLES_DIR = DATA_DIR / "candles"
CAPTURE_DIR = DATA_DIR / "capture"


def _ensure(dir_: Path) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    return dir_


def candles_path(product: str, granularity: int) -> Path:
    return _ensure(CANDLES_DIR) / f"{product}_{granularity}s.parquet"


def write_parquet(df: pd.DataFrame, path: Path) -> Path:
    _ensure(path.parent)
    df.to_parquet(path, engine="pyarrow", compression="zstd")
    return path


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path, engine="pyarrow")


def query(sql: str) -> pd.DataFrame:
    """Run a DuckDB SQL query (e.g. over parquet/csv globs) and return a DataFrame."""
    con = duckdb.connect()
    try:
        return con.execute(sql).fetchdf()
    finally:
        con.close()


def ingest_capture_log(csv_glob: str) -> Path:
    """Compact the recorder's append-only CSV capture into partitioned Parquet
    (hive-partitioned by product) using a DuckDB COPY — the capture → warehouse ETL."""
    out = _ensure(CAPTURE_DIR)
    con = duckdb.connect()
    try:
        con.execute(
            f"""
            COPY (SELECT * FROM read_csv_auto('{csv_glob}', header=true))
            TO '{out}' (FORMAT PARQUET, PARTITION_BY (product), OVERWRITE_OR_IGNORE 1)
            """
        )
    finally:
        con.close()
    return out
