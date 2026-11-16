# UML 流程图辅助读取 skill：单任务对照

任务：crystallographic-wyckoff-position-analysis（晶体结构 Wyckoff 位置分析）。

这是官方标为 medium 的计算任务，要求从 CIF 文件分析位置重数和代表坐标。它适合这次尝试的原因是两个 skill 的说明较长、包含选择路径和参考资料；并非宣称它是全套 benchmark 最难的任务。

## 已准备的两个版本

| 版本 | harness 强制提供的输入顺序 | skills 根目录 |
| --- | --- | --- |
| text | 两份完整 GUIDE.md → 原始任务 | bundles/text/ |
| image | 两张 PNG 图像 → 相同的两份完整 GUIDE.md → 原始任务 | bundles/image/ |

两个 skill 都已处理：pymatgen、sympy。图像组各有一张由 PlantUML 活动图源码渲染的 PNG，位于每个 skill 的 assets/flowchart.png。

两组保留相同的 name/description/元数据、原文、脚本和参考资料。原 SKILL.md 逐字节保存为同目录的 GUIDE.md，保持原文中 references/ 和 scripts/ 相对路径有效。入口改为短的读取顺序指引，避免 agent 第一次打开 SKILL.md 时就已经读完全文，导致无法观察“先图后文”。没有修改上游任务提示、数据、参考解法或评分器。

当前入口使用 `forced-prefix-v1`：实验专用适配器在 BenchFlow 的模型网关内，为每次 Agent 请求提供固定的 skill 输入。加图组的 PNG 通过真正的 `image_url` 数据块传递，不是路径、OCR 或 UML 源码；全部图片位于全文之前，两组的全文逐字相同，原始任务内容保持不变。模型无需主动调用 skill/read 工具也能收到这些材料。这保证输入传递，不能保证模型的注意力或使用效果。

两个 bundles 保留先前的文件布局与入口指引，不触发无关的任务镜像变更；新的传递约束由宿主侧适配器执行。宿主适配器复用框架的原有路由、预算与日志检查，不修改 BenchFlow、SkillsBench 源码或评分器。

流程图由本次助手基于现有 skill 说明提炼后编写为 PlantUML，使用本地固定版本渲染；未调用另一个模型服务生成图，也没有新增学习或训练过程。

## 查看流程图

- pymatgen：previews/pymatgen.png；可缩放版本 previews/pymatgen.svg。
- sympy：previews/sympy.png；可缩放版本 previews/sympy.svg。
- 可编辑 UML 源码：diagrams/pymatgen.puml、diagrams/sympy.puml。

UML/SVG 源码与预览放在挂载的 skills 根目录之外；agent 的图像组只获得 PNG 和相同原文资源，避免读了 UML 文字源码后被误记为读图。

图像使用英语，与原 skill 语言一致。它们是原 skill 部分核心流程的摘要和导航，没有试图将整套 API 文档压进一张图。pymatgen 的 Wyckoff 路径来自原本就存在的 references/wyckoff-positions-from-cif.md；不来自评分器或参考解法。sympy 的流程来自原文的精确算术、解算器选择、Solve and Verify、Symbolic to Numeric Pipeline 和 Troubleshooting。

## 跑一次对照

在工作区根目录执行：

    cd /home/silence/myfiles/SkillCanvas
    python3 experiments/uml-flowchart/prepare.py --check

已在工作区根目录创建 .env，并提供 .env.example 模板。打开 .env，填写 DEEPSEEK_API_KEY= 后面的值即可。默认已配置：

    DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
    EXP_AGENT=opencode
    EXP_MODEL=deepseek/deepseek-flash

模型名和视觉能力按 DeepSeek 官方说明确认：deepseek-flash 当前提供 V4.1 Flash 系列的多模态服务。资料：https://api-docs.deepseek.com/quick_start/pricing/

两个入口会自动读取根目录 .env，无需手工 source。实际运行时 key 留空会在启动环境前提示；dry-run 不需要 key。优先级是命令行参数 > 已有终端环境变量 > .env 中的默认值。直接调用 BenchFlow CLI 不使用我们入口的 .env 加载功能。

.env 支持每行 KEY=value、可选引号和注释，不执行 shell 命令或展开变量；含空格或 # 的值请加引号。.env 已被 Git 忽略，创建时文件权限为 600；.env.example 不含密钥。

先预览配置，dry-run 不调用模型：

    python3 experiments/uml-flowchart/run.py text --dry-run
    python3 experiments/uml-flowchart/run.py image --dry-run

实际各跑一次：

    python3 experiments/uml-flowchart/run.py text
    python3 experiments/uml-flowchart/run.py image

首次强制输入对照已经完成，见 [结果报告](results/2026-11-14-forced-v1-180854-185918.md)。两组均得分 1，传递校验通过；加图组 7 次任务请求每次均包含两张 PNG。

运行中修正过事后审计对框架日志脱敏的兼容性，原 text 目录保留旧入口 policy。后续重新实验请使用新的两组目录，避免 policy 检查拒绝混用：

    python3 experiments/uml-flowchart/run.py text --fresh --jobs-dir jobs/uml-flowchart/forced-v1-next/text
    python3 experiments/uml-flowchart/run.py image --fresh --jobs-dir jobs/uml-flowchart/forced-v1-next/image

首次启动时，`sandbox creating` 也包含 OpenCode 的安装，不只是任务容器创建。即使 oracle 已通过，模型组仍需首次下载 Node 和 OpenCode；OpenCode 的 Linux 二进制解压后约 214 MB，且安装器还会下载兼容版本。安装阶段可能数分钟没有终端输出；是否卡住需结合 Docker 构建日志判断。两组的 skill 文件不同，安装层也可能需要分别构建，不能据此承诺第二组立即启动。

EXP_EFFORT 目前留空，沿用 agent/模型默认设置；如果需要指定支持的推理档位，在 .env 中填写 EXP_EFFORT，或为两组都追加相同的 --effort 参数。模型可用 --model 显式覆盖；当前强制传递适配器仅支持 OpenCode 和 Chat Completions 路由。初次观察之后，可在两个命令中都追加 --trials 3，并使用新的 --jobs-dir，或 --fresh 开新实验。默认每组 1 次、并发 1；入口传入 --retry-attempts 0。同一目录默认续跑，重做时要区分已有结果。

查看两组结果：

    repos/benchflow/.venv/bin/bench results jobs/uml-flowchart/forced-v1/text jobs/uml-flowchart/forced-v1/image

新结果默认位于 `jobs/uml-flowchart/forced-v1/{text,image}`，不会覆盖旧实验。每个 trial 都会生成 `skill-delivery.json`，只有其中 `valid=true` 才可纳入该对照；图片缺失、内容或顺序不符、模型请求捕获不完整时，入口返回非零状态并显示 `INVALID`。原始评分不被改写，不能仅凭 reward 判断图像条件有效。目录内的 policy 记录输入及适配器源码哈希；更改输入或适配器后需换新目录。标题、摘要线程按固定 OpenCode 特征识别，不作为任务读图步骤。

oracle/nop 仍用原任务检查：

    python3 experiments/run.py oracle --task crystallographic-wyckoff-position-analysis
    python3 experiments/run.py nop --task crystallographic-wyckoff-position-analysis

## 如何判断这次对照有没有意义

除了结果分数、耗时和用量，重点检查：

1. 每个 trial 的 skill-delivery.json 是否 valid=true，并与该组 policy ID 对应。
2. 图像组的每个 Agent 模型请求是否含有两张 PNG 的真实 image_url 数据块，且哈希与当前图像一致。
3. 两张图像是否位于完整 GUIDE.md 之前；两组全文是否相同。
4. 不再以 skill 工具调用次数或 read 文件次数作为加载成功的证据；输入由 harness 提供，直接核对模型请求。任何传递失败均不能回退为有效纯文本尝试。
5. 比较完整任务用量，包含图像输入和后续上下文成本。

如果模型或 agent 无法读图，本实验没有实际施加图像条件；不要把它当作图像无效。仅一次成败也不能证明模型认知增强或统计显著。

本对照测量“新增流程图摘要并先看图”带来的整体影响。由于图像提炼了原文内容，若要单独证明视觉模态的作用，后续还需要同内容的文字摘要对照。

## 当前验证状态

旧版两组均完成并得分 1，但加图组没有向模型传入图像，因此不能用于判断图像增益。原始结果保留在 jobs/uml-flowchart/text/2026-11-14__15-15-34 和 jobs/uml-flowchart/image/2026-11-14__15-45-45。

forced-prefix-v1 已通过 10 项传递检查、既有 .env 的 5 项测试、两组 dry-run，以及使用真正 LiteLLM 转换链路的本地接口检查（确认实际 HTTP 请求包含两图与全文）。另用当前 DeepSeek 凭证做了两次限输出的小请求（修正代理对象复制兼容性后再验证一次），接口均接受了两图和全文，返回 OK；证据在 .runtime/uml-delivery/live-provider-smoke.json。

首次完整新对照已完成：text 为 19 次工具调用、491,396 token、Agent 执行 64.6 秒；image 为 8 次工具调用、161,328 token、Agent 执行 15.7 秒。两组全部 11 个评分测试通过，传递检查通过。原始结果在 jobs/uml-flowchart/forced-v1/，脱敏误报的原始与修正审计均保留；完整方法、证据哈希与局限见结果报告。单次观察不能证明模型认知增强，也不能分离视觉与图中摘要内容的作用。

前次运行遇到 Docker Hub 基础镜像拉取和 Python 包下载超时，已通过官方镜像导入及原始 Dockerfile 预构建处理。本机该任务的 oracle 已通过（reward=1、errors=0），OpenCode 的模型调用已在纯文本组验证。首次模型环境准备约 11 分钟，Agent 实际执行约 52 秒；本次 OpenCode 安装层已缓存，相同环境可复用。需要重新实验时使用 `--fresh` 新建运行；该参数不会要求清空环境缓存。迁移机器后仍需重新准备 Docker 环境。参见 ../STATUS.md。

## 修改 UML 后重新渲染

    python3 experiments/uml-flowchart/prepare.py --rebuild
    python3 experiments/uml-flowchart/prepare.py --check

重建会重新生成本目录的 bundles/、previews/ 和 manifest.json；不要将手工修改仅保存在这些生成文件里。

渲染器为 PlantUML MIT 1.2026.10，位于工作区 .runtime/plantuml/plantuml-mit-1.2026.10.jar。版本、下载地址、SHA256、上游提交以及两组每个文件的哈希均记录在 manifest.json。已生成的图片无需 Java 即可使用；仅重新渲染需要 Java 和该 jar。

如果迁移后缺少 jar，从 manifest.json 中的官方地址下载到上述路径；prepare.py 会检查 SHA256 后才调用。运行准备脚本不需要模型凭证。
