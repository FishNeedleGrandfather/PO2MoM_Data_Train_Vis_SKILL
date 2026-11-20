# Dataset inventory and schema

Source of truth: bundled `run_variants.py`, `dataset_builder_AllAngle.py`, `datasetbuilder_1ghz.py`, `cluster_6d.py`, and `comb.py`. Confirm the actual files before a new split or training run. PyTorch `.pt` files are pickle-backed: load only trusted project artifacts, using `torch.load(..., map_location="cpu", weights_only=False)`.

## Fixed six geometries (`simulation_smallbatch`)

`case1`–`case5` and `case_single` are six fixed meshes at PEC, 1 GHz, one polarization. θ=10:5:90 (17 values), φ=0:5:180 (37 values): 629 paired MoM/PO directions per geometry. After running `run_simulations.py`, separately invoke `dataset_builder_AllAngle.py`. `datasets/dataset_caseN_allangle_eta.pt` and `dataset_case_single_allangle_eta.pt` are dictionaries with `samples` (normally 629), angle/frequency/normalization/cluster metadata. `datasets/dataset_case1to5_allangle_eta.pt` is a **list of five case dictionaries**; `case_single` is excluded. A runner does not build this dataset automatically. The builder requires all angles unless `--skip-incomplete` is explicitly chosen and omissions are recorded.

## Parameter variants (`simulation_A`)

Five families `case1`–`case5`, variants `caseN_01`–`caseN_20`. `variants.md` is the fixed parameter plan (six columns `a1`–`a6`); `01` is the original combination. Each variant has 93 directions:

| Angle group | θ | φ | Samples/variant |
|---|---|---|---:|
| `train_angles` | 35, 45, 55 | 0:10:180 | 57 |
| `val_angles` | 40, 50 | 5:10:85 | 18 |
| `test_angles` | 40, 50 | 95:10:175 | 18 |

`caseN/caseN_XX/datasetN_XX.pt` is a dictionary: `samples` (93), `variant_id`, `case_id`, `parameters`, `mesh_sha256`, `num_triangles`, `num_angles`, `angle_groups`, `frequency_hz`, `normalization`, `cluster_config`. `collect_datasets.ps1` moves existing per-variant files to `simulation_A/dataset/`, skipping absent files and refusing name collisions. `dataset/comb.py` requires all 100 variant files and emits nine **flat sample lists**, with per-sample `variant_id`, `case_id`, `parameters`, and `mesh_sha256` added. Naming `dataset{geometry-code}V{angle-code}A.pt`: `X` variants 01–12 (60 geometries), `V` variants 13–15 (15), `C` variants 16–20 (25); angle `X`=57, `V`=18, `C`=18. Thus `datasetXVXA.pt`=60×57=3420; `XVVA`/`XVCA`=1080 each; `VVXA`=855; `VVVA`/`VVCA`=270 each; `CVXA`=1425; `CVVA`/`CVCA`=450 each. These are *geometry and angle* partitions, not interchangeable with the 629-angle fixed data. Prototypes and `case_single` were used during development; do not label them untouched final tests.

## Sample fields and geometry

For `N` triangles, each sample contains `X` float32 `[N,13]`: triangle center `[x,y,z]`, unit normal `[nx,ny,nz]`, area, and six real/imag PO current components multiplied by η₀. `Y` float32 `[N,6]` equals η₀·(`J_MoM−J_PO`); `scale=1/η₀`, η₀=376.730313668 Ω. Multiply predictions by `scale` to recover physical residual current. `K0=2πf/c`, `k_hat` float32 `[3]` is `(-sinθ cosφ,-sinθ sinφ,-cosθ)`, plus integer-degree `theta`, `phi`, `num_triangles`. Positions retain the CAD origin; no global `r−r_c` conversion. Per-variant samples also carry `angle_group`.

`cluster.c01` `[N]` maps G0 triangles to G1, `cluster.c12` `[G1]` maps G1 to G2. Counts target `ceil(N/15)` G1 and `ceil(G1/15)` G2. Connected six-dimensional clustering uses `[center, 0.5×normal]`, seed 42 for KMeans, and geodesic weight 1.0. `geo_edges.e0/e1/e2` are undirected edge-pair tensors `[2,E]`: shared triangle mesh edge, then boundaries between clusters. `cpl_edges.e1/e2` have shape `[2,E]` and store each selected pair only once, with `i<j`; the dataset does not store reverse edges. For each `i`, the builder retains at most 32 eligible `j` at G1 within 5/3 wavelength, or 8 at G2 within 10/3 wavelength. Eligibility uses oriented normal-facing projections (at least cos75° toward the other node) and excludes near-parallel/opposite normals with absolute dot ≥ cos30°; candidates are ranked by `(1−normal_dot)/distance²`. The model's `Geo_cache` concatenates the stored indices in both orders when it consumes these coupling edges. The stored tensors are shared by samples of the same geometry.

The builder requires ordered CFM/NAS triangle centers matching within 1e−6 m, nondegenerate triangles, method completion markers with PRE hash and triangle count, MoM `.out` convergence, and exactly one finite complex-current row per triangle with complete index coverage. Never construct from a partial MoM/PO pair or treat a `.done.json` alone as proof.

## Other current data

`case_addTrain` has three independent 19-direction datasets at θ=45°, φ=0:10:180 (`LayerCircle`, `LayerCylinder`, `ThreeAngle`); each is a dictionary with `samples`. `case_addTrain/dataset_transfer_8geom_theta45.pt` is a flat list of 152 samples from those three plus one seeded training variant from each of the five original families. Its `_selection.json` records the chosen variants. SLICY and feiji are independent complex targets; if used to select a checkpoint they become development data, not untouched final tests.
