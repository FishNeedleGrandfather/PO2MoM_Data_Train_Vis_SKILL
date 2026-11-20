# PO2MoM_TF project skills

These three Codex skills hand off the project's data, training, and evaluation workflows:

- [`data_skill`](data_skill/SKILL.md): FEKO simulation, dataset construction, schemas, and reusable scripts.
- [`train_skill`](train_skill/SKILL.md): V7 architecture, checkpoints, training, and evaluation splits.
- [`vis_val_skill`](vis_val_skill/SKILL.md): validation, experiment records, visualization, and GitHub Pages publication.

Install each directory as a separate skill, or read its `SKILL.md` before working in that area. The bundled scripts contain no CAD meshes, simulation outputs, model weights, datasets, or credentials. Check the current project files and actual run state before executing a workflow; these skills document the project as of 2026-11-20.
