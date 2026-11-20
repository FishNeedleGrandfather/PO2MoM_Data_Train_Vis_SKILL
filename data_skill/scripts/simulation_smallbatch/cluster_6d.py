"""Original position-and-normal clustering used by the 1 GHz datasets."""

from __future__ import annotations

import numpy as np
from heapq import heappop, heappush
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.cluster import KMeans, MiniBatchKMeans


def fit_clusters(features: np.ndarray, count: int, batch_size: int) -> np.ndarray:
    if features.ndim != 2 or not np.isfinite(features).all():
        raise ValueError("Expected finite [N, D] cluster features")
    if not 1 <= count <= len(features):
        raise ValueError("Cluster count must be between 1 and the number of inputs")
    labels = MiniBatchKMeans(
        n_clusters=count, random_state=42, batch_size=batch_size, n_init=3
    ).fit_predict(features)
    if np.unique(labels).size != count:
        labels = KMeans(n_clusters=count, random_state=42, n_init=3).fit_predict(features)
    if np.unique(labels).size != count:
        raise ValueError(f"Expected {count} nonempty clusters")
    return labels.astype(np.int64)


def fit_connected_clusters(
    features: np.ndarray, count: int, batch_size: int, edges: np.ndarray,
    geodesic_weight: float = 1.0,
) -> np.ndarray:
    """KMeans-seeded region growing; every label induces a connected subgraph."""
    n = len(features)
    if features.ndim != 2 or not np.isfinite(features).all():
        raise ValueError("Expected finite [N, D] cluster features")
    if not 1 <= count <= n or edges.ndim != 2 or edges.shape[0] != 2:
        raise ValueError("Invalid cluster count or [2, E] geometry edges")
    if geodesic_weight < 0 or not np.isfinite(geodesic_weight):
        raise ValueError("geodesic_weight must be finite and nonnegative")
    if edges.size and (edges.min() < 0 or edges.max() >= n):
        raise ValueError("Geometry edge index out of range")

    graph = coo_matrix(
        (np.ones(edges.shape[1] * 2, dtype=np.int8),
         (np.r_[edges[0], edges[1]], np.r_[edges[1], edges[0]])),
        shape=(n, n),
    ).tocsr()
    n_parts, parts = connected_components(graph, directed=False)
    if n_parts > count:
        raise ValueError(f"{n_parts} disconnected geometry components need at least that many clusters")
    part_sizes = np.bincount(parts)
    allocation = np.ones(n_parts, dtype=np.int64)
    quotas = count * part_sizes / n
    for _ in range(count - n_parts):
        priority = np.where(allocation < part_sizes, quotas - allocation, -np.inf)
        allocation[int(np.argmax(priority))] += 1

    result = np.full(n, -1, dtype=np.int64)
    offset = 0
    for part, k in enumerate(allocation):
        nodes = np.flatnonzero(parts == part)
        local_features = features[nodes]
        labels = fit_clusters(local_features, int(k), batch_size)
        centroids = np.vstack([local_features[labels == c].mean(axis=0) for c in range(k)])
        seeds = np.array([
            np.flatnonzero(labels == c)[np.argmin(
                np.sum((local_features[labels == c] - centroids[c]) ** 2, axis=1)
            )]
            for c in range(k)
        ])
        local_graph = graph[nodes][:, nodes].tocsr()
        assigned = np.full(len(nodes), -1, dtype=np.int64)
        assigned[seeds] = np.arange(k)
        heap = []

        def push_neighbors(src: int, cluster: int, path_length: float) -> None:
            start, stop = local_graph.indptr[src:src + 2]
            for dst in local_graph.indices[start:stop]:
                if assigned[dst] != -1:
                    continue
                distance = float(np.linalg.norm(local_features[dst, :3] - local_features[src, :3]))
                new_path = path_length + distance
                feature_cost = float(np.sum((local_features[dst] - centroids[cluster]) ** 2))
                score = feature_cost + (geodesic_weight * new_path) ** 2
                heappush(heap, (score, cluster, int(dst), new_path))

        for cluster, seed in enumerate(seeds):
            push_neighbors(int(seed), cluster, 0.0)
        while heap:
            _, cluster, dst, path_length = heappop(heap)
            if assigned[dst] != -1:
                continue
            assigned[dst] = cluster
            push_neighbors(dst, cluster, path_length)
        if np.any(assigned < 0) or np.unique(assigned).size != k:
            raise ValueError("Connected cluster growth failed")
        result[nodes] = assigned + offset
        offset += int(k)
    return result
