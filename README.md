# SkillCanvas：SkillsBench 最小实验工作区

先把执行链路跑通，再用少量任务验证你的逻辑。统一实验入口已准备；已有“UML 流程图辅助读取 skill”的单任务对照，并扩展到五个新任务。

**后续图像实验使用[读取时附图协议](experiments/skill-read-on-demand/README.md)**：模型通过 `skill` 工具或文件／命令工具实际取得某个 `SKILL.md` 正文后，图片条件自动附上对应图。新入口为 `experiments/skill-read-on-demand/runner.py`，使用新结果目录，不在任务开始前强制注入所有 skill。[仅监听原生工具的 v1 两题四轮结果](jobs/skill-on-demand-v1/two-task-2026-11-16/ANALYSIS.md)全部零图片发送，保留用于诊断。[读取时附图 v2 的四轮实际结果](jobs/skill-read-on-demand-v2/two-task-2026-11-16/FINDINGS.md)已完成：R2R 两组均 6/6、图片组实际收到四图，token −55.6%；晶体两组均未读取 skill、均 6/11，没有发图。每配置一次，尚无稳定收益结论。下文历史强制输入实验保留用于复盘，不能当作新协议结果。

用户停止后续混合批次后，[v2.1 四题图片轮重跑](jobs/skill-read-on-demand-v2.1/image-only-four-2026-11-16/FINDINGS.md)已结束：前缀缓存、电力定价满分；制造排程 13/15，但因提前开工整体得分 0；考试超时未提交文件，得分 0。实际附图分别 1、4、1、2 张，累计 3,842,405 token，框架估算 $0.191076。考试日志中的候选经离线复算达标，原始失败得分仍保留。本批没有新文字对照，不能计算图片收益。新入口及已知原生工具失败回退见 [v2.1 说明](experiments/skill-read-on-demand-v2_1/README.md)。

五任务实验共 13 张 UML 流程图，现已结束全部对照尝试：文字/图片两组均通过 4/5，图片组考试任务超时；完整四个配对的 token 有增有减，尚无稳定增益。[五任务结果与原始证据](experiments/uml-expanded/results/paired-five-v1-recovery.md)、[实验说明](experiments/uml-expanded/README.md)、[所有图、UML 和原文](experiments/uml-expanded/FIGURES.md)。原始连接故障、补跑及评分依赖适配均单独保留。

按完整 skill 文件夹重新提炼的 [v2 新版 13 张流程图](experiments/uml-expanded/full-skill-v2/FIGURES.md) 已生成，覆盖全部本地脚本、子目录参考和共享参考。[来源复核](experiments/uml-expanded/full-skill-v2/SOURCE_REVIEW.md)。新版对照的状态与结果见 [v2 独立实验目录](jobs/uml-expanded/paired-five-full-skill-v2/comparison.md)；旧轨迹与评分保持原样。

已准备好的图像实验见 [UML 流程图对照说明](experiments/uml-flowchart/README.md)：选用晶体结构分析任务，pymatgen 和 sympy 各增加一张 PlantUML 渲染的流程图，并提供 text/image 两组独立 skill 包和运行入口。

本次实际验证与环境状态见 [`experiments/STATUS.md`](experiments/STATUS.md)：强制输入的首次完整对照已完成，两组均得分 1，传递检查通过；加图组每次任务请求均含两张 PNG。本次总 token 从 491,396 降为 161,328，仅代表单任务各一次的观察，不能据此证明图像增益。[完整对照报告](experiments/uml-flowchart/results/2026-11-14-forced-v1-180854-185918.md)。

## 已拉取的代码

| 路径 | 用途 |
| --- | --- |
| `repos/skillsbench` | 官方 benchmark：87 个默认任务、领域 skill、参考解法、自动评分器 |
| `repos/benchflow` | 当前默认执行基座：启动容器、安装 agent、部署 skill、调用模型、保存轨迹与评分 |
| `repos/harbor` | 早期 SkillsBench 相关评测基座，留作阅读、旧版实验参考 |

具体提交写在 `sources.lock.json`。这次是浅克隆；阅读和运行已有代码足够，需要研究历史时再补全。

当前 SkillsBench 主分支使用 `task.md + environment/ + oracle/ + verifier/`。
其 README 推荐最新 BenchFlow，但 pyproject/部分贡献说明仍约束 0.6.x。这次单独使用拉取的 BenchFlow 0.10.0rc3 源码环境和它自己的锁文件；不要在 SkillsBench 目录运行 `uv run bench` 后又与这套命令交替使用。这里的运行验证只代表所选任务，不表示 87 个任务均已兼容。

这里的“基座”指评测运行框架。模型通过 API 或 agent 登录调用；尚未下载任何模型权重，也未配置本地推理服务。

## 环境与入口

当前运行入口使用 **SingularityCE 4.1.1**，服务器通过 **Slurm 数组作业**并行。每个 trial 有独立可写环境、临时目录和结果目录，SIF 镜像提前构建、运行时复用。OpenCode 的固定安装配方也可提前装进 SIF。旧[公共 Docker 工具镜像](experiments/SHARED_OPENCODE.md)仅用于历史实验复盘。

所有下列命令均在当前机器自己的项目根目录执行。仓库位置可以不同；路径在运行或生成 Slurm 计划时确定。

根目录 `.env` 已创建，默认是 OpenCode + DeepSeek Flash；填写 `DEEPSEEK_API_KEY` 即可。`experiments/run.py` 和 UML 实验入口会自动加载它，支持用命令行参数覆盖 agent/模型，已有终端环境变量优先于 `.env`。`oracle`/`nop` 控制组不会套用模型默认值。模板为 `.env.example`，实际 `.env` 已被 Git 忽略。

后续图像实验先使用 `repos/benchflow/.venv/bin/python experiments/skill-read-on-demand/runner.py --task crystallographic-wyckoff-position-analysis --arm image --figures uml-v1 --dry-run` 离线预览。[读取时附图说明](experiments/skill-read-on-demand/README.md)列出文字／图片组入口。历史 `experiments/uml-flowchart/run.py` 保留用于复现强制输入实验。

```bash
# 首次拉取项目后：需要 git、uv，准备固定版本的上游源码与 Python 3.12 环境。
python3 experiments/setup.py

repos/benchflow/.venv/bin/bench --version
repos/benchflow/.venv/bin/bench tasks check repos/skillsbench/tasks/econ-detrending-correlation
```

模型运行前，在本机终端设置对应服务的环境变量，如 `ANTHROPIC_API_KEY`、`OPENAI_API_KEY` 或 `GEMINI_API_KEY`。无需把密钥贴进聊天或写入提交。本文的模型名称由你填入有权限使用的确切 ID；`--agent`、`--model`、`--effort` 在各实验组保持一致，effort 选该模型支持的最高档位。模型服务不支持 reasoning effort 时，删去命令中的 `--effort` 参数；此时沿用 agent 默认设置并在报告中注明。

`experiments/setup.py` 按 `sources.lock.json` 获取 SkillsBench 和 BenchFlow，安装本项目的 Singularity 后端，再用上游锁文件准备 Python 环境。更新项目后重跑此命令；它保留上游固定提交，不自动切换版本。已有依赖且只需更新适配代码时用 `--no-sync`。源码保存在忽略的 `repos/`，服务器不能只拉主仓库后跳过这一步。

服务器需为当前账号启用 `--fakeroot` 的 UID/GID 映射，以支持容器内用户创建、用户切换和属主修改。请在计算节点验证，不能仅凭 `singularity --version` 判断。[SingularityCE 4.1 fakeroot 说明](https://docs.sylabs.io/guides/4.1/user-guide/fakeroot.html)。

本机 Arch 可安装真正的 SingularityCE：`yay -S singularity-ce`。当前 AUR 包是 4.6.0，本地检查不能替代服务器 4.1.1 的实际验证。安装后运行 `singularity --version`；本项目不自动安装系统软件。

源码安装未包含 BenchFlow 的 `bfx` 二进制，会提示使用 Python 回退；所选任务镜像包含 Python。需要评测不带 Python 的镜像时，按上游说明构建 bfx 或安装带 bfx 的发行 wheel。

`experiments/run.py` 包装官方 CLI，不替换 agent 执行或评分逻辑。默认任务为 `econ-detrending-correlation`、1 次、并发 1、基础设施自动重试 0 次；实际运行会记录源码提交、工作区改动和完整命令到 `experiments/manifests/`。运行结果在 `jobs/<实验组>/`。

## 服务器：准备镜像，再提交 Slurm

代码通过 GitHub 同步。`.env`、`repos/`、`images/`、`.runtime/` 和 `jobs/` 不进入 Git；服务器需自行填写 `.env`，不能依赖本地忽略目录。首次使用可复制 `.env.example`，填写 API key；已有 `.env` 不要覆盖。

先预览原始 task 环境对应的 Singularity 配方，无下载、无构建：

```bash
python3 experiments/images.py --task llm-prefix-cache-replay --plan
```

服务器可以直接用 Singularity 构建，无需 Docker。示例通过 Slurm 分配计算资源后构建一个简单 task；按集群要求补上分区和账号：

```bash
srun --ntasks=1 --cpus-per-task=2 --mem=4G --time=00:30:00 \
  repos/benchflow/.venv/bin/python experiments/images.py \
  --task llm-prefix-cache-replay --agent opencode
```

默认从该 task 的 `environment/Dockerfile` 生成原生配方，基础镜像由 Singularity 从 OCI 仓库取得，`docker://` 不要求 Docker 服务。保留 RUN/COPY 顺序、ENV、WORKDIR 和启动入口；多阶段构建等未实现写法会拒绝转换，可通过 `--definition 路径.def --workdir /root` 指定原生配方。`--source` 用于已有完整任务镜像，不能用裸 Python 基础镜像代替任务环境。

构建输出为 `images/<task>.sif` 和同名 `.json`（哈希、配方、输入文件指纹与安装配方记录）。两者配套保留；运行会核对 SIF 与任务输入。默认镜像目录也可通过 `SKILLCANVAS_IMAGES` 或 `--images-dir` 改到共享磁盘。不要在 trial 内重复构建，重建时使用新的镜像目录。

本地已有 Docker 缓存时，可选择一次性导入，例如本机已有的约 216 MB 前缀缓存 task 镜像：

```bash
repos/benchflow/.venv/bin/python experiments/images.py \
  --task llm-prefix-cache-replay \
  --docker-image skillcanvas-expanded:llm-prefix-cache-replay
```

这条可选导入命令才会读取 Docker；服务器默认构建和任务运行均不使用 Docker。`--agent opencode` 会在构建时执行上游固定安装配方，后续 trial 通过配方标记复用。未缓存 agent 时仍沿用原生安装流程。

先提交单次 oracle 验证执行与评分，不调用模型：

```bash
# 只生成可检查的计划、commands.txt 和 array.sbatch，不调用 sbatch。
python3 experiments/slurm.py oracle --task llm-prefix-cache-replay \
  --trials 1 --max-parallel 1 --cpus 2 --mem 4G

# 真正提交，使用新的结果目录。
python3 experiments/slurm.py oracle --task llm-prefix-cache-replay \
  --trials 1 --max-parallel 1 --cpus 2 --mem 4G --submit
```

`--partition`、`--account`、`--time` 控制 Slurm 参数。一个数组元素只跑一个 task 的一次 trial，框架内部并发固定为 1。`--max-parallel 4` 限制同时占用最多四份 `--cpus`/`--mem` 资源。计划在服务器生成，代码、镜像、结果目录应位于计算节点可见的共享路径；临时可写环境优先使用节点的 `SLURM_TMPDIR`。

完整原始文字基线使用 `curated`；无 skill 使用 `baseline`。可重复指定 `--task` 或用 `--tasks-file` 传入每行一个 task ID 的文件。以下示例生成同一任务三次 trial 的计划；需要提交时再加 `--submit`：

```bash
python3 experiments/slurm.py curated --task llm-prefix-cache-replay \
  --trials 3 --max-parallel 2 --cpus 2 --mem 4G
```

`slurm.py text` / `image` 调用读取时附图 v2.1 入口，仅适用于已注册的六题，使用相同的独立 trial 布局；三十题原始文字条件使用 `curated`。

本后端共享计算节点的网络，不实现 Docker Compose、网络防火墙、GPU 或容器快照。BenchFlow 对这些能力的检查仍生效。模型运行默认也保留云元数据检查；如果集群已在节点侧控制相关访问，可以显式加 `--allow-cloud-metadata` 使用上游的该项退出选项。

`drone-planning-control` 与 `react-performance-debugging` 依赖 Compose 多服务，当前后端不支持，框架会拒绝启动，不能把它们记作模型失败。所选三十题中其余二十八题通过静态能力检查；这不代表实际环境已验收。

旧 campaign/pilot 脚本依赖本地历史计划、缓存与校验哈希，保留供复盘，不作为服务器提交入口。新任务使用 `slurm.py`、`run.py` 或对应的 read-on-demand runner，并使用新的结果目录。

本地已用 SingularityCE 4.6.0 从 Docker 缓存构建 SIF，并跑通 `llm-prefix-cache-replay` 的单次 `oracle`（得分 `1.0`，未调用模型）。服务器端直接构建 SIF 和通过 Slurm 执行仍待在 SingularityCE 4.1.1 上验证。

## 第一步：不用模型验证链路

```bash
python3 experiments/run.py oracle --task llm-prefix-cache-replay --dry-run
python3 experiments/run.py oracle --task llm-prefix-cache-replay --jobs-dir jobs/singularity-oracle
python3 experiments/run.py nop --task llm-prefix-cache-replay --jobs-dir jobs/singularity-nop
```

oracle 执行上游参考解法，应得 reward=1；nop 不做任务，应得 reward=0。先确认二者有完整的评分输出；镜像下载、依赖安装、容器或评分器错误都应单独修复。oracle 成功仅说明参考解法到评分器的链路可用，并不验证真实 agent 安装、模型鉴权或你的方法有效。

通用入口默认任务是经济时间序列去趋势（需先构建它的 SIF）；上面链路检查显式选择更小的前缀缓存回放任务。经济任务读取已有表格，算出相关系数。它便于检查结构化输出和评分流程；不能据此推断某类 skill 一定有效。

## 第二步：一个任务比较无 skill 和官方 skill

以下先设置你实际要用的 agent、模型和推理档位，例如 agent 可以是 `claude-agent-acp`、`codex-acp` 或 `gemini`：

```bash
export EXP_AGENT='claude-agent-acp'
export EXP_MODEL='填入你有权限使用的模型ID'
export EXP_EFFORT='填入模型支持的推理档位'

# 预览计划，不调用模型。
python3 experiments/run.py baseline --agent "$EXP_AGENT" --model "$EXP_MODEL" --effort "$EXP_EFFORT" --dry-run
python3 experiments/run.py curated --agent "$EXP_AGENT" --model "$EXP_MODEL" --effort "$EXP_EFFORT" --dry-run

# 真正执行：各 1 次，共 2 次模型任务。
python3 experiments/run.py baseline --agent "$EXP_AGENT" --model "$EXP_MODEL" --effort "$EXP_EFFORT"
python3 experiments/run.py curated --agent "$EXP_AGENT" --model "$EXP_MODEL" --effort "$EXP_EFFORT"

repos/benchflow/.venv/bin/bench results jobs/baseline jobs/curated
```

baseline 对应 `no-skill`；curated 让每个任务使用自己的 `environment/skills/`。任务提示、输入数据和评分器相同。挂载了 skill 不等于 agent 实际读取了它，需要结合工具调用轨迹确认。

相同命令默认续跑已有结果；想重做需指定新 `--jobs-dir jobs/新名称` 或加 `--fresh`。改变模型、算法或参数时使用新目录，避免混合结果。

当前 0.10.0rc3 的 dry-run 卡片可能把 `--retry-attempts 0` 显示成默认 2；实际启动的卡片与结果才用于核对配置，本入口明确传入 0。

## 第三步：接你的逻辑

如果你的方法最终输出一组 skill，先把完整 skill 包放在自己的目录：

```text
experiments/my-skills/
  some-skill/
    SKILL.md
    references/      # 如需
    scripts/         # 如需
```

```bash
python3 experiments/run.py custom \
  --skills-dir experiments/my-skills \
  --agent "$EXP_AGENT" --model "$EXP_MODEL" --effort "$EXP_EFFORT" \
  --jobs-dir jobs/my-method-v1

repos/benchflow/.venv/bin/bench results jobs/baseline jobs/my-method-v1
```

`--skills-dir` 是包含多个 skill 子目录的根目录。同一轮多任务时会给每个任务同一组自定义 skill；若你的算法按任务选择不同 skill，先逐任务运行、各用独立目录，随后再接 Python SDK 做批量调度。

建议先在工作区实现方法，保留上游任务和评分器。接入位置按方法选择：

| 方法改变什么 | 阅读入口 |
| --- | --- |
| 检索、排序、压缩、组合 skill | `repos/benchflow/src/benchflow/skills.py` 和 `skill_policy.py`；先在框架外输出自定义 skill 目录 |
| 执行前动态准备资源 | `repos/benchflow/src/benchflow/rollout/__init__.py` 的 `pre_agent_hooks`，以及 `docs/reference/python.md` |
| agent 循环、工具调用或路由 | `repos/benchflow/src/benchflow/agents/`、`agent_router.py`、`rollout/` |
| 阅读旧版 Harbor agent 接口 | `repos/harbor/src/harbor/agents/base.py`、`agents/installed/` |

## 第四步：小样本看效果

确认方法能跑后，再固定 3 个任务，每个任务每组 3 次；A/B/C 三组共 `3 × 3 × 3 = 27` 次模型任务。可以先用下列跨领域样本，正式比较前每个任务都跑 oracle 和 nop：

- `econ-detrending-correlation`：时间序列计算。
- `offer-letter-generator`：文档生成。
- `crystallographic-wyckoff-position-analysis`：晶体结构分析，依赖较重。

给每组命令追加：

```bash
--task econ-detrending-correlation \
--task offer-letter-generator \
--task crystallographic-wyckoff-position-analysis \
--trials 3 --concurrency 1 --jobs-dir jobs/该组的新目录
```

报告每个任务及总体的 pass rate、平均 reward、tokens、耗时、可用时的费用，以及实际 skill 读取情况。方法增益按同一任务的平均得分相减，再在任务间取平均。鉴权、网络、容器、评分器错误作为运行健康问题另报；按预先一致的规则补跑，不能直接选择性删除失败。

重点阅读每次尝试的 `result.json`、`config.json`、`timing.json`、`trajectory/`、`verifier/test-stdout.txt` 和 `verifier/reward.txt`。检查无 skill 组没有读取 skill；检索或生成方法仅能用任务可见信息，不能读 oracle、verifier、参考答案。你的方法自身产生的检索/生成调用费用和延迟也要计入。

3 个任务 × 3 次只适合检查机制和发现明显问题，不能据此声称统计显著或复现全榜；选定方法后再扩展独立测试集、重复次数，并报告置信区间。若新增方法改变资源或预算，明确记录变化。

上游资料：[SkillsBench](https://github.com/benchflow-ai/skillsbench)、[BenchFlow](https://github.com/benchflow-ai/benchflow)、[SkillsBench 1.1](https://www.skillsbench.ai/blogs/skillsbench-1-1)。
