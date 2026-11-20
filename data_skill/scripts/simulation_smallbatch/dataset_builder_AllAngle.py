"""Build eta-normalized datasets from the completed six-case angle sweep.

Run from this directory on the workstation. The two copied geometry helpers
make this folder independent of the rest of PO2MoM_TF.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import torch

import datasetbuilder_1ghz as old
from cluster_6d import fit_connected_clusters
from run_simulations import CASES, PHIS, THETAS, mom_converged


ROOT = Path(__file__).resolve().parent
ETA0 = 376.730313668


def build_geometry(case_dir: Path, triangles_per_g1: int, g1_per_g2: int,
                   mesh_stem: str | None = None):
    cfm = case_dir / f"{mesh_stem or case_dir.name}.cfm"
    nas = cfm.with_suffix(".nas")
    grids, triangles = old.parse_nas(nas)
    old.verify_cfm_mesh(cfm, triangles, grids)
    centers, normals, areas = old.compute_geometry(triangles, grids)
    e0, edge_to_triangles = old.geometry_graph(triangles)
    count = len(triangles)
    n_g1 = math.ceil(count / triangles_per_g1)
    n_g2 = math.ceil(n_g1 / g1_per_g2)

    c01 = fit_connected_clusters(
        np.column_stack((centers, old.ALPHA * normals)),
        n_g1, 5000, e0, old.GEODESIC_WEIGHT,
    )
    c1_centers, c1_normals = old.cluster_centers(c01, centers, normals, n_g1)
    e1 = old.boundary_edges(edge_to_triangles, c01)
    c12 = fit_connected_clusters(
        np.column_stack((c1_centers, old.ALPHA * c1_normals)),
        n_g2, 200, e1, old.GEODESIC_WEIGHT,
    )
    c2_centers, c2_normals = old.cluster_centers(c12[c01], centers, normals, n_g2)
    e2 = old.boundary_edges(edge_to_triangles, c12[c01])
    coupling1 = old.coupling_edges(c1_centers, c1_normals, 32, old.G1_COUPLING_RADIUS_M)
    coupling2 = old.coupling_edges(c2_centers, c2_normals, 8, old.G2_COUPLING_RADIUS_M)
    cluster = {"c01": torch.from_numpy(c01), "c12": torch.from_numpy(c12)}
    geo_edges = {"e0": torch.from_numpy(e0), "e1": torch.from_numpy(e1),
                 "e2": torch.from_numpy(e2)}
    cpl_edges = {"e1": torch.from_numpy(coupling1),
                 "e2": torch.from_numpy(coupling2)}
    print(f"{case_dir.name}: triangles={count}, G1={n_g1}, G2={n_g2}", flush=True)
    return centers, normals, areas, cluster, geo_edges, cpl_edges, n_g1, n_g2


def check_result(angle_dir: Path, method: str, count: int) -> None:
    marker = angle_dir / f"{method}.done.json"
    pre = angle_dir / f"{method}.pre"
    info = json.loads(marker.read_text(encoding="utf-8"))
    pre_hash = hashlib.sha256(pre.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    if (info.get("method") != method or info.get("triangles") != count
            or info.get("pre_sha256") != pre_hash):
        raise ValueError(f"Completion marker does not match PRE or mesh: {marker}")
    if method == "mom" and not mom_converged(angle_dir / "mom.out"):
        raise ValueError(f"MoM convergence not confirmed: {angle_dir / 'mom.out'}")


def make_sample(case_dir: Path, theta: int, phi: int, geometry: tuple) -> dict:
    centers, normals, areas, cluster, geo_edges, cpl_edges, _, _ = geometry
    count = len(centers)
    angle_dir = case_dir / f"theta{theta:03d}_phi{phi:03d}"
    check_result(angle_dir, "mom", count)
    check_result(angle_dir, "po", count)
    mom = old.read_current(angle_dir / "mom_mom_Currents.os", count)
    po = old.read_current(angle_dir / "po_po_Currents.os", count)
    x = np.column_stack((centers, normals, areas[:, None], ETA0 * po)).astype(np.float32)
    y = (ETA0 * (mom - po)).astype(np.float32)
    theta_rad, phi_rad = np.deg2rad((theta, phi))
    wave = np.asarray((
        -np.sin(theta_rad) * np.cos(phi_rad),
        -np.sin(theta_rad) * np.sin(phi_rad),
        -np.cos(theta_rad),
    ), dtype=np.float32)
    return {
        "X": torch.from_numpy(x), "Y": torch.from_numpy(y), "scale": 1.0 / ETA0,
        "K0": 2 * np.pi * old.FREQUENCY_HZ / old.C0,
        "k_hat": torch.from_numpy(wave), "theta": theta, "phi": phi,
        "cluster": cluster, "geo_edges": geo_edges, "cpl_edges": cpl_edges,
        "num_triangles": count,
    }


def save_dataset(path: Path, dataset) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    torch.save(dataset, temporary)
    temporary.replace(path)
    print(f"Saved {path}", flush=True)


def build_case(case: str, thetas: list[int], phis: list[int], args) -> Path:
    case_dir = ROOT / case
    geometry = build_geometry(case_dir, args.triangles_per_g1, args.g1_per_g2)
    samples = []
    omitted = []
    for theta in thetas:
        for phi in phis:
            try:
                samples.append(make_sample(case_dir, theta, phi, geometry))
            except (OSError, ValueError, KeyError) as error:
                if not args.skip_incomplete:
                    raise RuntimeError(f"{case} theta={theta} phi={phi}: {error}") from error
                omitted.append((theta, phi, str(error)))
        print(f"{case}: theta={theta}, samples={len(samples)}", flush=True)
    if not samples:
        raise ValueError(f"No complete angles for {case}")
    _, _, _, _, _, _, n_g1, n_g2 = geometry
    dataset = {
        "samples": samples,
        "num_angles": len(samples),
        "theta_angles": thetas,
        "phi_angles": phis,
        "frequency_hz": old.FREQUENCY_HZ,
        "normalization": {"method": "eta0", "eta0": ETA0},
        "cluster_config": {
            "n_g1": n_g1, "n_g2": n_g2,
            "triangles_per_g1": args.triangles_per_g1,
            "g1_per_g2": args.g1_per_g2,
            "method": "connected_kmeans_6d", "alpha": old.ALPHA,
            "geodesic_weight": old.GEODESIC_WEIGHT,
            "coupling_min_facing_projection": old.MIN_FACING_PROJECTION,
            "coupling_max_facing_angle_deg": old.MAX_FACING_ANGLE_DEG,
            "wavelength_m": old.WAVELENGTH_M,
            "coupling_radius_lambda": {
                "g1": old.G1_COUPLING_RADIUS_LAMBDA,
                "g2": old.G2_COUPLING_RADIUS_LAMBDA,
            },
        },
    }
    output = args.output_dir / f"dataset_{case}_allangle_eta.pt"
    save_dataset(output, dataset)
    print(f"{case}: included={len(samples)}, omitted={len(omitted)}", flush=True)
    if omitted:
        report = args.output_dir / f"dataset_{case}_omitted.json"
        report.write_text(json.dumps(omitted, indent=2), encoding="utf-8")
        print(f"Omitted-angle report: {report}", flush=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--theta", nargs="+", type=int, help="Default: 10..90 step 5")
    parser.add_argument("--phi", nargs="+", type=int, help="Default: 0..180 step 5")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "datasets")
    parser.add_argument("--triangles-per-g1", type=int, default=15)
    parser.add_argument("--g1-per-g2", type=int, default=15)
    parser.add_argument("--skip-incomplete", action="store_true")
    args = parser.parse_args()
    if args.triangles_per_g1 < 1 or args.g1_per_g2 < 1:
        parser.error("Cluster group sizes must be positive")
    thetas = args.theta if args.theta is not None else list(THETAS)
    phis = args.phi if args.phi is not None else list(PHIS)
    if not thetas or not phis or set(thetas) - set(THETAS) or set(phis) - set(PHIS):
        parser.error("Angles must be nonempty subsets of the simulated theta/phi grids")
    args.output_dir = args.output_dir.resolve()

    outputs = {case: build_case(case, thetas, phis, args) for case in args.cases}
    if all(case in outputs for case in CASES[:5]):
        combined = [torch.load(outputs[case], map_location="cpu", weights_only=False)
                    for case in CASES[:5]]
        save_dataset(args.output_dir / "dataset_case1to5_allangle_eta.pt", combined)
        print("case_single remains a separate holdout dataset.", flush=True)


if __name__ == "__main__":
    main()
