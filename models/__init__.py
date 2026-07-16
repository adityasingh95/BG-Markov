"""Models (06 §arch): the shared state binner, the baseline, the ordinal model,
and the ICR/ISF estimators.

The state-binner lives here (not in features/) and is the single place a BG is
mapped to a clinical state — used by the baseline, the ordinal model, and the risk
readout alike.
"""
