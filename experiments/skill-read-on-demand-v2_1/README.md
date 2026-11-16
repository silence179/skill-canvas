# 读取时附图 v2.1：原生工具失败可回退

用户停止其余四题的文字／图片批次后，要求重新跑图片条件。本目录保留 v2 的原始正文、原图、自动附图规则和原生任务评分，仅修复一个已实际出现的错误分支：原生 skill 返回 `ripgrep execution failed` 时，原样把错误交给模型，不当作已加载，也不附图；模型若随后通过文件工具成功读取正文，再正常附图。

之前 v2 会因这个已知错误文本不在白名单内而拒绝下一次请求，模型无法回退读取文件。该次异常及中断的电力任务全部保存在 `jobs/skill-read-on-demand-v2/remaining-four-2026-11-16/`；旧代码的登记哈希保持不变。

28 项本地检查已通过，包括真实失败消息的原样透传、并行工具中的失败和成功结果，以及失败后直接读文件触发对应图。检查没有调用付费模型。

新批次入口 `image_only.py` 只启动前缀缓存、电力市场、制造排程、考试排程的图片条件，各一次，串行，无自动重试，不启动文字条件。结果保存在 `jobs/skill-read-on-demand-v2.1/image-only-four-2026-11-16/`。任务、资料、原 v1 UML、模型、OpenCode 1.19.5、依赖环境和预算均复用此前设置。

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True repos/benchflow/.venv/bin/python \
  -m unittest discover -s experiments/skill-read-on-demand-v2_1 -p 'test_*.py' -q
```

这批是图片条件重跑，没有生成新的文字对照；不将旧强制全文实验或被中断的运行拼接为新协议的配对控制。后续分析需单列是否实际附图、工具失败和超时，保留所有尝试。

四轮现已结束，参见[结果与归因](../../jobs/skill-read-on-demand-v2.1/image-only-four-2026-11-16/FINDINGS.md)和[逐请求审计](../../jobs/skill-read-on-demand-v2.1/image-only-four-2026-11-16/ANALYSIS.md)。前缀缓存、电力定价得分 1；制造得分 0（13/15，提前开工），考试得分 0（超时，缺失正式产物）。四题实际附图 1、4、1、2 张。考试候选只作事后纯函数复算，没有替换原评分或补写原产物。本批累计记录 3,842,405 token，估算 $0.191076。
