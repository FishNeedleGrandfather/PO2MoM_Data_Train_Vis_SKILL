---
name: po2mom-v7-training
description: Plan, build, review, or explain PO-to-MoM current-correction training in PO2MoM_TF, including new geometries, angle sets, V7 architecture changes, checkpoints, splits, and metrics. Not for FEKO simulation or website work.
---

# PO→MoM training handoff

Project root contains `PO2MoM_TF`. Re-read the relevant source at the start of a task; this skill describes a verified V7 snapshot, not a permanent experiment configuration. The user normally wants to discuss a design before changing training code and does not want extra BAT files.

## Start a new task

Read [references/new-experiment.md](references/new-experiment.md) first. It routes from the scientific objective through data provenance, split, model changes, checkpoint compatibility, one-sample smoke check, training strategy, and evaluation handoff. Use it even when a new experiment resembles A1: a new case, arbitrary direction list, and new experiment ID do not inherit V7A's paths or angle rules. Read [references/network.md](references/network.md) when rebuilding or changing the network and [references/training.md](references/training.md) for loss, optimizer, and evaluation contracts. Do not start a costly run until the user's intended design and compute scope are clear.

## Reproduce or query historical work

Read [references/history.md](references/history.md) and the current `PO2MoM_TF/record.md`. Verify checkpoint metadata, data split, and code version before comparing runs. Read [references/network.md](references/network.md) only if architecture is in question; read [references/training.md](references/training.md) for metric interpretation. An old result is evidence for its own split and initialization, not an automatically valid baseline for a new task.

## Invariants across both paths

- Predict a six-component complex-current correction, not the full current. With eta normalization, `Y=η₀(J_MoM−J_PO)` and `X[:,7:13]=η₀J_PO`; output is projected tangentially. `MSE(delta,Y)` and zero-correction PO MSE are not current-relative error.
- Keep whole geometries (`variant_id` or equivalent mesh identity) in a single geometry partition when claiming unseen-geometry performance. Track angle partitions separately and include any angle exposure through validation or pretraining.
- Clear accumulated gradients after *every* `optimizer.step()`. Choose batch scaling according to actual accumulation count, including a short final batch.
- Treat `MG_NUM`, shared versus unshared blocks, normalization, and tensor shapes as checkpoint compatibility decisions. A successful `load_state_dict` is necessary but does not prove matching experiment semantics.
- Never import `trainV7A.py` or `trainV7AllAngle.py` just to inspect their classes: their top-level code loads data and starts training. `PO2MoM_TF/export_allangle_visualization.py:load_model_class` extracts only model classes. The optional [scripts/check_contract.py](scripts/check_contract.py) performs a small synthetic forward/backward without training or saving.
