# 组合图续跑：每个剩余评测环境一次

用户在单图实验进行中要求：后续将各 task 中已选定的新图一起使用，直接跑一次，不再逐 skill 拆分运行。

选图仍以 skill 为依据。[8 张原先冻结的新图及选择理由](../skill-structure-v3/FIGURES.md)全部不变；本目录只把它们分组装包，不根据题目、实例、分数或历史解法改图。

|后续运行|一并替换的 skill 图|对照来源|
|---|---|---|
|R2R|finite-horizon-lqr、integral-action-design|本轮已结束的旧图控制|
|考试排程|ordered-window-sequencing-mip；audit 活动图保持旧版|历史完整目录 v2 图片组|
|制造排程|fjsp-baseline-repair-with-downtime-and-policy|历史完整目录 v2 图片组|

只新增上述 3 次，不补跑对照、不重跑前面已完成的缓存／电价运行。历史对照不能当同轮随机对照：模型采样、执行路径和时段可能不同。R2R 组合结果也不能分别归因于两张图。

原队列已完成 8 次，其中 LQR 单图在变更到达前已启动，允许收尾并作为额外记录保留；尚未启动的 5 个槽位取消。原父调度器在当前子评测结束后停止，原评分／轨迹不改写。

新增包装保持所有完整 GUIDE、资源与未替换 PNG 逐字节一致；R2R 恰有 2 个 PNG 改动，考试／制造各 1 个。[冻结包装清单](manifest.json)、[本地传递检查](wire-check.json)。本地预检模块查找修订发生于全部槽位仍 planned 时，旧清单保存在 prelaunch-wire-fix/，图和 bundle 字节未改变。

```bash
repos/benchflow/.venv/bin/python experiments/skill-structure-v3-combined/combined.py plan
repos/benchflow/.venv/bin/python experiments/skill-structure-v3-combined/combined.py run
repos/benchflow/.venv/bin/python experiments/skill-structure-v3-combined/combined.py report
```

[组合结果](../../jobs/skill-structure-v3-combined/comparison.md)。仍沿用原模型、公共工具、强制图片／全文传递、原环境、原生评分、串行、每变体一次和原超时预算。
