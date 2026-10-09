"""Content-addressed input releases. Parsed rows and provenance share the same bytes."""

from functools import lru_cache
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import tempfile

import pandas as pd


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@lru_cache(maxsize=6)
def _parquet(digest: str, payload: bytes) -> pd.DataFrame:
    if sha256(payload) != digest:
        raise ValueError("Snapshot checksum does not match parsed bytes")
    frame = pd.read_parquet(BytesIO(payload))
    required = {"ticker", "year", "item_code", "value"}
    if not required.issubset(frame.columns):
        raise ValueError("BCTC thiếu cột: " + ", ".join(sorted(required - set(frame.columns))))
    return frame


def read_parquet(path: Path) -> tuple[pd.DataFrame, str, bytes]:
    payload = path.read_bytes()
    digest = sha256(payload)
    return _parquet(digest, payload), digest, payload


def clear_cache():
    _parquet.cache_clear()


def read_release(directory: Path) -> tuple[list[tuple[Path, bytes, str]], str]:
    """A sealed release is rejected if any declared file changed or disappeared."""
    directory = Path(directory).resolve()
    manifest_path = directory / "release.json"
    declared = None
    if manifest_path.exists():
        declared = json.loads(manifest_path.read_text(encoding="utf-8"))
        if declared.get("schema_version") != "1.0.0":
            raise ValueError("Unsupported snapshot release schema")
        inventory = declared.get("files")
        if not isinstance(inventory, dict) or not inventory:
            raise ValueError("Snapshot release has no file inventory")
        paths = []
        for name in sorted(inventory):
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()) or path.suffix != ".parquet":
                raise ValueError("Invalid path in snapshot release")
            paths.append(path)
    else:
        paths = sorted(directory.glob("*/*.parquet"))
    entries = []
    inventory = {}
    for path in paths:
        payload = path.read_bytes()
        digest = sha256(payload)
        relative = path.relative_to(directory).as_posix()
        inventory[relative] = {"sha256": digest, "bytes": len(payload)}
        if declared and inventory[relative] != declared["files"][relative]:
            raise ValueError(f"Snapshot release integrity failed: {relative}")
        entries.append((path, payload, digest))
    version = sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode())
    if declared and declared.get("dataset_version") != version:
        raise ValueError("Snapshot release version mismatch")
    return entries, version


def seal_release(source: Path, destination: Path) -> Path:
    """Copy an input set into an immutable, hash-named release without changing input."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    entries, version = read_release(source)
    if not entries:
        raise ValueError("No Parquet files to seal")
    destination.mkdir(parents=True, exist_ok=True)
    final = destination / version
    if final.exists():
        read_release(final)
        return final
    stage = Path(tempfile.mkdtemp(prefix=".release-", dir=destination))
    try:
        inventory = {}
        for path, payload, digest in entries:
            relative = path.relative_to(source)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            inventory[relative.as_posix()] = {"sha256": digest, "bytes": len(payload)}
        manifest = {"schema_version": "1.0.0", "dataset_version": version, "files": inventory}
        (stage / "release.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
        read_release(stage)
        try:
            os.rename(stage, final)
        except FileExistsError:
            read_release(final)
        return final
    finally:
        if stage.exists() and stage.resolve().is_relative_to(destination.resolve()):
            shutil.rmtree(stage)
