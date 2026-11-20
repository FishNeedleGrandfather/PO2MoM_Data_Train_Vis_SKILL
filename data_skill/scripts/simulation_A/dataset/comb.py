"""Build nine datasets from the 100 per-variant datasets.

Variant split within every case:
    01-12 -> X (training variants)
    13-15 -> V (validation variants)
    16-20 -> C (test variants)

Angle split within every variant:
    train_angles -> X
    val_angles   -> V
    test_angles  -> C

For example, datasetXVXA.pt means training variants and training angles.
"""

from pathlib import Path
import shutil

import torch


ROOT = Path(__file__).resolve().parent

ANGLE_CODES = {
    "train_angles": "X",
    "val_angles": "V",
    "test_angles": "C",
}
EXPECTED_ANGLE_COUNTS = {
    "train_angles": 57,
    "val_angles": 18,
    "test_angles": 18,
}


def main() -> None:
    datasetXVXA = []
    datasetXVVA = []
    datasetXVCA = []
    datasetVVXA = []
    datasetVVVA = []
    datasetVVCA = []
    datasetCVXA = []
    datasetCVVA = []
    datasetCVCA = []

    datasets = {
        "XVXA": datasetXVXA,
        "XVVA": datasetXVVA,
        "XVCA": datasetXVCA,
        "VVXA": datasetVVXA,
        "VVVA": datasetVVVA,
        "VVCA": datasetVVCA,
        "CVXA": datasetCVXA,
        "CVVA": datasetCVVA,
        "CVCA": datasetCVCA,
    }

    input_paths = [
        ROOT / f"dataset{case}_{index:02d}.pt"
        for case in range(1, 6)
        for index in range(1, 21)
    ]
    missing = [path.name for path in input_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            f"Missing {len(missing)} datasets: {', '.join(missing)}"
        )

    source_bytes = sum(path.stat().st_size for path in input_paths)
    if shutil.disk_usage(ROOT).free < int(source_bytes * 1.1):
        raise OSError(
            "Not enough disk space for the split datasets "
            f"(source size is about {source_bytes / 1024**3:.1f} GiB)."
        )

    for case in range(1, 6):
        for index in range(1, 21):
            path = ROOT / f"dataset{case}_{index:02d}.pt"
            data = torch.load(path, map_location="cpu", weights_only=False, mmap=True)
            variant_id = f"case{case}_{index:02d}"

            if not isinstance(data, dict) or data.get("variant_id") != variant_id:
                raise ValueError(f"Wrong variant metadata: {path.name}")

            samples = data.get("samples")
            if not isinstance(samples, list) or len(samples) != 93:
                raise ValueError(f"Expected 93 samples in {path.name}")
            if len({(s["theta"], s["phi"]) for s in samples}) != 93:
                raise ValueError(f"Repeated or missing angles in {path.name}")

            if index <= 12:
                case_code = "X"
            elif index <= 15:
                case_code = "V"
            else:
                case_code = "C"

            angle_counts = {group: 0 for group in ANGLE_CODES}
            for sample in samples:
                sample["variant_id"] = variant_id
                sample["case_id"] = data["case_id"]
                sample["parameters"] = data["parameters"]
                sample["mesh_sha256"] = data["mesh_sha256"]

                angle_group = sample.get("angle_group")
                if angle_group not in ANGLE_CODES:
                    raise ValueError(
                        f"Unknown angle_group {angle_group!r} in {path.name}"
                    )
                angle_counts[angle_group] += 1
                angle_code = ANGLE_CODES[angle_group]
                datasets[f"{case_code}V{angle_code}A"].append(sample)

            if angle_counts != EXPECTED_ANGLE_COUNTS:
                raise ValueError(
                    f"Unexpected angle counts in {path.name}: {angle_counts}; "
                    f"expected {EXPECTED_ANGLE_COUNTS}"
                )

            print(
                f"{variant_id}: case_split={case_code} "
                f"train={angle_counts['train_angles']} "
                f"val={angle_counts['val_angles']} "
                f"test={angle_counts['test_angles']}",
                flush=True,
            )

    expected_counts = {
        "XVXA": 60 * 57,
        "XVVA": 60 * 18,
        "XVCA": 60 * 18,
        "VVXA": 15 * 57,
        "VVVA": 15 * 18,
        "VVCA": 15 * 18,
        "CVXA": 25 * 57,
        "CVVA": 25 * 18,
        "CVCA": 25 * 18,
    }

    for suffix, dataset in datasets.items():
        if len(dataset) != expected_counts[suffix]:
            raise ValueError(
                f"Sample count mismatch for dataset{suffix}: "
                f"expected {expected_counts[suffix]}, got {len(dataset)}"
            )

        output = ROOT / f"dataset{suffix}.pt"
        temporary = output.with_suffix(output.suffix + ".tmp")
        torch.save(dataset, temporary)
        temporary.replace(output)
        print(f"Saved {len(dataset)} samples to {output.name}", flush=True)


if __name__ == "__main__":
    main()
