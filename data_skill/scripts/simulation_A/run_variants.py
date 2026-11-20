"""Sequential FEKO MoM/PO sweep, per-variant dataset build, then safe cleanup."""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import torch
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parent
SMALL = ROOT.parent / "simulation_smallbatch"
sys.path.insert(0, str(SMALL))
import run_simulations as fixed  # noqa: E402
import dataset_builder_AllAngle as builder  # noqa: E402
import datasetbuilder_1ghz as geometry_tools  # noqa: E402
from automation.setup_variants import read_plan  # noqa: E402

ANGLE_GROUPS = {
    "train_angles": [(t, p) for t in (35, 45, 55) for p in range(0, 181, 10)],
    "val_angles": [(t, p) for t in (40, 50) for p in range(5, 86, 10)],
    "test_angles": [(t, p) for t in (40, 50) for p in range(95, 176, 10)],
}
ANGLES = [(t, p, group) for group, pairs in ANGLE_GROUPS.items() for t, p in pairs]
assert len(ANGLES) == 93 and len({(t, p) for t, p, _ in ANGLES}) == 93
METHODS = ("mom", "po")
REMOVE_NAMES = {f"{method}{suffix}" for method in METHODS for suffix in (
    f"_{method}_Currents.os", ".fek", ".str", ".bof", ".ol", ".ffe", ".log", ".out"
)}
REMOVE_NAMES.discard("mom.out")  # Keep convergence evidence.


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pre_sha256(path: Path) -> str:
    # Completion markers hash the generated PRE text (LF newlines). Windows
    # writes CRLF bytes, so hashing the raw file would reject a valid solve.
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def read_template(variant_dir: Path) -> list[str]:
    variant_id = variant_dir.name
    path = variant_dir / f"{variant_id}.pre"
    lines = path.read_text(encoding="utf-8").splitlines()
    for card in ("IN", "FP", "FR", "EN"):
        count = sum(line.strip() == "EN" if card == "EN" else
                    line.startswith(card + ":") or line.startswith(card + " ") for line in lines)
        if count != 1:
            raise ValueError(f"{path}: expected one {card} card, found {count}")
    frequency = next(line for line in lines if line.startswith("FR:"))
    if frequency.split(":")[-1].strip() != "1000000000":
        raise ValueError(f"{path}: expected 1 GHz")
    source_count = sum(line.startswith("A0:") for line in lines)
    current_count = sum(line.startswith("OS:") for line in lines)
    if (source_count, current_count) == (0, 0):
        reference = fixed.base_pre(SMALL / variant_dir.parent.name)
        for card in ("FP:", "EG:", "PS:", "CG:", "DI:", "PW:", "FR:", "NC:"):
            local = [line for line in lines if line.startswith(card)]
            old = [line for line in reference if line.startswith(card)]
            if local != old:
                raise ValueError(f"{path}: {card} differs from verified source template")
        lines = reference
    elif (source_count, current_count) != (1, 1):
        raise ValueError(f"{path}: inconsistent source/current cards")
    source = next(line for line in lines if line.startswith("A0:"))
    fields = [field.strip() for field in source.split("**", 1)[0].split(":")]
    if len(fields) < 14 or fields[3:5] not in (["1", "1"], ["17", "37"]) or fields[5:7] != ["1", "1"]:
        raise ValueError(f"{path}: expected one fixed-polarization plane wave")
    mesh_ref = next(line for line in lines if line.startswith("IN "))
    if f'"{variant_id}.cfm"' not in mesh_ref and f'"{variant_dir.parent.name}.cfm"' not in mesh_ref:
        raise ValueError(f"{path}: unexpected CFM reference")
    # The smallbatch generator inserts method-specific FM/PO cards. Remove the
    # template's FM and far-field request so no duplicate method card survives.
    return [line for line in lines if not line.startswith(("FM:", "PO:", "OF:", "FF:"))]


def expected_pre(template: list[str], name: str, labels: list[str], theta: int,
                 phi: int, method: str) -> str:
    content = fixed.make_pre(template, f"{name}.cfm", labels, theta, phi, method)
    lines = content.splitlines()
    for card in ("IN ", "FR:", "A0:", "OS:", "EN"):
        if sum(line.startswith(card) if card != "EN" else line.strip() == "EN"
               for line in lines) != 1:
            raise ValueError(f"{name}: generated {method} PRE has invalid {card} count")
    source = next(line for line in lines if line.startswith("A0:"))
    fields = [field.strip() for field in source.split("**", 1)[0].split(":")]
    if fields[3:5] != ["1", "1"] or fields[8:10] != [str(theta), str(phi)]:
        raise ValueError(f"{name}: generated {method} PRE has wrong angle")
    if f'"../{name}.cfm"' not in content:
        raise ValueError(f"{name}: generated {method} PRE references wrong mesh")
    if sum(line.startswith("FM:") for line in lines) != int(method == "mom"):
        raise ValueError(f"{name}: generated {method} PRE has wrong FM card")
    if sum(line.startswith("PO:") for line in lines) != (len(labels) if method == "po" else 0):
        raise ValueError(f"{name}: generated {method} PRE has wrong PO card count")
    return content


def dataset_path(variant_dir: Path) -> Path:
    return variant_dir / f"dataset{variant_dir.name.removeprefix('case')}.pt"


def dataset_valid(variant_dir: Path, path: Path, mesh_hash: str) -> bool:
    if not path.is_file():
        return False
    try:
        data = torch.load(path, map_location="cpu", weights_only=False)
        if data.get("variant_id") != variant_dir.name or data.get("mesh_sha256") != mesh_hash:
            return False
        if data.get("angle_groups") != ANGLE_GROUPS or data.get("num_angles") != 93:
            return False
        samples = data["samples"]
        if len(samples) != 93 or data.get("frequency_hz") != 1_000_000_000:
            return False
        if {(s["theta"], s["phi"]) for s in samples} != {(t, p) for t, p, _ in ANGLES}:
            return False
        n = data["num_triangles"]
        return all(s["X"].shape == (n, 13) and s["Y"].shape == (n, 6)
                   and torch.isfinite(s["X"]).all().item()
                   and torch.isfinite(s["Y"]).all().item() for s in samples)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, EOFError):
        return False


def build_dataset(variant_dir: Path, mesh_hash: str, parameters: dict) -> Path:
    started = time.monotonic()
    print(f"{variant_dir.name}: building geometry clusters", flush=True)
    geom = builder.build_geometry(variant_dir, 15, 15)
    print(f"{variant_dir.name}: geometry ready in {time.monotonic() - started:.1f}s; reading 93 current pairs", flush=True)
    samples = []
    for theta, phi, group in ANGLES:
        angle_dir = variant_dir / f"theta{theta:03d}_phi{phi:03d}"
        count = len(geom[0])
        for method in METHODS:
            pre_hash = pre_sha256(angle_dir / f"{method}.pre")
            if not fixed.complete(angle_dir, method, count, pre_hash):
                raise ValueError(f"Incomplete or invalid {method} result: {angle_dir}")
        sample = builder.make_sample(variant_dir, theta, phi, geom)
        sample["angle_group"] = group
        samples.append(sample)
        if len(samples) % 19 == 0 or len(samples) == 93:
            print(f"{variant_dir.name}: dataset samples {len(samples)}/93", flush=True)
    data = {
        "samples": samples, "variant_id": variant_dir.name,
        "case_id": variant_dir.parent.name, "parameters": parameters,
        "mesh_sha256": mesh_hash, "num_triangles": len(geom[0]),
        "num_angles": 93, "angle_groups": ANGLE_GROUPS,
        "frequency_hz": 1_000_000_000,
        "normalization": {"method": "eta0", "eta0": builder.ETA0},
        "cluster_config": {"triangles_per_g1": 15, "g1_per_g2": 15,
                           "method": "connected_kmeans_6d", "alpha": geometry_tools.ALPHA,
                           "geodesic_weight": geometry_tools.GEODESIC_WEIGHT},
    }
    output = dataset_path(variant_dir)
    temporary = output.with_name(output.name + ".tmp")
    print(f"{variant_dir.name}: saving and reloading {output.name}", flush=True)
    torch.save(data, temporary)
    if not dataset_valid(variant_dir, temporary, mesh_hash):
        raise ValueError(f"Dataset reload/coverage check failed: {temporary}")
    temporary.replace(output)
    print(f"{variant_dir.name}: dataset verified in {time.monotonic() - started:.1f}s", flush=True)
    return output


def cleanup(variant_dir: Path, output: Path, mesh_hash: str) -> None:
    if not dataset_valid(variant_dir, output, mesh_hash):
        raise ValueError(f"Dataset not verified; cleanup refused: {output}")
    root = variant_dir.resolve()
    targets = []
    for theta, phi, _ in ANGLES:
        angle_dir = variant_dir / f"theta{theta:03d}_phi{phi:03d}"
        if angle_dir.resolve().parent != root:
            raise ValueError(f"Unsafe angle directory: {angle_dir}")
        for path in angle_dir.iterdir():
            if path.is_file() and path.name in REMOVE_NAMES and path.resolve().parent == angle_dir.resolve():
                targets.append(path)
    manifest = {
        "variant_id": variant_dir.name, "dataset": output.name,
        "dataset_sha256": sha256(output), "mesh_sha256": mesh_hash,
        "angles": [{"theta": t, "phi": p, "group": g} for t, p, g in ANGLES],
        "deleted_files": [{"path": str(p.relative_to(variant_dir)), "bytes": p.stat().st_size}
                          for p in targets],
    }
    fixed.write_json(variant_dir / "archive_manifest.json", manifest)
    for path in targets:
        path.unlink()
    fixed.write_json(variant_dir / "ARCHIVED.json", {
        "variant_id": variant_dir.name, "dataset": output.name,
        "dataset_sha256": manifest["dataset_sha256"],
        "mesh_sha256": mesh_hash, "deleted_file_count": len(targets),
        "finished_at": fixed.stamp(),
    })


def variant_ids(args: argparse.Namespace) -> list[str]:
    selected = args.variants or ([args.variant] if args.variant else None)
    if selected:
        if any(not re.fullmatch(r"case[1-5]_(0[1-9]|1[0-9]|20)", name) for name in selected):
            raise ValueError("Variant names must be case1_01 through case5_20")
        return selected
    cases = args.cases or ([args.case] if args.case else [f"case{i}" for i in range(1, 6)])
    return [f"{case}_{i:02d}" for case in cases for i in range(1, 21)]


def check_inputs(variant_id: str, plan: dict) -> int:
    variant_dir = ROOT / variant_id.split("_")[0] / variant_id
    metadata = json.loads((variant_dir / "variant_parameters.json").read_text(encoding="utf-8-sig"))
    if (metadata.get("variant_id") != variant_id or
            metadata.get("parameters") != plan[variant_id] or
            metadata.get("frequency_hz") != 1_000_000_000):
        raise ValueError(f"Metadata/parameter plan mismatch: {variant_id}")
    cfm = variant_dir / f"{variant_id}.cfm"
    nas = variant_dir / f"{variant_id}.nas"
    grids, triangles = geometry_tools.parse_nas(nas)
    geometry_tools.verify_cfm_mesh(cfm, triangles, grids)
    count, labels = fixed.mesh_info(cfm)
    if count != len(triangles):
        raise ValueError(f"Mesh triangle count mismatch: {variant_id}")
    template = read_template(variant_dir)
    for theta, phi, _ in ANGLES:
        for method in METHODS:
            expected_pre(template, variant_id, labels, theta, phi, method)
    print(f"{variant_id}: {count} triangles; 93 MoM/PO PRE pairs valid", flush=True)
    return count


def run_variant(variant_id: str, args: argparse.Namespace, runfeko: Path | None) -> bool:
    variant_dir = ROOT / variant_id.split("_")[0] / variant_id
    if not variant_dir.is_dir():
        raise FileNotFoundError(variant_dir)
    metadata = json.loads((variant_dir / "variant_parameters.json").read_text(encoding="utf-8-sig"))
    if metadata.get("variant_id") != variant_id or metadata.get("frequency_hz") != 1_000_000_000:
        raise ValueError(f"Variant metadata mismatch: {variant_dir}")
    if metadata.get("parameters") != read_plan(ROOT / "variants.md")[variant_id]:
        raise ValueError(f"Variant parameters differ from variants.md: {variant_id}")
    cfm = variant_dir / f"{variant_id}.cfm"
    nas = variant_dir / f"{variant_id}.nas"
    mesh_hash = sha256(cfm)
    grids, triangles = geometry_tools.parse_nas(nas)
    geometry_tools.verify_cfm_mesh(cfm, triangles, grids)
    count, labels = fixed.mesh_info(cfm)
    if count != len(triangles):
        raise ValueError(f"CFM/NAS triangle count differs: {variant_id}")
    output = dataset_path(variant_dir)
    archived = variant_dir / "ARCHIVED.json"
    if archived.exists():
        record = json.loads(archived.read_text(encoding="utf-8"))
        if not dataset_valid(variant_dir, output, mesh_hash) or record.get("dataset_sha256") != sha256(output):
            raise ValueError(f"Archived dataset invalid: {variant_id}")
        print(f"{variant_id}: archived dataset verified; skipped", flush=True)
        return True
    if dataset_valid(variant_dir, output, mesh_hash):
        if not args.prepare_only:
            cleanup(variant_dir, output, mesh_hash)
        print(f"{variant_id}: dataset verified", flush=True)
        return True
    template = read_template(variant_dir)
    scratch = variant_dir / "feko_tmp"
    if not args.prepare_only:
        scratch.mkdir(exist_ok=True)
    status = {"variant_id": variant_id, "total_angles": 93, "completed_angles": 0,
              "active": None, "stage": "preparing", "updated_at": fixed.stamp()}
    fixed.write_json(variant_dir / "status.json", status)
    for index, (theta, phi, group) in enumerate(ANGLES, 1):
        angle_dir = variant_dir / f"theta{theta:03d}_phi{phi:03d}"
        angle_dir.mkdir(exist_ok=True)
        hashes = {}
        for method in METHODS:
            content = expected_pre(template, variant_id, labels, theta, phi, method)
            pre = angle_dir / f"{method}.pre"
            if not pre.is_file() or pre.read_text(encoding="utf-8") != content:
                pre.write_text(content, encoding="utf-8")
            hashes[method] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if args.prepare_only:
            if args.limit_angles and index >= args.limit_angles:
                break
            continue
        status.update(active=angle_dir.name, stage="solving", angle_group=group,
                      updated_at=fixed.stamp())
        fixed.write_json(variant_dir / "status.json", status)
        for method in METHODS:
            if fixed.complete(angle_dir, method, count, hashes[method]):
                continue
            if (ROOT / "STOP_REQUESTED").exists():
                status.update(stage="stopped", updated_at=fixed.stamp())
                fixed.write_json(variant_dir / "status.json", status)
                return False
            status.update(method=method, updated_at=fixed.stamp())
            fixed.write_json(variant_dir / "status.json", status)
            fixed.solve(angle_dir, method, runfeko, args.np, count, hashes[method], scratch)
        status.update(completed_angles=index, method=None, updated_at=fixed.stamp())
        fixed.write_json(variant_dir / "status.json", status)
    if args.prepare_only:
        print(f"{variant_id}: prepared {min(args.limit_angles or 93, 93)} angle PRE pairs", flush=True)
        return True
    if (ROOT / "STOP_REQUESTED").exists():
        status.update(stage="stopped", updated_at=fixed.stamp())
        fixed.write_json(variant_dir / "status.json", status)
        return False
    status.update(stage="building_dataset", active=None, updated_at=fixed.stamp())
    fixed.write_json(variant_dir / "status.json", status)
    output = build_dataset(variant_dir, mesh_hash, metadata["parameters"])
    status.update(stage="cleaning", updated_at=fixed.stamp())
    fixed.write_json(variant_dir / "status.json", status)
    cleanup(variant_dir, output, mesh_hash)
    status.update(stage="archived", updated_at=fixed.stamp())
    fixed.write_json(variant_dir / "status.json", status)
    print(f"{variant_id}: archived {output.name}", flush=True)
    return True


def run_queue(identifiers: list[str], args: argparse.Namespace, runfeko: Path | None) -> list[str]:
    failed = []
    for variant_id in identifiers:
        if (ROOT / "STOP_REQUESTED").exists() and not args.prepare_only:
            print("Safe stop requested", flush=True)
            break
        try:
            if not run_variant(variant_id, args, runfeko):
                break
        except Exception as error:
            failed.append(variant_id)
            variant_dir = ROOT / variant_id.split("_")[0] / variant_id
            status_path = variant_dir / "status.json"
            try:
                progress = json.loads(status_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                progress = {}
            fixed.write_json(variant_dir / "failure.json", {
                "variant_id": variant_id, "time": fixed.stamp(), "error": str(error),
                "stage": progress.get("stage"), "angle": progress.get("active"),
                "method": progress.get("method"), "status": str(status_path),
            })
            print(f"{variant_id}: FAILED: {error}", flush=True)
    return failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", help="One variant, for example case4_19")
    parser.add_argument("--variants", nargs="+", help="Selected variants from different cases")
    parser.add_argument("--case", choices=[f"case{i}" for i in range(1, 6)])
    parser.add_argument("--cases", nargs="+", choices=[f"case{i}" for i in range(1, 6)],
                        help="Selected cases, for example case4 case5")
    parser.add_argument("--np", type=int, default=12, help="MPI ranks for one MoM solve")
    parser.add_argument("--jobs", type=int, default=1, help="Independent case workers (1 or 2)")
    parser.add_argument("--builder-threads", type=int, default=4,
                        help="CPU threads for Python clustering and tensor checks; FEKO MPI is unchanged")
    parser.add_argument("--feko-bin", type=Path)
    parser.add_argument("--prepare-only", action="store_true", help="Generate PRE files, no FEKO solve")
    parser.add_argument("--check-inputs", action="store_true", help="Read-only validation of all PREs and meshes")
    parser.add_argument("--limit-angles", type=int, help="Only with --prepare-only")
    args = parser.parse_args()
    if sum(bool(choice) for choice in (args.variant, args.variants, args.case, args.cases)) > 1:
        parser.error("Select only one of --variant, --variants, --case, or --cases")
    if (args.np < 1 or args.jobs not in (1, 2) or args.builder_threads < 1 or
            (args.limit_angles and (not args.prepare_only or args.limit_angles < 1))):
        parser.error("Invalid --np, --jobs, --builder-threads or --limit-angles")
    if args.jobs == 2 and (args.variant or args.case or
                           (args.cases and len(set(args.cases)) < 2) or
                           (args.variants and len({name.split("_")[0] for name in args.variants}) < 2)):
        parser.error("--jobs 2 requires at least two cases")
    if args.cases and len(set(args.cases)) != len(args.cases):
        parser.error("--cases must not contain duplicates")
    if args.variants and len(set(args.variants)) != len(args.variants):
        parser.error("--variants must not contain duplicates")
    threadpool_limits(limits=args.builder_threads)
    torch.set_num_threads(args.builder_threads)
    if args.check_inputs and args.prepare_only:
        parser.error("Select --check-inputs or --prepare-only")
    if args.check_inputs:
        plan = read_plan(ROOT / "variants.md")
        failed = []
        for variant_id in variant_ids(args):
            try:
                check_inputs(variant_id, plan)
            except Exception as error:
                failed.append(variant_id)
                print(f"{variant_id}: INPUT CHECK FAILED: {error}", flush=True)
        print(f"Input check: {len(variant_ids(args)) - len(failed)}/{len(variant_ids(args))} passed", flush=True)
        return 1 if failed else 0
    if (ROOT / "STOP_REQUESTED").exists() and not args.prepare_only:
        parser.error("Remove STOP_REQUESTED before resuming")
    runfeko = None
    if not args.prepare_only:
        feko_bin = args.feko_bin or next((p for p in fixed.FEKO_BIN_CANDIDATES
                                         if (p / "runfeko.exe").is_file()), None)
        if not feko_bin or not (feko_bin / "runfeko.exe").is_file():
            parser.error("runfeko.exe not found; pass --feko-bin")
        runfeko = (feko_bin / "runfeko.exe").resolve()
    lock = ROOT / "RUNNING.lock"
    if not args.prepare_only:
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            parser.error(f"Another run may be active; inspect {lock} and remove only if stale")
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"pid": os.getpid(), "started_at": fixed.stamp()}) + "\n")
    failed = []
    try:
        identifiers = variant_ids(args)
        if args.jobs == 1:
            failed = run_queue(identifiers, args, runfeko)
        else:
            queues = [[variant_id for variant_id in identifiers
                       if variant_id.startswith(f"case{case_number}_")]
                      for case_number in range(1, 6)]
            queues = [queue for queue in queues if queue]
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = {pool.submit(run_queue, queue, args, runfeko): queue[0].split("_")[0]
                           for queue in queues}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        failed.extend(future.result())
                    except Exception as error:
                        case_id = futures[future]
                        failed.append(case_id)
                        print(f"{case_id}: WORKER FAILED: {error}", flush=True)
    finally:
        if not args.prepare_only:
            with contextlib.suppress(FileNotFoundError):
                lock.unlink()
    print(f"Finished: failures={len(failed)}; stopped={(ROOT / 'STOP_REQUESTED').exists()}", flush=True)
    return 1 if failed or (ROOT / "STOP_REQUESTED").exists() else 0


if __name__ == "__main__":
    raise SystemExit(main())
