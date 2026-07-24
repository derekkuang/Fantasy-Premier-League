#!/usr/bin/env python3
"""Initialise the DuckDB schema and load the latest landed FPL data.

Run `python scripts/pull_data.py` first to land raw data, then:
    python scripts/build_db.py
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from fpledge import config  # noqa: E402
from fpledge.storage import load  # noqa: E402


def main() -> None:
    counts = load.load_all()
    print(f"loaded into {config.DUCKDB_PATH}:")
    for table, n in counts.items():
        print(f"  {table:10s}: {n}")


if __name__ == "__main__":
    main()
