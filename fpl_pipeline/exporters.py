from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, child in value.items():
            name = f"{prefix}_{key}" if prefix else str(key)
            if isinstance(child, dict):
                result.update(flatten(child, name))
            elif isinstance(child, list):
                result[name] = json.dumps(child, separators=(",", ":"), ensure_ascii=False)
            else:
                result[name] = child
    else:
        result[prefix or "value"] = value
    return result


def rows_from(data: Any, *, id_fields: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    id_fields = id_fields or {}
    if isinstance(data, list):
        rows = [flatten(item) for item in data if isinstance(item, (dict, list))]
    elif isinstance(data, dict):
        rows = [flatten(data)]
    else:
        rows = [{"value": data}] if data is not None else []
    for row in rows:
        for key, val in id_fields.items():
            row.setdefault(key, val)
    return rows


def normalize_my_team(data: dict[str, Any], manager_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return one row per current squad pick and one row per chip record."""
    picks = data.get("picks")
    chips = data.get("chips")
    if not isinstance(picks, list):
        raise ValueError("my-team response missing picks list")
    if not isinstance(chips, list):
        raise ValueError("my-team response missing chips list")
    pick_rows = []
    for pick in picks:
        if not isinstance(pick, dict) or pick.get("element") is None:
            raise ValueError("my-team pick missing element player ID")
        row = flatten(pick)
        row["manager_id"] = manager_id
        row["player_id"] = pick["element"]
        pick_rows.append(row)
    chip_rows = []
    for chip in chips:
        if not isinstance(chip, dict):
            raise ValueError("my-team chip row is not an object")
        row = flatten(chip)
        row["manager_id"] = manager_id
        chip_rows.append(row)
    return pick_rows, chip_rows


def write_csv(path: Path, rows: Iterable[dict[str, Any]], *, required: tuple[str, ...] = ()) -> int:
    materialized = list(rows)
    if required and not materialized:
        raise ValueError(f"Refusing to replace {path.name}: response has no rows")
    for field in required:
        if not any(row.get(field) is not None for row in materialized):
            raise ValueError(f"Refusing to replace {path.name}: required identifier {field!r} missing")
    headers = list(dict.fromkeys(k for row in materialized for k in row))
    if not headers:
        headers = list(required) or ["value"]
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(materialized)
            stream.flush()
            os.fsync(stream.fileno())
        with open(temp_name, "r", newline="", encoding="utf-8-sig") as stream:
            if next(csv.reader(stream), None) != headers:
                raise ValueError(f"CSV validation failed for {path.name}")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return len(materialized)


def snapshot(path: Path, rows: list[dict[str, Any]], name: str) -> bool:
    """Write a timestamped snapshot only when normalized content differs."""
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
    directory = path.parent / "snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    for existing in directory.glob(f"{name}_*.csv"):
        marker = existing.with_suffix(".sha256")
        if marker.exists() and marker.read_text(encoding="ascii").strip() == digest:
            return False
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snap_path = directory / f"{name}_{stamp}.csv"
    write_csv(snap_path, rows)
    snap_path.with_suffix(".sha256").write_text(digest, encoding="ascii")
    return True
