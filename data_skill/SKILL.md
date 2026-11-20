---
name: po2mom-data
description: Inspect, validate, build, and hand off the PO2MoM_TF 1 GHz MoM/PO datasets; use for the fixed six-geometry sweep or the five-family parameter-variant pipeline, including resumable FEKO runs and dataset provenance.
---

# PO2MoM dataset handoff

First identify which pipeline the request concerns. Read [references/datasets.md](references/datasets.md) for dataset names, splits, tensor fields, and normalization. Read [references/operations.md](references/operations.md) before preparing or running FEKO, collecting, or rebuilding datasets. Inspect actual files and status before claiming completion.

Two distinct angle plans exist. `simulation_smallbatch` has six fixed geometries and 629 directions per geometry. `simulation_A` has five CAD families, 20 variants each, and 93 directions per variant. Do not interchange the plans. `case_single`, SLICY, feiji, and `case_addTrain` are not members of the five-family A1 training set. A dense angle holdout on an already seen mesh is not a new-geometry test.

Reusable code is bundled in `scripts/`. Use `scripts/launch.ps1` to stage it into a separate working root alongside the user's CFX/CFM/NAS, then run a read-only check or a selected variant. Never put large meshes, currents, or `.pt` files into this Skill. The user's data stays under the chosen work root. FEKO, Python, PyTorch, NumPy, SciPy, scikit-learn, and threadpoolctl are external dependencies.

For a new geometry, verify CAD adjustability and CFM/NAS element order before solving. A `.cfm` is a solver mesh, not a parameterized CAD template. Do not infer an archived solve from a dataset file alone; verify the matching mesh hash, angle coverage, current row count and convergence record. Full FEKO work requires the user's explicit requested scope and resource budget. `--np` is MPI ranks for one MoM solve; `--jobs` is concurrent case workers.
