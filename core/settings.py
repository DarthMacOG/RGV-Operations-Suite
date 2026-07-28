from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path


APP_NAME = "RGV Operations Suite"
DEFAULTS = {
    "logo_path": "",
    "output_folder": str(Path.home() / "Videos" / "RGV Exports"),
    "position": "Bottom Right",
    "opacity": 75,
    "size": 18,
    "margin": 24,
}


def settings_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    return base / "RGVOperationsSuite" / "settings.json"


def load_settings() -> dict:
    values = deepcopy(DEFAULTS)
    path = settings_path()
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            values.update({key: saved[key] for key in DEFAULTS if key in saved})
    except (OSError, ValueError, TypeError):
        pass
    return values


def save_settings(values: dict) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {key: values.get(key, DEFAULTS[key]) for key in DEFAULTS}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    temporary.replace(path)
