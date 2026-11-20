"""Verify that every prepared variant has matched, ordered CFM/NAS meshes."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMALLBATCH = ROOT.parent / "simulation_smallbatch"
sys.path.insert(0, str(SMALLBATCH))

from datasetbuilder_1ghz import parse_nas, verify_cfm_mesh  # noqa: E402


def main() -> int:
    total = 0
    for case_number in range(1, 6):
        case_id = f"case{case_number}"
        triangle_counts: list[int] = []
        for variant_number in range(1, 21):
            variant_id = f"{case_id}_{variant_number:02d}"
            variant_dir = ROOT / case_id / variant_id
            required = [
                variant_dir / f"{variant_id}{suffix}"
                for suffix in (".cfx", ".cfm", ".nas", ".map")
            ]
            missing = [path for path in required if not path.is_file() or path.stat().st_size == 0]
            if missing:
                raise ValueError(f"{variant_id}: missing or empty: {missing}")
            grids, triangles = parse_nas(variant_dir / f"{variant_id}.nas")
            verify_cfm_mesh(variant_dir / f"{variant_id}.cfm", triangles, grids)
            triangle_counts.append(len(triangles))
            total += 1
        print(
            f"{case_id}: 20/20 verified, "
            f"triangles={min(triangle_counts)}..{max(triangle_counts)}"
        )
    print(f"TOTAL: {total}/100 verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
