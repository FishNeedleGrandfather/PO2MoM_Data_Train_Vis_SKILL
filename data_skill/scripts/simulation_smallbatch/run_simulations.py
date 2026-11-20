"""Run the fixed-geometry 1 GHz MoM/PO angle sweep on a Windows workstation."""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import math
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CASES = ("case1", "case2", "case3", "case4", "case5", "case_single")
THETAS = tuple(range(10, 91, 5))
PHIS = tuple(range(0, 181, 5))
FEKO_BIN_CANDIDATES = (
    Path(r"C:\Program Files\Altair\2025\feko\bin"),
    Path(r"E:\Altair\feko\2025\feko\bin"),
)


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    content = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    for attempt in range(3):
        try:
            temporary.write_text(content, encoding="utf-8")
            temporary.replace(path)
            return
        except OSError:
            if attempt < 2:
                time.sleep(0.2 * (attempt + 1))
    # A synchronizer or antivirus can briefly block the Windows rename.
    path.write_text(content, encoding="utf-8")
    try:
        temporary.unlink(missing_ok=True)
    except OSError:
        pass


def mesh_info(cfm: Path) -> tuple[int, list[str]]:
    count = 0
    labels: list[str] = []
    with gzip.open(cfm, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith("DR:"):
                count += 1
            elif line.startswith("LA:"):
                label = line[3:].strip()
                if label and label not in labels:
                    labels.append(label)
    if not count or not labels:
        raise ValueError(f"CFM is missing triangles or surface labels: {cfm}")
    return count, labels


def base_pre(case_dir: Path) -> list[str]:
    path = case_dir / f"{case_dir.name}.pre"
    lines = path.read_text(encoding="utf-8").splitlines()
    required = ("IN", "FP", "A0", "FR", "OS", "EN")
    for card in required:
        if sum(line.strip() == "EN" if card == "EN" else
               line.startswith(card + ":") or line.startswith(card + " ")
               for line in lines) != 1:
            raise ValueError(f"Expected exactly one {card} card in {path}")
    angle = next(line for line in lines if line.startswith("A0:"))
    fields = [field.strip() for field in angle.split("**", 1)[0].split(":")]
    if (fields[3], fields[4], fields[8], fields[9], fields[11], fields[12]) != (
        "17", "37", "10", "0", "5", "5"
    ):
        raise ValueError(f"Unexpected angle sweep in {path}: {angle}")
    frequency = next(line for line in lines if line.startswith("FR:"))
    if frequency.split(":")[-1].strip() != "1000000000":
        raise ValueError(f"Expected 1 GHz in {path}: {frequency}")
    return lines


def make_pre(lines: list[str], cfm_name: str, labels: list[str],
             theta: int, phi: int, method: str) -> str:
    result = [f"** {method.upper()} theta={theta} phi={phi} f=1 GHz"]
    for line in lines:
        if line.startswith("** CADFEKO Checksum:"):
            continue
        if line.startswith("IN "):
            result.append(f'IN   8 1055  "../{cfm_name}"')
            if method == "mom":
                result.append("FM: 0 : 0 :  : 0")
            else:
                result.extend(
                    f"PO: {label} : 0 : 0 : 2 : 0 : 0 :  :  : 0 :  : 0 : 0 : 0"
                    for label in labels
                )
        elif line.startswith("A0:"):
            fields = [field.strip() for field in line.split("**", 1)[0].split(":")]
            fields[3], fields[4] = "1", "1"
            fields[8], fields[9] = str(theta), str(phi)
            fields[11], fields[12] = "0", "0"
            result.append("A0: " + " : ".join(fields[1:]))
        elif line.startswith("OS:"):
            result.append(f"OS: 1 :  : 1   ** {method}_Currents")
        else:
            result.append(line)
    return "\n".join(result) + "\n"


def current_rows(path: Path, n: int) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    seen = bytearray(n + 1)
    found = 0
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            parts = line.split()
            if not parts or not parts[0].isdigit():
                continue
            if len(parts) < 10:
                return False
            index = int(parts[0])
            if not 1 <= index <= n or seen[index]:
                return False
            try:
                if not all(math.isfinite(float(value)) for value in parts[4:10]):
                    return False
            except ValueError:
                return False
            seen[index] = 1
            found += 1
    return found == n


def mom_converged(path: Path) -> bool:
    if not path.is_file():
        return False
    output = path.read_text(encoding="utf-8", errors="replace")
    return "Stopping after" in output and "WARNING   830" not in output


def complete(angle_dir: Path, method: str, n: int, pre_hash: str) -> bool:
    marker = angle_dir / f"{method}.done.json"
    if not marker.is_file():
        return False
    try:
        record = json.loads(marker.read_text(encoding="utf-8"))
        if record.get("pre_sha256") != pre_hash or record.get("triangles") != n:
            return False
    except (ValueError, OSError):
        return False
    os_path = angle_dir / f"{method}_{method}_Currents.os"
    return current_rows(os_path, n) and (method != "mom" or mom_converged(angle_dir / "mom.out"))


def solve(angle_dir: Path, method: str, runfeko: Path, ranks: int, n: int,
          pre_hash: str, scratch: Path) -> None:
    pre = angle_dir / f"{method}.pre"
    command = [str(runfeko), pre.name]
    if method == "mom" and ranks > 1:
        command.extend(("-np", str(ranks)))
    environment = os.environ.copy()
    environment.update({"FEKO_TMPDIR": str(scratch), "TEMP": str(scratch), "TMP": str(scratch)})
    with (angle_dir / f"{method}.log").open("w", encoding="utf-8", errors="replace") as log:
        result = subprocess.run(command, cwd=angle_dir, env=environment,
                                stdout=log, stderr=subprocess.STDOUT, check=False)
    if result.returncode:
        raise RuntimeError(f"{method} FEKO exited {result.returncode}; see {angle_dir / (method + '.log')}")
    os_path = angle_dir / f"{method}_{method}_Currents.os"
    if not current_rows(os_path, n):
        raise RuntimeError(f"Incomplete current file: {os_path}")
    if method == "mom" and not mom_converged(angle_dir / "mom.out"):
        raise RuntimeError(f"MoM did not report convergence: {angle_dir / 'mom.out'}")
    write_json(angle_dir / f"{method}.done.json", {
        "method": method, "triangles": n, "pre_sha256": pre_hash, "finished_at": stamp()
    })


def run_case(case: str, thetas: list[int], phis: list[int], args: argparse.Namespace,
             runfeko: Path | None) -> int:
    case_dir = ROOT / case
    cfm = case_dir / f"{case}.cfm"
    n, labels = mesh_info(cfm)
    template = base_pre(case_dir)
    scratch = case_dir / "feko_tmp"
    if not args.prepare_only:
        scratch.mkdir(exist_ok=True)
    total = len(thetas) * len(phis)
    progress = {"case": case, "total_angles": total, "finished_angles": 0,
                "failed_angles": 0, "skipped_angles": 0, "active": None,
                "triangles": n, "updated_at": stamp()}
    status_warning = False

    def status() -> None:
        nonlocal status_warning
        progress["updated_at"] = stamp()
        try:
            write_json(case_dir / "status.json", progress)
            status_warning = False
        except OSError as error:
            if not status_warning:
                print(f"{case}: WARNING: cannot update status.json: {error}", flush=True)
            status_warning = True

    if not args.prepare_only:
        status()
    for theta in thetas:
        for phi in phis:
            if not args.prepare_only and (ROOT / "STOP_REQUESTED").exists():
                progress["active"] = "stopped"
                status()
                print(f"{case}: safe stop after current solve", flush=True)
                return progress["failed_angles"]
            angle_dir = case_dir / f"theta{theta:03d}_phi{phi:03d}"
            angle_dir.mkdir(exist_ok=True)
            progress["active"] = angle_dir.name
            hashes = {}
            for method in ("mom", "po"):
                content = make_pre(template, cfm.name, labels, theta, phi, method)
                pre = angle_dir / f"{method}.pre"
                if not pre.is_file() or pre.read_text(encoding="utf-8") != content:
                    pre.write_text(content, encoding="utf-8")
                hashes[method] = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if args.prepare_only:
                continue
            status()
            try:
                already_done = all(complete(angle_dir, method, n, hashes[method])
                                   for method in ("mom", "po"))
                if already_done:
                    progress["skipped_angles"] += 1
                else:
                    for method in ("mom", "po"):
                        if complete(angle_dir, method, n, hashes[method]):
                            continue
                        if (ROOT / "STOP_REQUESTED").exists():
                            progress["active"] = "stopped"
                            status()
                            print(f"{case}: safe stop before {method} solve", flush=True)
                            return progress["failed_angles"]
                        print(f"{case} theta={theta:03d} phi={phi:03d} {method}: solving", flush=True)
                        solve(angle_dir, method, runfeko, args.np, n, hashes[method], scratch)
                    progress["finished_angles"] += 1
                    print(f"{case}: {progress['finished_angles'] + progress['skipped_angles']}/{total} angles complete", flush=True)
            except Exception as error:
                progress["failed_angles"] += 1
                try:
                    write_json(angle_dir / "failure.json", {"time": stamp(), "error": str(error)})
                except OSError as write_error:
                    print(f"{case}: WARNING: cannot record failure.json: {write_error}", flush=True)
                print(f"{case} theta={theta:03d} phi={phi:03d}: FAILED: {error}", flush=True)
            progress["active"] = None
            status()
    if args.prepare_only:
        print(f"{case}: prepared {total} angles ({2 * total} PRE files); {n} triangles", flush=True)
    else:
        print(f"{case}: done={progress['finished_angles'] + progress['skipped_angles']}/{total}, "
              f"failed={progress['failed_angles']}", flush=True)
    return progress["failed_angles"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--theta", nargs="+", type=int, help="Subset of theta angles; default 10..90 step 5")
    parser.add_argument("--phi", nargs="+", type=int, help="Subset of phi angles; default 0..180 step 5")
    parser.add_argument("--np", type=int, default=12, help="MoM MPI ranks per case; PO is serial")
    parser.add_argument("--jobs", type=int, default=1, help="Cases solved concurrently (default 1)")
    parser.add_argument("--feko-bin", type=Path, help="FEKO bin folder containing runfeko.exe")
    parser.add_argument("--prepare-only", action="store_true", help="Write angle PREs without running FEKO")
    args = parser.parse_args()
    thetas = list(dict.fromkeys(args.theta if args.theta is not None else THETAS))
    phis = list(dict.fromkeys(args.phi if args.phi is not None else PHIS))
    if not thetas or any(theta not in THETAS for theta in thetas):
        parser.error("Theta must be selected from 10, 15, ..., 90")
    if not phis or any(phi not in PHIS for phi in phis):
        parser.error("Phi must be selected from 0, 5, ..., 180")
    if args.np < 1 or args.jobs < 1:
        parser.error("--np and --jobs must be positive")
    if (ROOT / "STOP_REQUESTED").exists() and not args.prepare_only:
        parser.error("Remove STOP_REQUESTED before resuming")
    runfeko = None
    if not args.prepare_only:
        feko_bin = args.feko_bin or next(
            (path for path in FEKO_BIN_CANDIDATES if (path / "runfeko.exe").is_file()), None
        )
        if feko_bin is None or not (feko_bin / "runfeko.exe").is_file():
            parser.error("runfeko.exe not found; pass --feko-bin with the FEKO bin directory")
        runfeko = (feko_bin / "runfeko.exe").resolve()
        print(f"FEKO: {runfeko}; jobs={args.jobs}, MoM -np {args.np}", flush=True)
    print("Simulation only: no dataset construction", flush=True)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.jobs, len(args.cases))) as pool:
        futures = {pool.submit(run_case, case, thetas, phis, args, runfeko): case
                   for case in args.cases}
        errors = 0
        for future in concurrent.futures.as_completed(futures):
            case = futures[future]
            try:
                errors += future.result()
            except Exception as error:
                errors += 1
                print(f"{case}: SETUP FAILED: {error}", flush=True)
    stopped = (ROOT / "STOP_REQUESTED").exists()
    outcome = "Stopped safely" if stopped else "Finished"
    print(f"{outcome} in {(time.monotonic() - started) / 60:.1f} min; failures={errors}", flush=True)
    return 1 if errors or stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
