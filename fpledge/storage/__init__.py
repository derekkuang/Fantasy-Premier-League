"""Storage layer: DuckDB over the raw/processed Parquet, and prediction tables.

Design rule: PREDICTION tables are write-once and tagged with (model_version,
run_ts). Never overwrite a prediction — that is what makes honest backtesting and
model A/B comparison possible.
"""
