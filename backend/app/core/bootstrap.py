"""Path bootstrap: make the repository root importable so the top-level ``ai`` package
(providers / gateway / guardrails / routing / evaluation) can be imported by the API
layer without packaging tricks.

Repository root == ``<root>/backend/app/core/`` three levels up.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
