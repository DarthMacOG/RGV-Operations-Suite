from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative: str) -> Path:
    """Resolve an asset both from source and from a PyInstaller bundle."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base / relative
