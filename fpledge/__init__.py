"""fpledge — an FPL-first football prediction system.

One shared Dixon-Coles match engine emits a per-fixture scoreline probability
matrix. Everything derives from that single object:

    FPL      : expected points (xP), captain / transfer / differential picks
    Betting  : an HONEST calibration & closing-line-value (CLV) benchmark
               — NOT a profit product (EPL markets are efficient)

See README.md for the design rationale and the honest scope of each output.
"""

__version__ = "0.1.0"
