"""CPU-only synthetic V7 forward/backward check; never trains or saves."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F


MODEL_CLASSES = {
    "MLP", "LocalExchange", "BiasTransformerBlock", "CoupleExchange",
    "DownBlock", "MGTransformer", "Geo_cache", "PO2MoMModel",
}


def load_model_class(path: Path):
    """Extract model definitions without executing the training script."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes = [node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name in MODEL_CLASSES]
    if {node.name for node in classes} != MODEL_CLASSES:
        raise ValueError(f"Missing V7 model classes in {path}")
    module = ast.fix_missing_locations(ast.Module(body=classes, type_ignores=[]))
    namespace = {"torch": torch, "nn": nn, "F": F}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["PO2MoMModel"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-source", type=Path,
                        help="Path to trainV7A.py or compatible V7 model source; "
                             "required when this skill is outside the project")
    parser.add_argument("--checkpoint", type=Path)
    args = parser.parse_args()

    nearby_source = Path(__file__).resolve().parents[3] / "trainV7A.py"
    model_source = args.model_source or nearby_source
    if not model_source.is_file():
        parser.error(f"Model source not found: {model_source}. Pass --model-source PATH")

    torch.set_num_threads(1)
    torch.manual_seed(7)
    model = load_model_class(model_source)()
    if args.checkpoint:
        state = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
        model.load_state_dict(state["model_state_dict"], strict=True)

    centers = torch.tensor([[0., 0., 0.], [1., 0., 0.],
                            [2., 0., 0.], [3., 0., 0.]])
    normals = torch.tensor([[0., 0., 1.]]).repeat(4, 1)
    areas = torch.ones(4, 1)
    po = torch.randn(4, 6) * 0.1
    sample = {
        "X": torch.cat([centers, normals, areas, po], dim=1),
        "Y": torch.randn(4, 6) * 0.1,
        "K0": 20.0,
        "k_hat": torch.tensor([1., 0., 0.]),
        "cluster": {
            "c01": torch.tensor([0, 0, 1, 1]),
            "c12": torch.tensor([0, 0]),
        },
        "geo_edges": {
            "e0": torch.tensor([[0, 1, 2], [1, 2, 3]]),
            "e1": torch.tensor([[0], [1]]),
            "e2": torch.empty((2, 0), dtype=torch.long),
        },
        "cpl_edges": {
            "e1": torch.tensor([[0], [1]]),
            "e2": torch.empty((2, 0), dtype=torch.long),
        },
    }

    model.train()
    delta = model(sample, MG_NUM=4)
    assert delta.shape == sample["Y"].shape == (4, 6)
    assert torch.isfinite(delta).all()
    normal_component = (delta.reshape(4, 3, 2) * normals.unsqueeze(-1)).sum(dim=1)
    assert torch.allclose(normal_component, torch.zeros_like(normal_component), atol=1e-5)
    loss = F.mse_loss(delta, sample["Y"])
    po_baseline = F.mse_loss(torch.zeros_like(sample["Y"]), sample["Y"])
    assert torch.isfinite(loss) and torch.isfinite(po_baseline)
    loss.backward()
    grads = [p.grad for p in model.parameters() if p.grad is not None]
    assert grads and all(torch.isfinite(g).all() for g in grads)
    print(f"OK: output={tuple(delta.shape)} MSE={loss.item():.6g} "
          f"PO_MSE={po_baseline.item():.6g} finite_gradients={len(grads)}")


if __name__ == "__main__":
    main()
