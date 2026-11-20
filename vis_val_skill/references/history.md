# 历史实例索引

只作定位线索。复现前仍核对当前文件、checkpoint、日志和远程状态；以下固定数值不是新任务默认值。

| 实例 | 已有入口与产物 |
| --- | --- |
| 全角度 V7 | `export_allangle_visualization.py` 默认 `checkpoints/case1_1ghz_bestV7_eta_all.pt`，在 `visualization/allangle_export/` 产六份 `.npz` 与 `summary.json`；`visualization/generate_allangle_viewer.py` 产 JS，`visualization/allangle/index.html` 为页面。每几何 17×37 RCS、三个电流方向 (25°,25°)、(55°,95°)、(75°,145°)。 |
| 多变体 V7comb | `trainV7A.py`、`checkpoints/case1_1ghz_bestV7_eta_comb.pt`；`datasetXVXA.pt` 3420 样本训练，`datasetVVVA.pt` 和 `datasetVVCA.pt` 各 270 验证选参。`VVCA` 的 C 角已参与当前模型选模。 |
| 新几何观察 | `caseSLICY`、`casefeiji`、`case_single` 各自导出；`combine_v7comb_viewer.py` 汇集到 `visualization/v7comb_variants/`。SLICY 二次反射是 `caseSLICY/duoci/farfield_summary.json` 的 FEKO 原生远场；`single` 来源 JS 曾以 `feiji` 作内部键，组合脚本会重键。 |
| 记录与发布 | `record.md` 现有消融 13–16、全角度 17–19、多变体 20；`Weekly Journal.md` 按日期成节。门户 `up2github/` 与各站点 `up2github_split/` 分开；现场查 `.git` 和远程。 |

全角度旧训练每几何 171 训练方向、24 验证方向，余下角度不能自动称独立 test。旧多变体五族的几何 X=01–12、V=13–15、C=16–20；角度 X 为 θ∈{35°,45°,55°}、φ=0°:10°:180°，V 为 θ∈{40°,50°}、φ=5°:10°:85°，C 为同 θ、φ=95°:10°:175°。这只是历史划分，不是新数据的通用 schema。

现有 Variant 的 `slicy_data.js` 约 83 MB，涉及 GitHub 文件限制和浏览器加载。旧 `build_up2github.py` 的 `main()` 会重写门户 `up2github/index.html`，不能在只改 Record/周志时无检查地运行。
