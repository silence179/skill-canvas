# 完整 skill 文件夹版 UML v2

按完整目录重新提炼五个任务的 13 个 skill，渲染 PNG 和 SVG。入口：[图像索引](FIGURES.md)、[来源与语义复核](SOURCE_REVIEW.md)。

读取范围包含全部 16 个本地源文件：13 份 SKILL.md、DC 潮流 Python 脚本、经济调度成本函数参考，以及制造 skills 根目录的共享 reference.md。cache-policy-comparison 显式引用的兄弟 prefix-cache-replay 也完整纳入。其余 skill 目录没有额外资源，不把不存在的文件当作遗漏。

每个任务目录提供：

- `source/`：完整原始 skills 树的逐字节副本，含共享文件。
- `source-map.json`：图中 S1/S2 对应文件、哈希、行数、标题与脚本接口、提炼说明。
- `diagrams/`、`previews/`：新 UML、PNG、SVG。
- `bundles/{text,image}/`：保留全部原始资源与完整 GUIDE.md 的两组材料；图片包每个 skill 另有 assets/flowchart.png。UML 源码和来源说明放在包外。

新版重点补入脚本的输入/输出与边界行为、成本参考中的分段线性格式，以及共享参考中的 baseline repair 目标。所有图重做语义复核；例如积分控制明确区分时间步更新与试验后的调参。原资料的公式/启发式冲突会标明，不根据旧评分结果暗中补写答案。

```bash
python3 experiments/uml-expanded/full-skill-v2/build.py
python3 experiments/uml-expanded/full-skill-v2/build.py --check
```

使用已固定版本的本地 PlantUML 渲染，不调用图片生成模型。manifest 已存在时只做校验，不覆盖冻结材料。

这是看过旧结果后的材料修订，不是独立盲测结果。旧 UML、bundle、轨迹和评分均保留原样。已通过 10 种输入的本地 HTTP 传递检查，并完成新版十次对照。新入口为本目录 campaign.py / delivery.py，沿用旧版传递协议、公共 OpenCode、任务时限与评分。结果见 jobs/uml-expanded/paired-five-full-skill-v2/；旧运行入口仍绑定旧版材料。

最新结果：文字组通过 4/5、图片组通过 3/5；考试两组均超时，R2R 图片组性能测试未过。详见 [结果解释](../../../jobs/uml-expanded/paired-five-full-skill-v2/RUN_NOTES.md) 与 [轨迹索引](../../../jobs/uml-expanded/paired-five-full-skill-v2/TRACE_INDEX.md)。23 项材料/传递/源文件/输入检查通过，任务容器均已清理。每组一次，不能认定图像有稳定收益。

在 Slurm 上复跑时，`experiments/slurm.py uml-v2` 为每题生成一个文字试跑和一个图像试跑，沿用这里的直接输入协议。准备好相同的任务副本和每题一个 SIF 后，可以用下面的命令生成计划：

```bash
python3 experiments/slurm.py uml-v2 --partition main --nodelist kt-fat \
  --max-parallel 10 --tasks-root /path/to/prepared-tasks \
  --images-dir /path/to/sifs
```

不加 `--submit` 只生成计划。正式提交前在服务器项目根目录的 `.env` 填写 `DEEPSEEK_API_KEY`。默认模型是此前使用的 `deepseek/deepseek-flash`，两组都用 OpenCode；两组共用每题的 SIF，各有独立结果目录。计划不保存密钥。

要跨题复用旧实验的 OpenCode 工具层，从旧公共工具镜像提取 `/payload/tools.tar`，连同匹配的 `.runtime/shared-opencode/image.json` 保存到同一目录。为每题构建 SIF 时给 `experiments/images.py` 加 `--agent opencode --opencode-tools <目录>`。构建会核对归档、内容和工具版本；各题使用同一份 OpenCode 与 Node，同时保留自己的任务环境。
