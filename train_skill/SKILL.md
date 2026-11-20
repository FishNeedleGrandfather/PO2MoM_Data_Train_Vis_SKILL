---
name: po2mom-v7-training
description: Rebuild, adapt, review, or plan training for this PO-to-MoM V7 network and its A1 geometry/angle datasets. Use for architecture, checkpoint, split, loss, and evaluation decisions in PO2MoM_TF; not for FEKO simulation or website work.
---

# PO→MoM V7 training handoff

Work from the current code, not from this snapshot alone. The project root is the directory containing `PO2MoM_TF`; the current model/training entry points are `PO2MoM_TF/trainV7A.py` and `PO2MoM_TF/trainV7AllAngle.py`. Read both before changing a run. `PO2MoM_TF/record.md` has measured experiments; distinguish those from code settings. The user normally wants the design discussed before code changes, and does not want extra BAT files.

Read [references/network.md](references/network.md) when rebuilding or modifying model, feature, graph, cache, checkpoint, or forward behavior. Read [references/training.md](references/training.md) when planning a run, changing data splits/optimizer/loss, selecting a checkpoint, or interpreting metrics. Read both for a new end-to-end training scheme.

Core invariants:

- Predict the normalized six-component complex-current correction `Y = η₀(J_MoM − J_PO)` from normalized `η₀ J_PO`; the decoder output is projected into the local tangent plane. `criterion(pred, Y)` is correction MSE. A zero correction is the PO MSE baseline. Neither is current-relative error.
- Keep a whole `variant_id` in one geometry partition. In the current A1 run, `XVXA` is training and `VVVA+VVCA` selects checkpoints. `CVCA` uses held-out C geometries, but C angles have already influenced model selection through `VVCA`; describe its geometry and angle novelty separately. The V in filenames marks the variant dimension; the A marks angle. Reinspect `simulation_A/dataset/comb.py` if the partition policy changes.
- Current `MG_NUM=4` calls reuse the same `mg_transformer` and `local_exchange_post` parameters. Do not load a state dict into a different structure without checking keys, shapes, normalization, and call count.
- Every gradient accumulation `optimizer.step()` must be followed by `optimizer.zero_grad()`; experiments 17/18 in `record.md` are invalid because this was omitted.
- Report exact split, initialization checkpoint, optimizer state choice, `MG_NUM`, validation selection rule, and whether evaluation geometry or angles appeared in pretraining. Do not claim new-geometry performance from adjacent-angle validation.

For a lightweight, non-training check after an edit, run `python -m py_compile PO2MoM_TF/trainV7A.py` and inspect the model loader in `PO2MoM_TF/export_allangle_visualization.py` (its `load_model_class` extracts only the model classes, avoiding training at import). For data shape and split counts, use the assertions documented in [references/training.md](references/training.md). Do not import `trainV7A.py` merely to inspect classes: its top-level code loads data and starts training.
