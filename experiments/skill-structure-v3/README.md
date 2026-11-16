# 按 skill 源结构重绘：单图替换实验

**用户中途调整后的状态：** 原计划 13 个槽位已关闭为 8 次实际运行＋5 个未启动即取消的槽位。之后改为 [每个剩余评测环境一次组合图运行](../skill-structure-v3-combined/README.md)，新增 3 次；LQR 单图在调整前已经启动，收尾后作为补充结果保留，不冒充组合试验。来源、选图与新图均未改变。取消登记见 jobs/skill-structure-v3/user-steering-amendment.json。下文保留原始设计用于追溯。

用户授权：复用既有实验逻辑，只对不适合活动流程图的 skill 重画；适合不画图的 skill 不单独跑。选图不由任务题目、实例、评分失败或历史解法反推。

来源与材料先冻结，评测后分析。作者先前已见历史结果，本实验不是盲选；生成程序只读取冻结的本地 skill 闭包与旧图包，所有 16 份源资源逐字节匹配公开 SkillsBench 提交。图不加入实例数据或源中不存在的验收阈值。

- [逐 skill 判断与全部新图](FIGURES.md)
- [源定位与选图理由](selection.json)、[冻结材料清单](manifest.json)、[人工来源与图面检查](SOURCE_REVIEW.json)
- [本次结果](../../jobs/skill-structure-v3/comparison.md)

重绘 8 个 skill：prefix-cache-replay、dc-power-flow、economic-dispatch、locational-marginal-prices、finite-horizon-lqr、integral-action-design、ordered-window-sequencing-mip、fjsp-baseline-repair-with-downtime-and-policy。

不另画／不单独评测 4 个：cache-policy-comparison、power-flow-data、state-space-linearization、mpc-horizon-tuning，原因是原文表格／公式／代码更直接。mip-solver-and-solution-audit 保留活动图，因原文就是操作与审计顺序。

“不单独评测”并不意味着悄悄删除背景图：当另一 skill 被替换时，这些 skill 的完整原文和旧图保持原字节，确保每个变体只有一个 PNG 改动。此次没有测删除图片的作用。

对每份重绘 skill 运行一次新图变体；它所关联的原生评测环境提供一个当轮旧图控制，同环境的多个单图变体共享这个控制。共 8 个变体＋5 个共享控制＝13 个唯一运行。评测环境只是测量接口；干预和报告单位为被替换的 skill。共享控制意味着配对相关，每个变体只有一次，不能当作独立重复或稳定因果效应。

沿用 DeepSeek Flash、OpenCode 1.19.5、每轮 PNG-first＋完整原文、同一公共工具镜像、原环境与原生评分、原超时预算、串行、无自动重试。制造评分沿用之前登记的离线依赖启动适配，评分断言不变。没有修改 BenchFlow 或 SkillsBench 源码。

新图用 Graphviz 的源生结构表示而不是位图生成模型。图的摘要强调、关系、布局、像素面积都可能变化，因此测的是单份 skill 的“图替换包”效果，不是内容完全相等的纯图型消融。符号时间线仅表达源约束，不是任何任务实例的可行解。

```bash
python3 experiments/skill-structure-v3/materials.py --check
repos/benchflow/.venv/bin/python experiments/skill-structure-v3/smoke.py
repos/benchflow/.venv/bin/python experiments/skill-structure-v3/campaign.py plan
repos/benchflow/.venv/bin/python experiments/skill-structure-v3/campaign.py run
```

材料冻结后不覆盖；同一结果目录不重复启动已 launched 的槽位。失败和超时保留原生得分与消耗，不根据分数选择性重跑。实际接口预检单独记录于 live-preflight.json，不作为 benchmark，也不混进 13 次的用量。

本地传递检查覆盖全部 13 个输入包。来源、目标地址与审批核查记录见 PREFLIGHT_DATA_SCOPE.json；预检最初因审批缺少材料来源／目标证据被拒绝，证明材料来自公开源、目标为既有 api.deepseek.com 后重新审核通过。
