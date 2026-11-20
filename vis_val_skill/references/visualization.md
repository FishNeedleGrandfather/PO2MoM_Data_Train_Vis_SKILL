# 可视化来源与检查

从项目根目录定位文件，检查脚本实际默认路径和输入版本；以下是当前路径示例，不等于所有文件已同步或已发布。

## 全角度

- 工作站入口 `export_allangle_visualization.py` 默认读取 `checkpoints/case1_1ghz_bestV7_eta_all.pt`、`simulation_smallbatch/datasets/dataset_case1to5_allangle_eta.pt` 和 `dataset_case_single_allangle_eta.pt`，输出到 `visualization/allangle_export/`：六份 `.npz` 与 `summary.json`。每几何 RCS 为 PO/MoM/预测 × 17 θ × 37 φ；另有 (25°,25°)、(55°,95°)、(75°,145°) 的三种复电流与网格。导出前验证 checkpoint 可加载、样本角度完整且不重复、网格三角元顺序与数据一致。
- 本地入口 `visualization/generate_allangle_viewer.py` 结合导出 `.npz` 与全角度 `.pt` 数据集，生成 `visualization/allangle/index.html` 所需六份 `*_data.js` 和 `coupling_data.js`。检查脚本是否也更新 HTML；该生成器当前只写 JS。`visualization/index.html` 与 `index_v7.html` 是旧页面，不是全角度入口。
- 页面电流图当前显示 `||Re J||_2`，相对误差使用完整复电流；17×37 RCS 来自电流积分估算。标出当前方向属于训练、验证或留出观察，角度标签须按实际划分生成，不把三张留出电流图称为全角度测试集的统计结果。

## V7comb Variant 和其他几何

- `combine_v7comb_viewer.py` 汇集 `visualization/slicy_comb`、`feiji_comb`、`single_comb` 的 JS 到 `visualization/v7comb_variants/`，并由 `caseSLICY/duoci/farfield_summary.json` 生成 SLICY 二次反射 JS。当前页面还包含 X/V/C 三个变体。`single` 来源文件曾使用 `feiji` 内部键，组合脚本有显式重键步骤；不要据旧键把 single 当成飞机。
- 修改前追溯各模型导出脚本、checkpoint 与样本角度。X/V/C 的页面标识必须说明几何组和角度组分别是什么；新几何如 SLICY、飞机、single 列为独立几何观察。聚类 G1/G2、几何边、耦合边和三角元索引来自相配的数据集，验证计数、范围和网格一致，避免图层看似能显示却错位。
- 页面需要可切换的 PO/MoM/预测电流、RCS、角度、聚类/耦合图层时，核对对应 JS 和 `index.html` 的全部 `<script src>`/图片引用。RCS 的 FEKO 原生曲线与积分估算曲线要注明来源。

## 浏览器与性能

静态文件只放网页运行所需 HTML/JS/图片和必要 `.nojekyll`；`.npz`、`.pt`、checkpoint、原始电流/仿真文件留本地。检查每个引用的相对路径、文件大小与浏览器加载；大的几何 JS 应实测加载时间、交互帧率和内存。当前 Variant 的 `slicy_data.js` 约 83 MB，尤其需检查 GitHub 单文件限制及用户端性能。至少打开本地页面验证默认几何、角度切换、电流颜色、RCS 图例和 G1/G2 边图层；上线后再核验线上页面与资源。
