"""Generate CADFEKO Lua configuration files from variants.md."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def lua_string(value: object) -> str:
    text = str(value).replace("\\", "/")
    if "]]" in text:
        raise ValueError("Lua long-string terminator is not allowed")
    return f"[[{text}]]"


def read_plan(path: Path) -> dict[str, dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    rows: dict[str, dict[str, str]] = {}
    for match in re.finditer(
        r"^\|\s*(case[1-5]_\d{2})\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|$",
        text,
        re.MULTILINE,
    ):
        rows[match.group(1)] = {
            f"a{index}": match.group(index + 1).strip() for index in range(1, 7)
        }
    if len(rows) != 100:
        raise ValueError(f"Expected 100 variants in {path}, found {len(rows)}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    plan = read_plan(root / "variants.md")
    prepare_lua = root / "automation" / "prepare_variant.lua"

    for variant_id, parameters in sorted(plan.items()):
        case_id = variant_id.split("_", 1)[0]
        case_dir = root / case_id
        variant_dir = case_dir / variant_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        source_cfx = case_dir / f"{case_id}.cfx"
        if not source_cfx.is_file():
            raise FileNotFoundError(source_cfx)

        mesh_outputs = [
            variant_dir / f"{variant_id}.cfm",
            variant_dir / f"{variant_id}.nas",
            variant_dir / f"{variant_id}.map",
        ]
        if all(path.is_file() and path.stat().st_size > 0 for path in mesh_outputs):
            status = "mesh_prepared"
        elif (variant_dir / "PREPARE_FAILED.json").is_file():
            status = "prepare_failed"
        else:
            status = "configured_not_meshed"

        metadata = {
            "case": case_id,
            "variant_id": variant_id,
            "parameters": parameters,
            "source_cfx": str(source_cfx),
            "source_cfx_sha256": sha256(source_cfx),
            "frequency_hz": 1_000_000_000,
            "mesh_size": "Standard",
            "status": status,
            "seed": 20261113,
        }
        (variant_dir / "variant_parameters.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        parameter_lines = [
            f"        {name} = {lua_string(value)}," for name, value in parameters.items()
        ]
        config = "\n".join(
            [
                "return {",
                f"    source_cfx = {lua_string(source_cfx)},",
                f"    model_name = {lua_string(variant_id)},",
                "    frequency_hz = [[1000000000]],",
                "    parameters = {",
                *parameter_lines,
                "    },",
                "}",
                "",
            ]
        )
        config_path = variant_dir / "variant_config.lua"
        config_path.write_text(config, encoding="utf-8")
        launcher = "\n".join(
            [
                f"VARIANT_CONFIG_PATH = {lua_string(config_path)}",
                f"dofile({lua_string(prepare_lua)})",
                "",
            ]
        )
        (variant_dir / "prepare_variant_run.lua").write_text(launcher, encoding="utf-8")

    print(f"Configured {len(plan)} variants under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
