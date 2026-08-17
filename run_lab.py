"""Convenience entry point for the validation harness — equivalent to ``python -m harness``.

    python run_lab.py                 # run the example suite
    python run_lab.py --out artifacts # …and write results.ndjson / junit.xml / report.json
"""

from __future__ import annotations

import sys

from harness.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
