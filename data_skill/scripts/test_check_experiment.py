"""Small no-FEKO checks for manifest boundary cases."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from check_experiment import check


EXAMPLE = json.loads(
    (Path(__file__).resolve().parent.parent / "references" / "case6-12directions.json")
    .read_text(encoding="utf-8")
)


class ExperimentCheckTests(unittest.TestCase):
    def test_fixed_mesh_without_cfx(self):
        manifest = copy.deepcopy(EXAMPLE)
        geometry = manifest["geometries"][0]
        geometry["geometry_kind"] = "fixed_mesh"
        geometry.pop("cfx")
        with patch.object(Path, "read_text", return_value=json.dumps(manifest)), \
             patch.object(Path, "is_file", return_value=True) as is_file, \
             patch.object(Path, "stat", return_value=SimpleNamespace(st_size=1)):
            result = check(Path("memory.json"), check_files=True)
        self.assertEqual(result["directions_per_geometry"], 12)
        self.assertEqual(is_file.call_count, 3)  # CFM, NAS, PRE only

    def test_phi_360_cannot_duplicate_phi_0_across_groups(self):
        manifest = copy.deepcopy(EXAMPLE)
        manifest["directions"][1] = {"theta": 35, "phi": 360, "group": "test"}
        with patch.object(Path, "read_text", return_value=json.dumps(manifest)):
            with self.assertRaisesRegex(ValueError, "canonical phi"):
                check(Path("memory.json"))

    def test_frequency_must_be_finite_nonboolean(self):
        for invalid in (True, float("inf")):
            manifest = copy.deepcopy(EXAMPLE)
            manifest["frequency_hz"] = invalid
            with self.subTest(invalid=invalid), patch.object(
                Path, "read_text", return_value=json.dumps(manifest)
            ):
                with self.assertRaisesRegex(ValueError, "finite positive"):
                    check(Path("memory.json"))


if __name__ == "__main__":
    unittest.main()
