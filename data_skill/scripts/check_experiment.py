"""Read-only structural check for a new explicit-direction experiment manifest."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path


def check(path: Path, check_files: bool = False) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manifest must be a JSON object")
    experiment_id = data.get("experiment_id")
    if not isinstance(experiment_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", experiment_id):
        raise ValueError("experiment_id must be a stable filename-safe identifier")
    frequency = data.get("frequency_hz")
    if type(frequency) not in (int, float) or not math.isfinite(frequency) or frequency <= 0:
        raise ValueError("frequency_hz must be a finite positive number")
    for key in ("material", "polarization"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f"{key} must be recorded")
    geometries = data.get("geometries")
    if not isinstance(geometries, list) or not geometries:
        raise ValueError("geometries must be a nonempty list")
    ids = set()
    for geometry in geometries:
        if not isinstance(geometry, dict):
            raise ValueError("Each geometry must be an object")
        gid = geometry.get("geometry_id")
        if not isinstance(gid, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", gid):
            raise ValueError(f"Invalid geometry_id: {gid!r}")
        if gid in ids:
            raise ValueError(f"Repeated geometry_id: {gid}")
        ids.add(gid)
        for key in ("family", "geometry_split", "cad_units", "cfm", "nas", "pre"):
            if not isinstance(geometry.get(key), str) or not geometry[key].strip():
                raise ValueError(f"{gid}: missing {key}")
        kind = geometry.get("geometry_kind")
        if kind not in ("fixed_mesh", "parameterized_cad"):
            raise ValueError(f"{gid}: geometry_kind must be fixed_mesh or parameterized_cad")
        cfx = geometry.get("cfx")
        if kind == "parameterized_cad" and (not isinstance(cfx, str) or not cfx.strip()):
            raise ValueError(f"{gid}: parameterized_cad requires cfx")
        if cfx is not None and (not isinstance(cfx, str) or not cfx.strip()):
            raise ValueError(f"{gid}: cfx must be a nonempty path when provided")
        if geometry["geometry_split"] not in ("train", "dev", "test"):
            raise ValueError(f"{gid}: unknown geometry_split")
        if check_files:
            for key in ("cfm", "nas", "pre") + (("cfx",) if cfx is not None else ()):
                candidate = path.parent / geometry[key]
                if not candidate.is_file() or candidate.stat().st_size == 0:
                    raise FileNotFoundError(f"{gid}: missing or empty {key}: {candidate}")
    directions = data.get("directions")
    if not isinstance(directions, list) or not directions:
        raise ValueError("directions must be a nonempty list of explicit pairs")
    if type(data.get("expected_direction_count")) is not int or data["expected_direction_count"] != len(directions):
        raise ValueError("expected_direction_count differs from directions length")
    pairs = set()
    groups = Counter()
    for number, direction in enumerate(directions, 1):
        if not isinstance(direction, dict):
            raise ValueError(f"Direction {number} must be an object")
        theta, phi, group = (direction.get(k) for k in ("theta", "phi", "group"))
        if type(theta) is not int or not 0 <= theta <= 180 or type(phi) is not int or not 0 <= phi < 360:
            raise ValueError(f"Direction {number} requires integer theta in [0,180] and canonical phi in [0,360); use phi=0 instead of 360")
        if group not in ("train", "dev", "test"):
            raise ValueError(f"Direction {number} has unknown group: {group!r}")
        pair = theta, phi
        if pair in pairs:
            raise ValueError(f"Duplicate direction pair: {pair}")
        pairs.add(pair)
        groups[group] += 1
    return {
        "experiment_id": experiment_id,
        "geometries": len(ids),
        "directions_per_geometry": len(pairs),
        "paired_solves_per_geometry": 2 * len(pairs),
        "angle_groups": dict(groups),
        "mesh_files_checked": check_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--check-files", action="store_true")
    args = parser.parse_args()
    try:
        result = check(args.manifest.resolve(), args.check_files)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Experiment check failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
