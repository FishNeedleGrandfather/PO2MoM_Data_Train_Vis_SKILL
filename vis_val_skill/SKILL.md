---
name: po2mom-vis-validation
description: Validate PO-to-MoM experiment results, maintain numbered record and weekly evidence, build current/RCS viewers, and stage or publish this project's GitHub Pages sites. Use for evaluation, visualization, experiment documentation, and website handoff; exclude FEKO dataset production and model training.
---

# PO→MoM 验证、可视化与发布

先定位项目根目录 `PO2MoM_TF`，核对当前数据、checkpoint、生成脚本和目标仓库状态。`record.md` 是实验指标的主要文字记录，`Weekly Journal.md` 是按日期组织的周志。不要从文件名或旧对话推断结果已经发布；工作站导出、本地页面、上传准备目录、Git 仓库和线上 Pages 各自检查。

按当前任务读取对应参考文件：

- 评估 checkpoint、划分、指标和新数据泛化：读 [references/validation.md](references/validation.md)。
- 新增记录、曲线、图注或周志：读 [references/record.md](references/record.md)。
- 生成或修改全角度、Variant、SLICY 等网页：读 [references/visualization.md](references/visualization.md)。
- 整理上传包、提交、推送或核验 GitHub Pages：读 [references/publishing.md](references/publishing.md)。

若任务跨多个环节，按依赖顺序读取相关参考文件；先确定数据来源和误差口径，再制作图表和网页，最后发布。测试集若参与过 checkpoint 选择、阈值或展示方案的反复调参，记录实际用途，不能再称为独立最终测试。发现误差变差、训练失效、曲线缺失或不同远场口径，也如实保留。不要把未经验证的 `.pt`、`.npz` 或模型输出称作 FEKO 原生远场。

本 Skill 仅提供流程和口径，不包含数据、凭据、模型或上传授权。执行高成本 FEKO/训练、删除远程内容、覆盖其他展示或变更仓库目标时，以用户本次任务范围为准。
