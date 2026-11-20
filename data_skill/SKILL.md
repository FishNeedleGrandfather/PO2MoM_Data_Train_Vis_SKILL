---
name: po2mom-data
description: Plan a new PO2MoM_TF MoM/PO dataset experiment or reproduce and inspect the historical fixed-geometry and five-family datasets; validate angle-pair manifests, mesh/current integrity, and dataset provenance.
---

# PO2MoM data experiments

Choose the entry point from the request:

- **Start a new task:** Read [references/new-experiment.md](references/new-experiment.md). Create a new experiment ID and an explicit list of `(theta, phi)` pairs with intended groups. Run `scripts/check_experiment.py` on the manifest before adapting any solver code. Preserve the physical and data integrity contract below. Historical scripts are implementation references, not a general case/angle engine.
- **Reproduce or query historical work:** Read [references/datasets.md](references/datasets.md) for actual artifacts and schema, then [references/operations.md](references/operations.md) if running the original FEKO or dataset workflows. Check real files, statuses, and lineage before reporting results.

Shared contract for either route: a PEC model with known CAD units, one explicit frequency/polarization convention, CFM solver mesh and same-order NAS, matched MoM/PO per angle on that mesh, finite complete triangle currents, MoM convergence evidence, and the η₀-normalized [sample schema](references/schema.md). A `.cfm` is not an adjustable CAD template. Lock geometry and angle group assignments before looking at results. Do not call seen prototypes or a dense-angle interpolation split an untouched new-geometry test.

Historical code is bundled in `scripts/`. `scripts/launch.ps1` stages it into a separate work root for *historical* runs. It only accepts `case1`–`case5` variant IDs and the 93-direction plan. For a new experiment, branch/adapt the staged code under the new experiment root and update every case, angle, validation, naming, and combiner assumption identified in the new-task reference. Keep the original bundle unchanged for reproduction. Never put large meshes, currents, or `.pt` files in this Skill.

FEKO, Python, PyTorch, NumPy, SciPy, scikit-learn, and threadpoolctl are external dependencies. Full FEKO work requires the user's requested compute scope. `--np` is MPI ranks for one MoM solve; `--jobs` is concurrent case workers.
