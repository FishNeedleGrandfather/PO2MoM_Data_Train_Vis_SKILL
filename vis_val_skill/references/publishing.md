# GitHub Pages 发布交接

发布前确认用户要更新的仓库、文件范围及对现有内容的影响。项目门户是 `visual`，其本地 Git 仓库为 `up2github/`，线上入口 `https://fishneedlegrandfather.github.io/visual/`。Record、Weekly Journal、V6、V7、V7 AllAngle、Variant 为独立站点；以现场 `git remote -v`、仓库 Pages 设置和线上链接为准，不从门户文字推断是否已经部署。

当前可核实的本地 Git checkout 包括 `up2github_split/visual-record-checkout`、`visual-weekly-journal-checkout`、`visual-v7-AllAngle`、`visual-v7-Variant-checkout`。`up2github_split/visual-record`、`visual-weekly-journal`、`visual-v6`、`visual-v7` 等目录可能只是准备包。先 `git -C <目录> rev-parse --show-toplevel` 与 `remote -v`，不能直接对非 Git 目录推送。V6/V7 目标位置要重新查找对应 checkout 或安全克隆。

## 准备与推送

1. 查目标仓库的 `remote -v`、`status --short --branch`、`log -1` 和远程 `main`。识别用户已有未提交修改，先比对，不能覆盖。检查仓库 Pages 来源是分支根目录、`/docs` 还是 Actions；检查大小及 HTML 的 JS/图片相对引用。GitHub 普通文件上限 100 MB，超过或接近时先处理资源体积；浏览器性能也独立核对。
2. 只在目标 checkout 中同步被页面实际引用的静态文件。`build_up2github.py` 的 `main()` 会重写门户 `up2github/index.html` 并拷贝旧页面等资源；门户有手工调整时，先检查脚本差异，不盲目运行。Record/周志可调用其中 `render_document` 定向生成各自 `index.html`，但先比对生成结果是否保留侧栏和“返回首页”。
3. 在提交前核对 `git diff --check`、`git diff --stat`、`git status` 和实际 HTML/资源；明确新增、替换、删除的文件，排除 `.pt`、`.npz`、checkpoint、原始仿真结果。提交时使用已配置身份，`git push origin main` 到核实的远程；网络代理只按当前环境设置，不写入仓库或全局 Git 配置。
4. 推送后验证本地 `HEAD` 与远程分支、GitHub Actions/Pages 的对应 commit 与最终部署结果，再请求实际 Pages URL 和关键 JS/图片的 HTTP 响应并打开页面。构建成功不代表部署成功；失败时查看具体 workflow 步骤与日志，修复后只重推相关文件。远程仓库出现文件不等于网站已经刷新。

若用户只要求本地修改，就停在本地页面与准备包；若明确要求上传，完成推送和部署核验。任何删除旧 V6/V7 展示、更换仓库/Pages 来源或强推都需明确任务依据。记录最终 URL、commit、Pages 状态和未能验证的事项。
