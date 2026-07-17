"""The gated output/prescriptive package.

Holds the gate enforcement (``gates.py``, S-703) and the prescriptive bolus entry point
(``bolus.py``). Nothing here produces patient-visible output or a dose without first
passing the invariants in ``core/safety.py``.
"""
