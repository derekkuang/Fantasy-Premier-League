"""Data acquisition: FPL REST API, xG scraping, and the immutable raw landing zone.

Everything fetched lands VERBATIM and timestamped in `data/raw/` before any
parsing. Because raw is immutable and stamped with ingest time, you can always
reconstruct exactly what was known before a deadline — the backbone of honest,
point-in-time backtesting.
"""
