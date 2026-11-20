# Historical V7 and A1 snapshot

Use `PO2MoM_TF/record.md` for reported observations and recheck current scripts/checkpoints for reproducibility. The following facts describe existing runs, not rules for new experiments.

| Run | Input and selection | Initialization / configuration | Observed result |
| --- | --- | --- | --- |
| V7 18-angle | Five fixed cases, 15 train + 3 validation angles per case, eta normalized | `trainV7.py`, shared MG called four times; `case1_1ghz_bestV7_4_eta.pt` | Best epoch 705, validation correction MSE ≈0.03263611 on that split |
| 17/18 all-angle | 855 train, 120 adjacent-angle validation | `trainV7AllAngle.py`, MG 4 | Invalid because gradients were not zeroed after each five-sample step |
| 19 all-angle | Same 855/120 split | Starts from earlier V7 weights, corrected gradient clearing, `case1_1ghz_bestV7_eta_all.pt` | Best epoch 204, validation correction MSE ≈0.01475297, PO baseline ≈0.1903792 |
| 20 A1 variants | `XVXA` 3420 train; `VVVA+VVCA` 540 validation | `trainV7A.py` from all-angle model weights; fresh Adam, MG 4, `case1_1ghz_bestV7_eta_comb.pt` | Best epoch 100, validation correction MSE ≈0.038437246; current-relative errors ≈30.18%/30.20% on VVVA/VVCA |

The A1 `simulation_A/dataset/comb.py` currently reads 100 variants, 20 per geometry family. Per family, variant IDs 01–12 are X/train, 13–15 V/validation, 16–20 C/test. Each has 57 X-angle samples (θ35/45/55, φ0:10:180), 18 V-angle samples (θ40/50, φ5:10:85), and 18 C-angle samples (θ40/50, φ95:10:175). Nine `dataset{geometry_code}V{angle_code}A.pt` files are flat sample lists. `CVCA` holds C geometries, but C angles were used for model selection on V geometries via `VVCA`; do not call them globally blind angles. The old `trainV7AllAngle.py` has a *different* nested dataset format and angle filter.

`trainV7A.py` loads only model weights from the all-angle checkpoint, constructs fresh Adam at LR 0.001, runs 100 epochs, accumulates five losses divided by five, steps and zeroes gradients, and halves LR after 20 non-improving validation epochs. It shuffles training samples once. Best checkpoint stores model/optimizer plus logged train/validation loss; the train value was accumulated before/during updates and is not a fixed-checkpoint reevaluation. History saves at the end. The old all-angle MSE and A1 MSE cannot be compared as the same validation set.

`record.md` also records SLICY 19-angle transfer as an independent geometry observation, not a guarantee of broad geometry generalization. Always verify exact checkpoint provenance and data identities when citing these results.
