# 可视化数据、布局与验收

从项目根目录定位输入和输出。先读取 [new-task.md](new-task.md) 的方向清单，选择与实际数据匹配的展示方式；历史页面及路径仅见 [history.md](history.md)。

## 导出契约

- 导出前核实 checkpoint 可加载，模型与 dataset 的归一化/特征一致，三角元网格、中心和边索引顺序一致；方向键唯一。保留每个方向的 θ/φ、train/val/test/未使用标签、PO/MoM/预测电流、RCS 值及来源、checkpoint epoch 和频率/极化元数据。若只有稀疏点，使用方向记录；只有实际完整矩形网格才存成 `rcs_db[3,theta,phi]`。
- 现有 `export_allangle_visualization.py` 硬编码六几何、629 个方向和三个电流方向，适合对应旧任务，不是任意新 case 的即用导出器。新任务需参数化或建专用导出器，并为不匹配的方向/网格报错，不静默填充。
- `visualization/generate_allangle_viewer.py` 当前只写 JS，假定六几何、三电流方向和矩形 RCS；其 `visualization/allangle/index.html` 要另核对。`visualization/index.html`、`index_v7.html` 是不同旧页面。新几何或稀疏方向须改生成器与 HTML 两侧的数据 schema，或做独立页面。

## 页面与图层

- 按实际方向选择电流、RCS 布局：同 θ 的 φ 扫描可绘曲线；多 θ 稀疏方向用列表或 θ/φ 散点，不跨 θ 连伪连续曲线。每点标用途和来源；未使用方向不出现在误差计算中。页面着色 `||Re J||₂` 与完整复电流 error 分开标注，FEKO 原生远场与电流积分曲线分开标注。
- 聚类 G1/G2、几何边、耦合边应从对应几何 dataset 导出；核对三角元总数、簇成员和边索引范围、实际网格配准。若合并旧页面 JS，检查内部键与 case 标签一致，避免把不同几何当成同一个模型。
- 页面需要的每份 JS/图片都必须被 HTML 正确以相对路径引用。检查角度切换、电流模式、RCS 图例、聚类与边层、默认状态，以及键盘/窗口缩放后的可用性。

## 浏览器与性能

静态文件只放网页运行所需 HTML/JS/图片和必要 `.nojekyll`；`.npz`、`.pt`、checkpoint、原始电流/仿真文件留本地。检查引用路径、单文件与整页大小、浏览器加载、交互帧率和内存；大几何 JS 尤须实测。上线后分别请求页面和关键资源、在实际网页操作确认。现有大文件实例见 [history.md](history.md)。
