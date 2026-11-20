# Reproducing the historical pipelines

These commands reproduce the original five-family or six-fixed-geometry work. They do not accept a new `case6` or an arbitrary list of 12 angle pairs. For a new experiment, follow [new-experiment.md](new-experiment.md) and adapt a separate work copy under its own experiment ID.

The bundled source tree is `scripts/simulation_A/` and `scripts/simulation_smallbatch/`. It contains code only. `launch.ps1` stages code into an existing, separately chosen *work root* with sibling `simulation_A` and `simulation_smallbatch` folders. It refuses to overwrite a differing target file. Copy the real project input files into that work root yourself: `simulation_A/variants.md`, each base `caseN/caseN.cfx`, and prepared variant input folders; fixed-case CFM/NAS/PRE go under `simulation_smallbatch/caseN` and `case_single`. The bundling script does not create CAD or mesh data and does not stage any `.pt`, `.cfm`, `.nas`, `.os`, or logs. Paths are relative to the staged scripts. For mesh preparation the CADFEKO path is passed explicitly to `prepare_meshes.ps1`; FEKO binaries remain external.

From the Skill's `scripts/` directory in PowerShell (substitute a real absolute work root):

```powershell
.\launch.ps1 -WorkRoot 'D:\PO2MoM_work' -Mode Stage             # preview code staging
.\launch.ps1 -WorkRoot 'D:\PO2MoM_work' -Mode Stage -Apply      # stage code
.\launch.ps1 -WorkRoot 'D:\PO2MoM_work' -Mode Check -Variant case1_02
.\launch.ps1 -WorkRoot 'D:\PO2MoM_work' -Mode Prepare -Variant case1_02 -Apply -LimitAngles 2
.\launch.ps1 -WorkRoot 'D:\PO2MoM_work' -Mode Solve -Variant case1_02 -Apply -Np 6 -FekoBin 'E:\Altair\feko\2025\feko\bin'
```

`Check` is read-only and requires existing CFM/NAS. `Prepare` writes angle PREs only. `Solve` runs 93 MoM/PO pairs for one explicitly named variant, builds and verifies its dictionary dataset, then cleans only the listed intermediate solver files; it retains NAS/CFM, PRE, `mom.out`, markers, and archive manifest. For a new variant, first run `simulation_A/prepare_meshes.ps1 -CaseId case1 -VariantId case1_02 -FekoBin ...` from a reviewed variant parameter plan; that script generates all configuration files and invokes CADFEKO for the selected mesh. It is not dry-run and the original variant mesh-prep script removes selected prior prepared outputs before remeshing, so inspect targets first. Avoid `-Force` on established results. Use `automation/verify_prepared_meshes.py` when the whole 100-mesh inventory is present.

Fixed-case procedure is separate: `python simulation_smallbatch/run_simulations.py --prepare-only --cases case1 --theta 10 --phi 0`, then a selected solve `--cases case1 --theta 10 --phi 0 --np 6 --feko-bin ...`, then `python simulation_smallbatch/dataset_builder_AllAngle.py --cases case1 --theta 10 --phi 0` for that deliberately selected subset. Its default builder requires all 629 directions. Do not use `simulation_A`'s 93-direction builder for these fixed cases.

Resume: `RUNNING.lock` protects the variant runner. Check its PID and FEKO processes before removing a stale lock. Create `simulation_A/STOP_REQUESTED` to stop between solves; remove it before restart. The runner verifies PRE hashes, current rows, and MoM convergence before skipping a solved direction. `status.json` reports progress, `failure.json` records variant/stage/angle/method, and `mom.log`/`mom.out` explain solver failures. A failure in one variant does not mark it complete. `--np 6` is six ranks in one MoM; `--jobs 2` would start two case queues and can double aggregate demand. The wrapper intentionally limits one selected variant at a time.

After per-variant outputs exist, run `simulation_A/collect_datasets.ps1 -DryRun` to preview the move, then without `-DryRun` to collect. `python simulation_A/dataset/comb.py` requires all 100 files, free disk, and writes nine split files. This collection is a move, not a copy, and is not appropriate while a solver is active. Validate counts and selected IDs in the resulting files before training; never silently infer a missing variant. No large sweep is started by installing or checking this Skill.
