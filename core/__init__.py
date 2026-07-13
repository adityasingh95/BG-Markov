"""Core package: safety invariants, gates, and guardrails.

Per ADR-6, ``core/safety.py`` (added in S-104) imports nothing from the
project. This package root deliberately stays dependency-free so importing it
can never pull in the heavier feature/model layers.
"""

from __future__ import annotations

__version__ = "0.1.0"
