"""Build a 1 GHz case dataset with 15 triangles/G1 and 15 G1/G2."""

from __future__ import annotations

import argparse
import gzip
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch
from scipy.sparse import coo_matrix

from cluster_6d import fit_connected_clusters


ROOT = Path(__file__).resolve().parent
SIM_DIR = ROOT / "case1"
FREQUENCY_HZ = 1_000_000_000
C0 = 299_792_458.0
WAVELENGTH_M = C0 / FREQUENCY_HZ
G1_COUPLING_RADIUS_LAMBDA = 5.0 / 3.0
G2_COUPLING_RADIUS_LAMBDA = 10.0 / 3.0
G1_COUPLING_RADIUS_M = G1_COUPLING_RADIUS_LAMBDA * WAVELENGTH_M
G2_COUPLING_RADIUS_M = G2_COUPLING_RADIUS_LAMBDA * WAVELENGTH_M
THETA_DEG = 45
PHI_ANGLES = tuple(range(0, 180, 10))
TRIANGLES_PER_G1 = 15
G1_PER_G2 = 15
ALPHA = 0.5
GEODESIC_WEIGHT = 1.0
COS30 = np.sqrt(3) / 2
MAX_FACING_ANGLE_DEG = 75.0
MIN_FACING_PROJECTION = float(np.cos(np.deg2rad(MAX_FACING_ANGLE_DEG)))


def parse_nas(path: Path):
    # Keep a leading sign, but never absorb a NASTRAN continuation ID such as
    # ``*    458-2.500000000E-02`` into the coordinate token.
    scientific = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)[Ee][-+]?\d+")
    grids = {}
    triangles = []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        lines = iter(stream)
        for line in lines:
            if line.startswith("GRID*"):
                match = re.search(r"GRID\*\s+(\d+)", line)
                xy = scientific.findall(line)
                continuation = next(lines)
                z_values = scientific.findall(continuation)
                if not match or len(xy) < 2 or not z_values:
                    raise ValueError(f"Invalid GRID record in {path}")
                grids[int(match.group(1))] = (
                    float(xy[0]), float(xy[1]), float(z_values[-1])
                )
            elif line.startswith("CTRIA3"):
                fields = line.split()
                triangles.append(tuple(map(int, (fields[1], fields[3], fields[4], fields[5]))))
    if not grids or not triangles:
        raise ValueError(f"Empty NAS mesh: {path}")
    return grids, triangles


def verify_cfm_mesh(path: Path, triangles, grids):
    cfm_centers = []
    current = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.startswith("DR:"):
                if current:
                    raise ValueError("Incomplete CFM triangle")
                fields = line.strip().split(":")
                current = [tuple(float(v) for v in fields[6:9])]
            elif current and line.startswith("  ::::::"):
                fields = line.strip().split(":")
                current.append(tuple(float(v) for v in fields[6:9]))
                if len(current) == 3:
                    cfm_centers.append(np.mean(current, axis=0))
                    current = []
    if len(cfm_centers) != len(triangles):
        raise ValueError(f"CFM/NAS triangle mismatch: {len(cfm_centers)} vs {len(triangles)}")
    nas_centers = np.asarray([
        np.mean([grids[node] for node in tri[1:]], axis=0) for tri in triangles
    ])
    deviation = np.linalg.norm(np.asarray(cfm_centers) - nas_centers, axis=1)
    if not np.all(deviation < 1e-6):
        raise ValueError(
            f"CFM/NAS triangle order differs at {np.count_nonzero(deviation >= 1e-6)} positions"
        )


def compute_geometry(triangles, grids):
    centers = np.empty((len(triangles), 3), dtype=np.float32)
    normals = np.empty_like(centers)
    areas = np.empty(len(triangles), dtype=np.float32)
    for i, (_, a, b, c) in enumerate(triangles):
        vertices = np.asarray((grids[a], grids[b], grids[c]), dtype=np.float64)
        cross = np.cross(vertices[1] - vertices[0], vertices[2] - vertices[0])
        magnitude = np.linalg.norm(cross)
        if magnitude <= 1e-30:
            raise ValueError(f"Degenerate triangle {i + 1}")
        centers[i] = vertices.mean(axis=0)
        normals[i] = cross / magnitude
        areas[i] = magnitude / 2
    return centers, normals, areas


def geometry_graph(triangles):
    edge_to_triangles = defaultdict(list)
    for i, (_, a, b, c) in enumerate(triangles):
        for u, v in ((a, b), (b, c), (c, a)):
            edge_to_triangles[tuple(sorted((u, v)))].append(i)
    row, col = [], []
    for indices in edge_to_triangles.values():
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                row.extend((indices[i], indices[j]))
                col.extend((indices[j], indices[i]))
    adj = coo_matrix((np.ones(len(row)), (row, col)), shape=(len(triangles),) * 2).tocsr()
    coo = adj.tocoo()
    mask = coo.row < coo.col
    e0 = np.stack((coo.row[mask], coo.col[mask])).astype(np.int64)
    return e0, edge_to_triangles


def cluster_centers(labels, centers, normals, count):
    location = np.zeros((count, 3), dtype=np.float64)
    normal = np.zeros_like(location)
    np.add.at(location, labels, centers)
    np.add.at(normal, labels, normals)
    location /= np.bincount(labels, minlength=count)[:, None]
    normal /= np.linalg.norm(normal, axis=1, keepdims=True) + 1e-30
    return location, normal


def boundary_edges(edge_to_triangles, triangle_labels):
    pairs = set()
    for indices in edge_to_triangles.values():
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                a, b = triangle_labels[indices[i]], triangle_labels[indices[j]]
                if a != b:
                    pairs.add((min(a, b), max(a, b)))
    if not pairs:
        return np.zeros((2, 0), dtype=np.int64)
    return np.asarray(sorted(pairs), dtype=np.int64).T


def coupling_edges(centers, normals, top_k, radius):
    # Same directional normal-facing rule and score as the original builder.
    lower = centers.min(axis=0) - 0.01
    cells = ((centers - lower) / radius).astype(int)
    buckets = defaultdict(list)
    for i, cell in enumerate(cells):
        buckets[tuple(cell)].append(i)
    source, target = [], []
    for i, cell in enumerate(cells):
        candidates = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for j in buckets.get(tuple(cell + (dx, dy, dz)), []):
                        if j <= i:
                            continue
                        offset = centers[j] - centers[i]
                        distance = np.linalg.norm(offset)
                        if not 1e-10 < distance <= radius:
                            continue
                        direction = offset / distance
                        facing_i = np.dot(normals[i], direction)
                        facing_j = np.dot(normals[j], direction)
                        if facing_i < MIN_FACING_PROJECTION or facing_j > -MIN_FACING_PROJECTION:
                            continue
                        overlap = np.dot(normals[i], normals[j])
                        if abs(overlap) >= COS30:
                            continue
                        candidates.append(((1 - overlap) / distance**2, j))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        for _, j in candidates[:top_k]:
            source.append(i)
            target.append(j)
    return np.asarray((source, target), dtype=np.int64).reshape(2, -1)


def read_current(path: Path, count: int):
    values = np.zeros((count, 6), dtype=np.float32)
    seen = np.zeros(count, dtype=bool)
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            parts = line.split()
            if len(parts) < 10:
                continue
            try:
                index = int(parts[0]) - 1
                current = [float(v) for v in parts[4:10]]
            except ValueError:
                continue
            if not 0 <= index < count or seen[index]:
                raise ValueError(f"Invalid or duplicate current index in {path}: {index + 1}")
            values[index] = current
            seen[index] = True
    if not seen.all() or not np.isfinite(values).all():
        raise ValueError(f"Incomplete or nonfinite current data in {path}: {seen.sum()}/{count}")
    return values


def default_output(sim_dir: Path) -> Path:
    case_name = "single" if sim_dir.name.lower() == "case_single" else sim_dir.name
    return ROOT / f"dataset_{case_name}_1ghz.pt"


def main(
    sim_dir: Path = SIM_DIR,
    output: Path | None = None,
    triangles_per_g1: int = TRIANGLES_PER_G1,
    g1_per_g2: int = G1_PER_G2,
    require_convergence: bool = False,
):
    output = output or default_output(sim_dir)
    cfm_files = sorted(sim_dir.glob("*.cfm"))
    if len(cfm_files) != 1:
        raise ValueError(f"Expected exactly one CFM mesh in {sim_dir}, found {len(cfm_files)}")
    cfm_path = cfm_files[0]
    grids, triangles = parse_nas(cfm_path.with_suffix(".nas"))
    verify_cfm_mesh(cfm_path, triangles, grids)
    count = len(triangles)
    print(f"Matched CFM/NAS: {count} triangles", flush=True)
    if triangles_per_g1 < 1 or g1_per_g2 < 1:
        raise ValueError("Cluster group sizes must be positive")
    n_g1 = math.ceil(count / triangles_per_g1)
    n_g2 = math.ceil(n_g1 / g1_per_g2)
    if count < n_g1 or n_g1 < n_g2:
        raise ValueError("Cluster counts must satisfy triangles >= G1 >= G2")
    if require_convergence:
        for phi in PHI_ANGLES:
            out_path = sim_dir / f"phi{phi:03d}" / "mom.out"
            output_text = out_path.read_text(encoding="utf-8", errors="replace") if out_path.is_file() else ""
            if "Stopping after" not in output_text or "WARNING   830" in output_text:
                raise ValueError(f"MoM convergence is not confirmed for phi={phi:03d}: {out_path}")
    centers, normals, areas = compute_geometry(triangles, grids)
    e0, edge_to_triangles = geometry_graph(triangles)

    c01 = fit_connected_clusters(
        np.column_stack((centers, ALPHA * normals)), n_g1, 5000, e0, GEODESIC_WEIGHT
    )
    c1_centers, c1_normals = cluster_centers(c01, centers, normals, n_g1)
    e1 = boundary_edges(edge_to_triangles, c01)
    c12 = fit_connected_clusters(
        np.column_stack((c1_centers, ALPHA * c1_normals)), n_g2, 200, e1, GEODESIC_WEIGHT
    )
    c2_centers, c2_normals = cluster_centers(c12[c01], centers, normals, n_g2)
    e2 = boundary_edges(edge_to_triangles, c12[c01])
    coupling1 = coupling_edges(c1_centers, c1_normals, 32, G1_COUPLING_RADIUS_M)
    coupling2 = coupling_edges(c2_centers, c2_normals, 8, G2_COUPLING_RADIUS_M)
    cluster = {"c01": torch.from_numpy(c01), "c12": torch.from_numpy(c12)}
    geo_edges = {"e0": torch.from_numpy(e0), "e1": torch.from_numpy(e1), "e2": torch.from_numpy(e2)}
    cpl_edges = {"e1": torch.from_numpy(coupling1), "e2": torch.from_numpy(coupling2)}
    print(f"G1={n_g1}, G2={n_g2}; geo edges={tuple(e.shape[1] for e in (e0, e1, e2))}", flush=True)

    samples = []
    for phi in PHI_ANGLES:
        angle_dir = sim_dir / f"phi{phi:03d}"
        mom = read_current(angle_dir / "mom_mom_Currents.os", count)
        po = read_current(angle_dir / "po_po_Currents.os", count)
        scale = float(np.mean(np.linalg.norm(po, axis=1, keepdims=True) + 1e-6)) + 1e-6
        x = np.column_stack((centers, normals, areas[:, None], po / scale)).astype(np.float32)
        y = ((mom - po) / scale).astype(np.float32)
        if not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError(f"Nonfinite sample phi={phi}")
        theta_rad = np.deg2rad(THETA_DEG)
        phi_rad = np.deg2rad(phi)
        wave = np.asarray((
            -np.sin(theta_rad) * np.cos(phi_rad),
            -np.sin(theta_rad) * np.sin(phi_rad),
            -np.cos(theta_rad),
        ), dtype=np.float32)
        samples.append({
            "X": torch.from_numpy(x), "Y": torch.from_numpy(y), "scale": scale,
            "K0": 2 * np.pi * FREQUENCY_HZ / C0, "k_hat": torch.from_numpy(wave),
            "phi": phi, "cluster": cluster, "geo_edges": geo_edges,
            "cpl_edges": cpl_edges, "num_triangles": count,
        })
        relative = np.linalg.norm(po - mom) / max(np.linalg.norm(mom), 1e-30)
        print(f"phi={phi:03d} PO_rel={relative:.5f}", flush=True)

    dataset = {
        "samples": samples,
        "num_angles": len(samples),
        "theta_deg": THETA_DEG,
        "frequency_hz": FREQUENCY_HZ,
        "cluster_config": {
            "n_g1": n_g1, "n_g2": n_g2,
            "triangles_per_g1": triangles_per_g1, "g1_per_g2": g1_per_g2,
            "method": "connected_kmeans_6d", "alpha": ALPHA,
            "geodesic_weight": GEODESIC_WEIGHT,
            "coupling_min_facing_projection": MIN_FACING_PROJECTION,
            "coupling_max_facing_angle_deg": MAX_FACING_ANGLE_DEG,
            "wavelength_m": WAVELENGTH_M,
            "coupling_radius_lambda": {
                "g1": G1_COUPLING_RADIUS_LAMBDA,
                "g2": G2_COUPLING_RADIUS_LAMBDA,
            },
            "coupling_radius_m": {
                "g1": G1_COUPLING_RADIUS_M,
                "g2": G2_COUPLING_RADIUS_M,
            },
        },
    }
    torch.save(dataset, output)
    print(f"Saved {output}: {len(samples)} samples, X={tuple(samples[0]['X'].shape)}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, default=SIM_DIR, help="Directory containing NAS, CFM and phi folders")
    parser.add_argument("--output", type=Path, help="Defaults to PO2MoM_TF/dataset_<case>_1ghz.pt")
    parser.add_argument("--triangles-per-g1", type=int, default=TRIANGLES_PER_G1, help="Average triangles per G1 target (default: 15)")
    parser.add_argument("--g1-per-g2", type=int, default=G1_PER_G2, help="Average G1 clusters per G2 target (default: 15)")
    parser.add_argument("--require-convergence", action="store_true", help="Reject MoM .out files with FEKO warning 830")
    args = parser.parse_args()
    main(
        args.case_dir.resolve(), args.output.resolve() if args.output else None,
        args.triangles_per_g1, args.g1_per_g2, args.require_convergence,
    )
