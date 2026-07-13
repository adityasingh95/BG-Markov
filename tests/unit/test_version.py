"""S-101: the ``core`` package is importable and carries a version.

Exists so the 90%-coverage gate on ``core/`` has something real to measure at
the skeleton stage rather than passing vacuously on an empty package.
"""

from __future__ import annotations

import core


def test_core_exposes_version() -> None:
    assert isinstance(core.__version__, str)
    assert core.__version__
