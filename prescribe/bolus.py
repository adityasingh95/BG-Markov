"""The prescriptive bolus entry point — hard-gated on Gate 2 (S-703, INV-1).

``recommend_bolus`` evaluates Gate 2 from the **live** ICR on its first line, on every
call. With ``icr = null`` it raises ``GateNotPassed`` and cannot return — and there is no
parameter, environment variable, or config flag that skips that check. The dosing
arithmetic itself is **EPIC 9**, which lands on top of this merged story; until then, a
call that *passes* the gate raises ``NotImplementedError`` (the gate opened, the
calculator does not yet exist).
"""

from __future__ import annotations

from prescribe.gates import gate2_status, require_gate2


def recommend_bolus(*, icr: float | None) -> float:
    """Recommend a meal/correction bolus — **disabled until Gate 2 passes** (INV-1).

    The gate is evaluated from the live ``icr`` first, on every call; there is no bypass.
    Raises ``GateNotPassed`` when the ICR is unconfirmed (``null``/non-positive), and
    ``NotImplementedError`` when the gate is open (the dosing math is EPIC 9).
    """
    # Gate 2, from live data, every call, no bypass (ADR-7, INV-1).
    require_gate2(gate2_status(icr=icr))

    # Gate 2 is open — but the prescriptive dosing calculator is EPIC 9, blocked on this
    # story being merged. It does not exist yet; do NOT fabricate a dose.
    raise NotImplementedError(
        "Gate 2 is open (confirmed ICR), but the prescriptive bolus calculator is EPIC 9 "
        "and is not yet built. It must not fabricate a dose."
    )
