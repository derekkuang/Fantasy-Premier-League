"""Feature engineering with strict point-in-time (no-leakage) discipline.

The #1 way a football/betting backtest lies to you is look-ahead leakage: using
information that did not exist before kickoff. `pointintime` provides the as-of
primitives and a guard that make leakage a caught error, not a silent bug.
`build` implements the DuckDB feature store on top of the same contract.
"""
