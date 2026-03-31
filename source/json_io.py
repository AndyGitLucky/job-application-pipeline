from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_file(path: str | Path, default: Any = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        try:
            return json.loads(target.read_text(encoding="utf-8-sig"))
        except Exception:
            return default
    except Exception:
        return default
