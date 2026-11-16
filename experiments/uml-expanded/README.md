# 五个新增任务的 UML 辅助 skill 对照

**完整目录版 v2 已重新生成：** [13 张新版图](full-skill-v2/FIGURES.md)、[完整来源与语义复核](full-skill-v2/SOURCE_REVIEW.md)、[新版材料说明](full-skill-v2/README.md)。覆盖五个完整 skills 树的全部 16 个本地文件，包含脚本、参考及共享资源。新版独立存放，模型对照单独登记在 [v2 实验目录](../../jobs/uml-expanded/paired-five-full-skill-v2/comparison.md)；下文旧实验数据仍对应 v1。

已于 2026-11-15 完成全部对照尝试，详见 [最终结果](results/paired-five-v1-recovery.md)。两组均通过 4/5：制造任务文字 0、图片 1；考试任务文字 1、图片超时 0。其余三任务均通过。包含超时的已记录总 token 为 4,247,030→5,258,823（+23.8%），仅完整四个配对为 +39.0%。每组每任务仅一次，尚不支持稳定增益结论。

沿用晶体任务的 `forced-prefix-v1`：每次任务模型请求均由 harness 直接加入完整 skill 原文；图片组在全文前加入该任务所有 skill 的 PNG。图片不依赖 Agent 自行调用读图工具。标题等已识别辅助线程豁免。

| 任务 | Skill / PNG 数 | 图中重点 |
|---|---:|---|
| llm-prefix-cache-replay | 2 | 请求到达前的前缀命中、S/M/G 队列、频率与 second-chance |
| energy-market-pricing | 4 | 网络映射、DC 约束、成本/备用、对偶价格与反事实分析 |
| r2r-mpc-control | 4 | 线性化、有限时域递推、积分补偿、控制参数权衡 |
| exam-block-sequencing | 2 | 有序窗口、重叠逻辑、MIP 求解和最终文件审计 |
| manufacturing-fjsp-optimization | 1 | 前序顺序、停机冲突、逐整数搜索和修改预算 |

每个 skill 一张图，共 13 张。图依据原 `SKILL.md` 提炼，不使用 oracle 或 verifier 的内容。先冻结图和 bundle，再做参考解环境验证和正式对照；诊断时读取官方参考解/评分日志不会用于修改图。参考解和评分测试断言保持原样；制造任务另有下述依赖启动适配。

本实验两组均保留全部原始配套文件；`GUIDE.md` 是原始 `SKILL.md` 的逐字节副本。text/image 仅在入口说明和 PNG 上不同，其他资源一致。保留了源根目录的辅助文件。UML/SVG 源文件放在 bundle 外，Agent 不会额外得到图的文本源代码。

文件位于 `tasks/<task>/`：

- `diagrams/`：可编辑 PlantUML 活动图。
- `previews/`：PNG 与 SVG，便于查看。
- `bundles/{text,image}/`：配套 skill 原文与资源。
- `manifest.json`：源提交、原文/资源、UML、PNG 和两组 bundle 哈希。

准备与验证：

```bash
python3 experiments/uml-expanded/build_diagrams.py
python3 experiments/uml-expanded/study.py
python3 experiments/uml-expanded/study.py --check
```

首次准备已完成。已有 manifest 时 `study.py` 做验证，不会静默覆盖已冻结的材料。

正式计划为每任务 text/image 各 1 次，共 10 次，OpenCode + `.env` 中配置的同一路由模型，串行，按任务交替组别先后顺序。两组都使用公共 OpenCode 镜像。campaign 在首个正式模型任务之前记录时间、任务与代码哈希、工具镜像、参数、顺序和官方参考解健康状态；凭证不写入清单。

首次原始环境检查暴露了 PyPI 连接重置、评分依赖缺失和构建超过 600 秒的问题，失败记录保留在 `jobs/uml-expanded/environment-controls/` 和 `environment-controls-diagnostic/`，不作为模型失败。为隔离这些安装问题，`prepare_environments.py` 在 `.runtime/uml-expanded/prepared-tasks/` 建立任务副本，仅在 Dockerfile 追加原任务/评分所需依赖的预安装与 wheel 缓存。题目、数据、skill、oracle 和评分测试断言逐文件保持原样；制造任务评分启动脚本的后续适配见文末。CVXPY 1.4.2 在 Python 3.12 下从源码构建同版本 wheel。临时构建代理在构建完成后关闭，不写入运行容器；未修改 Docker 服务配置。正式两组都使用相同的准备后环境，不与此前晶体任务结果混合统计。

参考解复核使用 `environment-controls-prepared/`；每项正式结果同时记录实际 task digest、源材料、环境准备清单和公共工具镜像。构建脚本能从固定上游源重新生成这些实验副本：

```bash
repos/benchflow/.venv/bin/python experiments/uml-expanded/prepare_environments.py
```

```bash
repos/benchflow/.venv/bin/python experiments/uml-expanded/campaign.py run \
  --campaign jobs/uml-expanded/paired-five-v1
```

每次运行结束校验所有任务模型请求的图片数、全文、顺序和哈希。只接收到图不能证明模型实际利用了图。正式结果、逐任务日志、完整轨迹、评分、计量证据和对比报告均留在 campaign 目录；失败与缺失行也保留。

本轮是小样本探索。图同时增加了由 LLM 提炼的流程信息，不能直接把结果归因于图像形式；后续需要重复试验，并加入“同样提炼内容以文字提供”的第三组，才能区分总结与视觉形式的作用。较短 skill 也纳入本轮，以观察增加图片是否反而提高开销。

## 制造任务的预先环境修订

制造任务的原评分启动脚本会先执行 apt 更新并在线安装 uv 0.9.7，已观察到这部分超过 450 秒，固定安装链接也下载失败。在该任务首次模型试验前，单独登记了两项修订：保留签名 apt 索引并预热同版本 uv 测试缓存；将 `verifier/test.sh` 的依赖启动部分替换为同版本校验及离线缓存使用。**从创建日志目录开始的原评分脚本尾部（包括测试命令、reward 分支）逐字节一致，`test_outputs.py` 的全部断言和阈值也逐字节一致。** 因此此任务不能描述为“整个评分脚本未改”，应准确描述为“仅适配依赖启动，评分测试不变”。其余四个任务的评分脚本保持原样。

修订文件及前后哈希：campaign 中的 `manufacturing-environment-amendment.json`、`manufacturing-bootstrap-amendment.json`、`manufacturing-amended-files.json`。这两项修订都发生在制造任务两组模型槽位仍为 planned 时；两组使用相同修订。适配后官方参考解 reward=1；空输出控制 reward=0，实际执行测试后按预期拒绝无解提交。新增缓存准备和适配脚本只用于未开始的新试验；已经冻结并执行的 campaign 不应重新运行环境准备命令。

## 连接故障补跑与评分执行核查

首轮 `paired-five-v1` 的考试两组遇到模型接口连接重置，制造文字组也包含失败请求。已在制造图片组出分前登记一次完整配对补跑：`paired-five-v1-recovery` 只重跑考试、制造各两组，其余六次直接引用原始记录。按基础设施错误选择，所有原始尝试保留，不按得分挑选结果，也不将引用或补跑当成额外独立重复。

之后制造图片组暴露另一问题：评分依赖仍尝试访问 PyPI，超时后原脚本写出 reward=0，实际没有执行测试。原始 0 分不改写，派生分析会要求 CTRF 中存在实际测试执行，缺少证据的行排除于能力和 token 配对。制造两组补跑启动前，再登记 `manufacturing-offline-recovery-amendment.json`，仅在依赖启动中给 uvx 添加命令行级离线及本地 wheel 参数；原评分尾部与 Python 断言仍逐字节一致。新参考解 15 项通过、空输出 15 项实际执行并拒绝，控制记录绑定新 task digest。原登记和这项范围明确的修订分别保留。

独立的 [仅图片识读检查](results/vision-sanity.json) 使用同一路由，只给两张 PNG，没有原文。三个节点/注释/出口位置的文字问题全部答对。这验证基本识图能力，不计入 benchmark，也不能代替任务效果对照。
