---
name: po2mom-vis-validation
description: Validate PO-to-MoM checkpoints and datasets, document numbered experiment results, create current/RCS visualizations, and prepare or publish this project's GitHub Pages. Use for a new evaluation or reproducing existing evidence; exclude FEKO dataset production and model training.
---

# PO→MoM 验证、可视化与发布

以 `PO2MoM_TF` 为项目根目录。先判断请求属于“开始一个新任务”还是“复现/查询历史工作”；不把旧实验的角度网格、几何数、checkpoint、仓库地址或结论套用到新任务。`record.md` 是实验结果记录，`Weekly Journal.md` 是按日期的周志。工作站导出、本地 HTML、上传准备包、Git checkout 和已发布 Pages 分别核实。

## 开始一个新任务

读 [references/new-task.md](references/new-task.md)，从用户给定或实际文件中确定 checkpoint、dataset、几何、方向清单、划分和目标产物；缺少的数据标为待确认。先按 [references/validation.md](references/validation.md) 评估，再按 [references/record.md](references/record.md) 更新编号与证据。若要网页，按 [references/visualization.md](references/visualization.md) 导出、构建、验收；用户授权上传时再按 [references/publishing.md](references/publishing.md) 处理。每一环只运行任务必要部分，保留原始输入和可复算的汇总。

## 复现/查询历史工作

读 [references/history.md](references/history.md) 找到对应旧实验、脚本和产物，再核对当前文件及元数据。复现计算时仍按 [references/validation.md](references/validation.md) 检查口径；涉及网页或发布时再读对应参考文件。旧聊天或旧仓库状态只能作线索，不能替代现场核验。若仅查询，不修改记录或网站。

## 跨任务契约

同一批比较须固定几何、频率/极化、入射/观察方向、MoM 参照、复电流定义与 RCS 来源；记录 loss、样本级电流相对 error、PO baseline 和 RCS RMSE 的不同单位与汇总方式。验证选模用过的组合不再冒充独立封存测试。失败实验、模型比 PO 更差的样本和 FEKO 原生远场与电流积分估算的口径差异照实呈现。图的电流着色如为 `||Re J||₂`，不能写成复电流幅值。

本 Skill 只含流程和项目索引，不含模型、数据或凭据。训练/FEKO 等高成本任务以及发布、删除、覆盖旧站点，都以用户实际授权范围为准。
