import os
from pathlib import Path


def load_environment(path: Path | None = None):
    path = path or Path.cwd() / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith(("VNRESEARCH_", "VNSTOCK_", "LLM_", "JEV_", "TYPESAFE_")):
            os.environ.setdefault(key, value.strip().strip("\"'"))
