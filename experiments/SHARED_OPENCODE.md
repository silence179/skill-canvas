# 历史：公共 OpenCode Docker 工具镜像

以下记录迁移前的 Docker 实验与验证。当前 Singularity/Slurm 入口及镜像准备方式见[项目 README](../README.md)，不再默认使用本文的工具镜像与旧参数。

当时实验入口默认复用本机的 `skillcanvas-opencode:1.19.5-19299e3fe8add58e3b19`，包含 OpenCode 1.19.5 和 Node 22.20.0。Python 及其依赖仍由各 task 原有的 Dockerfile 安装。

公共镜像是工具来源：只保存已安装工具的归档，不包含晶体任务的 Python 包、数据、skill、用户目录、对话或密钥。任务先按自己的 Dockerfile 构建，再在一个不联网的构建步骤中从公共镜像解包工具。这样可以跨任务复用 OpenCode，同时保留任务自己的系统与 Python 环境。更换 skill 也只需重新复制工具，不会重新 npm 下载。

目前适用于与公共镜像相同的 linux/amd64、glibc 环境；musl、不同架构、自定义安装命令或不支持原生镜像缓存的任务沿用 BenchFlow 原有安装路径。任务缺少兼容系统库时，构建检查失败，框架也会按原有路径安装。不能据此承诺任意系统、架构均通用。

## 使用

继续使用原来的实验入口即可。无需修改 `.env`，也不需要把 task 的 `FROM` 改成公共镜像。公共工具接入只在当前实验入口进程生效，上游 BenchFlow 与 SkillsBench 源码未改。

请为新实验使用新结果目录，避免续跑旧实验时复用旧成绩：

```bash
python3 experiments/uml-flowchart/run.py text --fresh --jobs-dir jobs/uml-flowchart/shared-tools/text
python3 experiments/uml-flowchart/run.py image --fresh --jobs-dir jobs/uml-flowchart/shared-tools/image
```

两组都使用公共镜像；原来的 PNG＋完整 skill 原文输入方式继续生效。检查/复建工具：

```bash
repos/benchflow/.venv/bin/python experiments/shared_opencode.py check
repos/benchflow/.venv/bin/python experiments/shared_opencode.py build
```

`build` 在已有镜像可用时只做检查。目前复建需要本机存在 BenchFlow 记录过来源的原生 OpenCode 安装层：迁移到新机器时，可以先按原路径安装一次，再建立该机器的公共镜像。镜像与本机记录在 `.runtime/shared-opencode/`；删掉 Docker 镜像或这些记录后不保证继续复用。版本和配方变更会拒绝复用旧工具。

需要复现原有的逐任务安装方式时，加 `--no-shared-opencode`。直接运行上游 `bench` 不经过本适配层，也沿用原方式。

## 验证与证据

2026-11-14 完成真实 Docker 离线检查：

| 环境 | Python 包区别 | 首次复制和构建 | 再次查找 |
|---|---|---:|---|
| 晶体任务预构建环境 | 有 pymatgen | 17.2 秒 | 命中缓存 |
| 原始 python:3.12-slim | 无 pymatgen | 16.8 秒 | 命中缓存 |

两者均以普通用户运行同一个 OpenCode 1.19.5 和 Node 22.20.0，并通过实际环境内的文件内容、符号链接校验。构建步骤禁止网络访问，未执行 npm。故意给错工具归档哈希的真实构建被拒绝；5 项回归测试覆盖自定义配方、系统不兼容、镜像标签移动、原生构建保护保留及运行时文件损坏。

原有镜像来源校验、任务环境检查、缓存锁、运行用户、凭证配置、skill 部署和评分流程继续由 BenchFlow 执行。公共工具归档在解包前校验，实际使用缓存时再次校验全部工具文件和符号链接。记录文件本身不会使错误内容被接受。

本机原始证据：`.runtime/shared-opencode/image.json`、`smoke.json`、`smoke.log`。完整模型验证另存 `jobs/uml-flowchart/shared-opencode-canary/image/`，其每个实际使用公共工具的 trial 有 `shared-opencode.json`。这次环境验证与旧 text/image 对照分开记录，不能补作旧实验的额外重复。

完整验证已完成：`2026-11-14__20-51-54/crystallographic-wyckoff-position-analysis__805dc7e6`，reward=1，11/11 检查通过，error=null；8 次任务模型请求均含两张 PNG 与完整原文，传递复核 valid=true。首次该任务变体的环境准备 23.6 秒，实际 Agent 执行 20.4 秒，评分 97.1 秒，总计 153.4 秒。10 次工具调用、总 token 202,203；这次仅验证运行兼容性，不用于宣称图像效果或环境优化改变了模型能力。任务容器清理后已确认不存在，公共工具镜像仍在。

本轮环境准备代码 SHA256 为 `45fe58513fe9db1e6153eab95b8e8794ecbb9e06a74b1a693705afa2de997b9d`；5 项公共工具回归、5 项环境配置回归、10 项图像传递回归均通过。两个上游代码仓库仍无改动。运行过程中 BenchFlow 原生缓存回收器回收了两份旧 agent 缓存层，以维持其磁盘空间要求；旧结果文件与公共工具镜像保留。

首次新任务仍需构建自己的环境、复制约 0.6 GB 工具、准备评分器；本改动省去重复下载和安装 OpenCode，不表示整个 sandbox 创建过程都只需上述 17 秒。
