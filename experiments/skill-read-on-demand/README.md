# 读取 SKILL.md 时自动附图

协议 `skill-read-on-demand-v2` 修正 v1 只监听原生 `skill` 工具的范围。模型使用什么工具由模型决定；无需为看图额外调用工具。原始 SKILL.md 的正文和文件名不改。

当模型成功收到某个已登记 skill 的原生工具结果，或通过 `read`、`read_file`、`readfile`、`bash`、`shell`、`execute`、`exec_command` 获得该 SKILL.md 正文时，图片组自动在该批完整工具结果之后附上对应 PNG。原有工具文本原样保留，图片作为真实多模态媒体发送；文字组不改变输入，使用相同规则记录读取事件。

文件读取以**返回的源正文**识别，不只匹配命令里的路径。因此 `cat`、循环、变量和 Python 脚本返回完整正文都可识别；带行号的文件工具也支持。部分读取要求能关联到具体 skill 路径且返回至少 80 字符的连续原文证据。只读元数据、极短或无法核验的片段不算已获得正文；这是输出匹配方案的覆盖边界。代理层不是文件系统审计器，不承诺识别没有返回正文的隐藏读取、编码内容或任意自定义工具。

仅列目录、读取失败、提及文件名、压缩摘要、仅读取参考文件，都不触发。首次实际返回正文前不注入正文或图片；不因为 task 内容决定选哪个 skill。同一已保留历史中每个 skill 只附一次图，重复读取不增加副本；历史压缩移除相关正文后，不从摘要恢复图片。并行工具结果收齐后才附图。

## 入口与历史隔离

新入口：`experiments/skill-read-on-demand/runner.py`，默认新结果目录 `jobs/skill-read-on-demand-v2/`。本目录复用同样的公共任务、原始 skill、已有图、模型路由、固定 OpenCode 和原生评分器；旧 v1 代码、材料和四轮结果不修改。

离线预览，不启动模型、容器或任务评分：

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True repos/benchflow/.venv/bin/python \
  experiments/skill-read-on-demand/runner.py \
  --task r2r-mpc-control --arm image --figures uml-v1 --dry-run
```

单次模型运行使用相同命令去掉 `--dry-run`；文字条件改为 `--arm text`。2026-11-16 在用户再次授权后已完成[晶体与 R2R 四轮实际对照](../../jobs/skill-read-on-demand-v2/two-task-2026-11-16/FINDINGS.md)：R2R 图片条件实际附四张图、两组均 6/6，图片条件 token −55.6%；晶体两组均未读取 skill，均为 6/11，未附图。本批结束，没有启动额外运行。

## 已验证的范围

26 项本地检查覆盖原生 skill、直接读取、命令循环、多 skill 同次读取、带行号结果、可核验的部分读取、文字条件、失败和目录读取、并行边界、重复与压缩，以及原生 BenchFlow callback 的编译和预算检查。

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True repos/benchflow/.venv/bin/python \
  -m unittest discover -s experiments/skill-read-on-demand -p 'test_*.py' -v

LITELLM_LOCAL_MODEL_COST_MAP=True repos/benchflow/.venv/bin/python \
  experiments/skill-read-on-demand/replay_check.py \
  --campaign jobs/skill-on-demand-v1/two-task-2026-11-16
```

[离线回放记录](replay-check.json) 使用刚完成的四轮真实请求检查新规则，并核对原始证据哈希。**回放只重建“若使用新规则会发送什么”，没有把图片发送给模型，也没有生成新的答案或成绩。**

- 晶体文字条件：识别到 pymatgen 的直接读取，新规则会附图。
- 晶体图片条件：实际只读 Wyckoff 参考文件，没有读取 SKILL.md，新规则仍不会附图。
- R2R 两条件：均识别到四个 skill 的直接读取，新规则会附上对应四张图；不因同一工具调用返回多个 skill 而漏记。

这修正图片加载的触发范围；尚未验证新规则下图片是否提高任务效果。今后报告应分别列出原生工具调用、文件读取激活和实际图片发送，不能再把这些指标混用。
