# 本次准备与验证

日期：2026-11-14（北京时间）。

新增 5 任务实验正在执行：材料位于 `uml-expanded/`，13 个 skill 各有 UML、PNG、SVG 和严格匹配的 text/image 包。正式计划为每任务每组 1 次，共 10 次，结果目录 `jobs/uml-expanded/paired-five-v1/`。已验证所有任务的实际 HTTP 图像传递，以及 DeepSeek 接受 4 图输入。首次原始参考解检查出现下载、评分依赖缺失和构建超时；记录保留。随后在 `.runtime/uml-expanded/prepared-tasks/` 建立只增加依赖预装/wheel 缓存的实验副本，其余题目/数据/skill/参考解/评分器逐文件一致。全部 5 个依赖环境已准备；参考解在逐项复核，健康任务开始对照。

当前已完成前缀缓存一对：两组 reward=1、传递 valid=true；text 68,624 token / 5 次工具调用，image 77,396 token / 4 次工具调用。其余结果以 campaign 的 comparison.json 为准；未完成的槽位不能算失败或成功。原先晶体任务的结果保持独立。

最新环境更新：公共 OpenCode 1.19.5 / Node 22.20.0 工具镜像已构建并接入默认 OpenCode 实验入口，各 task 仍使用自己的 Python 依赖。两个不同包环境的离线复制、缓存命中、损坏哈希拒绝检查通过；晶体任务完整兼容性验证 reward=1，8 次任务请求图像传递 valid=true，任务容器清理确认。见 [公共工具镜像说明](SHARED_OPENCODE.md)。新增 5 个任务的 UML 准备仍待继续，本轮先按用户要求处理跨任务重复安装问题。

- SkillsBench、BenchFlow、Harbor 已完整检出当前浅克隆文件；三个仓库与 `sources.lock.json` 的提交一致，上游工作区无改动。
- SkillsBench 默认任务目录实际有 87 个 `task.md`。
- BenchFlow 已在 `repos/benchflow/.venv` 按其锁文件安装，版本 `0.10.0rc3`，Python `3.12.13`。
- 工作区补装 Compose `2.40.3` 和 Buildx `0.30.1`，两者 SHA256 已验证，值记录在 `sources.lock.json`。
- `econ-detrending-correlation`、`offer-letter-generator`、`crystallographic-wyckoff-position-analysis` 均通过官方结构检查。检查同时提醒：任务没有 canary，且评分阶段会联网安装依赖，网络失败可能影响评分。
- 实验入口的五种模式及三任务三次重复计划已检查；dry-run 不调用模型。

## 实际运行状态

**强制图像/全文输入的新对照已完成，两组均得分 1，传递复核通过；本次加图组总 token 减少约 67.2%。仅为单任务各一次的观察，不能据此证明图像增益。** 旧版未读图的结果和前次失败记录均保留，不能混用。

首次 oracle 因本机缺 Compose 在容器创建前失败，该问题已通过工作区插件解决。

第二次 oracle 继续到 Docker 镜像构建，但基础镜像 `python:3.12-slim` 的拉取失败：Docker daemon 请求 `https://auth.docker.io/token` 超时。失败发生在任务执行前，属于镜像仓库网络问题，不是参考解法或 skill 的效果问题。对应任务没有有效 reward，不能把命令显示的汇总 0 分当作模型失败。

错误证据：

`jobs/oracle/2026-11-14__13-51-14/econ-detrending-correlation__db4c7df8/error-traceback.txt`

## 早期排查步骤（后续处理结果见文末）

1. 先让宿主机 Docker daemon 能正常访问 Docker Hub 的 registry 和鉴权端点。当前 shell 能从 GitHub 下载，并不代表 Docker daemon 具备相同的网络配置。
2. 在工作区终端检查基础镜像：

   ```bash
   cd /home/silence/myfiles/SkillCanvas
   export DOCKER_CONFIG="$PWD/.runtime/docker"
   docker pull python:3.12-slim
   ```

3. 拉取成功后，重新创建参考实验并执行空操作检查：

   ```bash
   python3 experiments/run.py oracle --fresh
   python3 experiments/run.py nop
   ```

4. oracle=1、nop=0 且评分日志完整后，按根目录 README 的流程跑 baseline/curated/custom。若报错，不要通过修改评分器或放宽断言来让控制实验通过。

## 后续新增：UML 流程图实验

已按用户确定的方案准备 experiments/uml-flowchart/：选用 crystallographic-wyckoff-position-analysis，为 pymatgen 和 sympy 各生成一张 UML 活动流程图，并准备 text/image 两组。两组均保留完整原文和相同脚本、参考资料；image 入口要求先用读图工具查看 PNG，再读原文。

PlantUML 渲染、图像布局检查、原文与资源哈希校验、四个 skill 入口结构检查和两个运行计划的 dry-run 均已完成。尚未执行模型对照任务或确认实际读图传递链路。详见 uml-flowchart/README.md。

## 后续新增：DeepSeek 配置

已创建根目录 .env（API key 留空，创建权限 600）和 .env.example；默认 EXP_AGENT=opencode，EXP_MODEL=deepseek/deepseek-flash，官方 API 地址为 https://api.deepseek.com/v1。实验入口已支持自动读取 .env，并在实际 DeepSeek 任务缺少 key 时提前报错。配置解析测试与默认 text/image 的 dry-run 已检查；没有调用模型服务或验证凭证。

## Docker Hub 网络问题处理

用户运行 text 组时再次遇到基础镜像拉取超时，证据位于 jobs/uml-flowchart/text/2026-11-14__14-54-59/crystallographic-wyckoff-position-analysis__ceb42932/error-traceback.txt。该次 n_tool_calls=0、rewards=null，未进入模型执行。

只读检查发现：当前进程能访问 Docker Hub 的鉴权端点（HTTP 200），Docker daemon 的直接访问却超时，且没有缓存 python:3.12-slim。已用本地 crane 0.20.6 从官方 Docker Hub 下载 linux/amd64 镜像并导入 Docker，未修改或重启宿主机 Docker 服务。

基础镜像 image ID：sha256:20215fae337479b40ac2900bb24229701ab04d563432ba4d23113f70296d7ddb。

镜像归档与来源记录：.runtime/images/python-3.12-slim.tar 和 .runtime/images/python-3.12-slim.json。

## 晶体任务环境验证通过

基础镜像导入后，首次参考实验又遇到构建超过 600 秒；使用任务原始 Dockerfile 提前构建环境，期间 Python 包下载曾超时，重试后成功。pymatgen、sympy 及其依赖已装入本地镜像缓存，未修改任务 Dockerfile、参考解或评分器。

随后重新执行晶体任务 oracle，于 2026-11-14 15:14（北京时间）完成：reward=1.0、errors=0，耗时约 13 秒，未调用模型。报告：jobs/uml-flowchart/environment-check/2026-11-14__15-13-58/report.md。

该结果确认本机该任务的环境、参考解与评分流程可运行；OpenCode 启动、API 凭证和实际图像读取仍需模型实验验证。可用下列命令重新开始两组实验，避开此前失败结果的默认续跑：

```bash
python3 experiments/uml-flowchart/run.py text --fresh
python3 experiments/uml-flowchart/run.py image --fresh
```

## 纯文本组首次模型运行完成

用户启动的 jobs/uml-flowchart/text/2026-11-14__15-15-34 于北京时间 15:29:11 完成：OpenCode + deepseek/deepseek-flash，reward=1.0、error=null、22 次工具调用。报告位于该目录的 report.md。

本次一直显示 `sandbox creating` 的主要原因是首次安装 OpenCode：系统组件和 Node 安装约 245 秒，npm 下载两个 Linux 二进制包约 412 秒，随后导出镜像。总环境准备 678.6 秒，云元数据访问隔离准备 69.5 秒，Agent 实际执行 52.4 秒，总计 816.3 秒。辅助镜像原先也遇到 Docker Hub 超时，框架回退到容器内安装并通过检查。

OpenCode 安装层已保留为 benchflow-layer:agent-ebd9cee41ffd0311ce20801f251a5278ea511fa87f1501cf7633c2712445157b。相同任务镜像内容、相同安装版本和配方、相同架构可复用它；text/image 的 skill 文件被复制进任务镜像，镜像内容不同，可能分别安装。不能保证所有任务或实验组都共用这一层。清理 Docker/BenchFlow 缓存或缓存自动回收后也可能需要重建。

辅助基础镜像已从官方固定摘要导入：alpine@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6；OCI 文件及归档在 .runtime/images/alpine-metadata.oci 和 alpine-metadata.oci.tar。其所有 blob 的 SHA256 均已校验，未关闭框架检查。

随后调用框架原始辅助镜像构建函数预备缓存，已越过 Docker Hub 拉取，但 Alpine 包安装超过框架的 300 秒时限，完整辅助镜像尚未就绪。不要将基础镜像导入视为全部辅助安装已完成。此前纯文本组已通过框架回退路径正常完成；后续启动仍可能花时间执行此项检查。

## 强制 skill 图像输入：forced-prefix-v1

旧版对照的加图组（15:45:45 运行）虽得到 reward=1，但调用 skill(pymatgen) 失败（ripgrep execution failed，约 90 秒），全部捕获的模型请求均无图像。两组都没有完整读取 GUIDE.md，不能视作有效的图像实验。

新入口使用实验目录内的 delivery_runner.py 与 delivery_protocol.py，仅在该入口进程内扩展 BenchFlow 生成的私有模型代理回调，不修改上游框架源码。每次 Agent 请求在原始任务前强制加入：text 组两份完整原文；image 组两张真正的 PNG image_url 数据块，再加入相同全文。没有图像到纯文本的有效回退。标题/摘要调用不计入 Agent 图像传递检查。运行结束逐请求复核哈希、顺序、响应与捕获覆盖；失败返回非零并生成 valid=false 的 skill-delivery.json，原始评分不改写。

输出目录更换为 jobs/uml-flowchart/forced-v1/{text,image}；policy 包含资源和适配器代码哈希，防止与旧实验或修改后的配置混用。两组都强制预加载全文，因此这是新的实验条件；旧版按需加载结果不能直接混入。

验证：10 项新传递测试、5 项 .env 回归测试、两组 dry-run 均通过；本地接口实际检查 LiteLLM 发送的 HTTP 正文，含两图与两份原文；两次 DeepSeek 小请求也接受了该输入并返回 OK（代理对象复制兼容性修正后复核一次）。证据在 .runtime/uml-delivery/{local-wire-smoke,live-provider-smoke}.json。后续增加了只读审计对框架日志脱敏的兼容性，实时传递协议未改变。

## 首次强制输入对照完成

text：jobs/uml-flowchart/forced-v1/text/2026-11-14__18-08-54；image：jobs/uml-flowchart/forced-v1/image/2026-11-14__18-59-18。两组同一任务、OpenCode 1.19.5、DeepSeek Flash 路由，原文哈希与传递协议源码哈希一致，评分均为 11/11、reward=1，无模型或工具失败。任务容器均确认已清理。

纯文本 19 次工具调用、15 次任务模型调用、491,396 总 token、Agent 执行 64.6 秒；加图 8 次工具调用、7 次任务模型调用、161,328 总 token、Agent 执行 15.7 秒。每次加图任务请求均包含两张 PNG。总 token 包含各一次自动标题请求，缓存命中属于输入子集。

执行期间修复两个问题：运行前版本清单不再要求未参与执行的 Harbor 仓库存在；事后审计对原文 API key 示例占位值的框架原生脱敏作精确匹配。文本原始误报保留为 skill-delivery.original.json，修正后复核单独保留 skill-delivery.reviewed.json，原始模型记录和评分没有改写，也没有为审计修正重跑模型。两组传递复核均 valid=true。

具体数据、代码与原始证据哈希、单次实验局限见 uml-flowchart/results/2026-11-14-forced-v1-180854-185918.md 和同名 JSON。两组之间仅事后审计实现更新，实时传递协议一致；旧入口源码已保留在 .runtime/uml-delivery/adapter-before-audit-fix/。

## 五任务扩展对照完成（2026-11-15）

新增前缀缓存、电价分析、R2R 控制、考试排程、制造排程五任务，共 13 个 skill，各有 PlantUML、PNG/SVG 与原文索引。沿用每次任务请求强制提供全文、图片组 PNG 在前的协议，使用 OpenCode 1.19.5 与 deepseek/deepseek-flash。公共 OpenCode 镜像复用正常；新任务环境启动约 26 秒，无需再次 npm 下载。

原始 10 次尝试保留在 jobs/uml-expanded/paired-five-v1。考试模型接口连接重置、制造文字组含失败请求，因此在制造图片组出分前登记一次完整补跑，额外运行考试/制造各两组，最终选定记录在 paired-five-v1-recovery（其余六次引用原始结果）。制造评分依赖曾在线下载失败，原生 reward=0 却未执行测试，已在派生分析中排除；在制造两组补跑前仅适配依赖启动，评分尾部和 Python 断言逐字节一致，新参考解通过 15 项、空输出被 15 项测试拒绝。

最终五任务两组均通过 4/5。制造文字组因局部最早开始约束失败一项，图片组 15/15；考试图片组 1500 秒超时，缺最终 schedule.csv，其 35 次捕获请求图文均齐全，但完整运行审计因超时不通过。超时仍计入任务失败，没有从通过率中删除。

完整四个配对总 token 为 2,512,281→3,492,581（+39.0%）；包含考试超时的全部选定五任务为 4,247,030→5,258,823（+23.8%），工具调用 122→127。单任务变化 +12.8%、−2.1%、+102.9%、考试单列、−9.1%。现有结果尚无稳定通过率或成本收益，不能从单次差异推断认知增强。

独立仅图识读检查三问全对。20 项最终证据核验通过：冻结材料、原始计量、评分执行、相同 task digest 与参考解、公共镜像、十组可见输入和容器清理等。上游仓库未修改，全部任务容器已清理，共享镜像保留。结果、限制、14 次任务尝试累计开销及证据链接见 [完整报告](uml-expanded/results/paired-five-v1-recovery.md)，图见 [索引](uml-expanded/FIGURES.md)。

## 完整 skill 文件夹版 UML v2（2026-11-15）

按用户要求重新读取五个任务完整 skills 目录（16 个不同源文件），重写并渲染 13 张图；新增来源包括 DC 潮流计算脚本、成本函数子目录参考、制造 skills 根目录共享 reference.md，并纳入显式引用的兄弟 skill。其余目录只有 SKILL.md，已逐一复读。

材料单独位于 uml-expanded/full-skill-v2/：完整源快照、来源映射、UML、PNG/SVG、全文与原始资源保持一致的两组材料包、manifest 和 QA 记录。修正了积分控制把调参建议放在每个时间步中的歧义；图中标注源公式/启发式的适用边界，未按旧评分补写算法。

13 张最终 PNG 已逐张检查文字与箭头；全部源文件、原文、共享资源与两组材料哈希校验通过。旧版冻结图和实验校验仍通过，未覆盖任何旧轨迹。本次没有启动模型对照，旧运行入口仍绑定 v1。参见 [新版图像索引](uml-expanded/full-skill-v2/FIGURES.md) 和 [来源复核](uml-expanded/full-skill-v2/SOURCE_REVIEW.md)。

## 2026-11-15 完整 skill 文件夹 UML v2 重跑

已登记并启动五任务各 text/image 一次，共十次串行对照，使用完整目录提炼的 13 张新版图。原文、资源和原版字母序目录均匹配，仍为每个主请求 PNG 优先 + 完整 GUIDE。10 种本地 HTTP 输入检查及两组 dry-run 通过；所有 prepared task 摘要与此前健康 oracle 一致。模型 deepseek/deepseek-flash、OpenCode 1.19.5、公共工具镜像、任务时限及评分设置沿用 v1。

结果与实时状态：`jobs/uml-expanded/paired-five-full-skill-v2/campaign.json`；每个槽位结束自动更新 `comparison.md` / `comparison.json`。新版入口：`uml-expanded/full-skill-v2/campaign.py`。旧实验保持独立。本轮尚未完成，不预判图像收益。

## 2026-11-15 完整目录 UML v2 十次重跑完成

文字 4/5、图片 3/5。前缀缓存、电价与制造均两组通过；R2R 图片 5/6 测试通过、整定时间 5.04s 未达 <4s；考试两组均在 1500s 超时、缺最终文件，不纳入完整 token 配对。总记录 7,596,686 token，框架估计 $0.438587（非供应商账单）。图片组各任务收益不一致，不能证明稳定认知增强。23 项材料、源文件、镜像与可见输入检查通过，所有本批任务容器清理确认，上游仓库未改动。

结果：`jobs/uml-expanded/paired-five-full-skill-v2/RUN_NOTES.md`；轨迹：同目录 `TRACE_INDEX.md`；十次明细与旧版比较保持独立。
