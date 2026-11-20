# Training and evaluation contract

This file contains the reusable contract. Read [history.md](history.md) for the current A1 file mapping, epoch numbers, and reported outcomes; read [new-experiment.md](new-experiment.md) for a new-run design sequence.

## Data and physical meaning

For the current eta builder, `η₀=376.730313668`, `X[:,7:13]=η₀ J_PO`, `Y=η₀(J_MoM−J_PO)`, `scale=1/η₀`, and `K0` is the sample's wavenumber. The six current entries interleave real/imag x,y,z. Changing normalization, frequency, mesh ordering, or polarization requires explicit data/model compatibility review. A future builder may use different values; inspect its metadata before assuming these.

The output `delta:[N0,6]` is normalized correction. Train using `MSE(delta,Y)` if retaining this target. The PO baseline on a given split is `MSE(zeros_like(Y),Y)`, computed with the same per-sample aggregation. To recover physical currents use `J_pred=(X[:,7:13]+delta)*scale` and `J_MoM=(X[:,7:13]+Y)*scale`. For each sample, relative error is `||J_pred−J_MoM||_F / ||J_MoM||_F ×100%`, over six real/imag components and all triangles, without area weighting. Compute per-sample first; state whether the final value is sample weighted or equal per geometry/family. The common sample scale cancels in the ratio. A ratio of aggregate MSE values cannot be called relative current error.

## Splits, optimization, and checkpoint semantics

Separate geometry identity from incidence direction. Group all angles of a `variant_id` when the claim is about unseen geometry; decide which angle IDs are used for fitting, checkpoint selection, and untouched evaluation. A direction used on a validation geometry has influenced model selection, even if the final test geometry is held out. Check pretraining provenance before claiming a direction was never seen.

For gradient accumulation, divide each sample loss by the actual number of samples in its update group, call backward for the group, then `optimizer.step()` and immediately `optimizer.zero_grad()`. The last short group needs its own denominator. A single shuffle before the epoch loop repeats the same order each epoch; decide whether to reshuffle each epoch for a new experiment. Validation needs `model.eval()` and no gradient recording, and its aggregation must match the declared selection metric.

Declare whether a checkpoint is for initialization, exact resume, best-model selection, or final inference. Loading model state only and constructing new Adam is fine-tuning. Exact resume additionally needs optimizer/scheduler, RNG, counters, and progress state. Save best checkpoint against the designated validation metric; keep an independent final test out of selection. Use unique experiment output names. Online epoch train loss mixes parameter states as updates occur; re-evaluate the best checkpoint for a fixed-weight train metric. If plotting history after the loop, interruptions may leave no final curve even when a best checkpoint exists.

Compare models only on the same samples, normalization, metric, and aggregation. For an unseen-geometry claim, report the geometry split explicitly and distinguish angles seen in training, validation, or pretraining. A low adjacent-angle MSE by itself does not establish transfer to a different mesh.
