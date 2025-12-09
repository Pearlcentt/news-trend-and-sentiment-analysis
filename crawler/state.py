from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


class StateStore:
    """Simple JSON-based checkpoint store keyed by feed name."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Dict[str, int]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, state: Dict[str, int]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp_path.replace(self.path)
