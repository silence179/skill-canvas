# Skill 结构图 v3

按 skill 来源选图；每次只替换该 skill 的一张图。以下任务名仅用于找到原资源和后续评测。

|skill|决定|表示／原因|预览|
|---|---|---|---|
|prefix-cache-replay|redraw|state_machine：驻留状态与带 guard 的 S/M/G 迁移，比单一路径更核心。|[PNG](figures/prefix-cache-replay/diagram.png) · [SVG](figures/prefix-cache-replay/diagram.svg)|
|cache-policy-comparison|no_new_diagram|原文已是完整的策略比较表；继续保留全文，不另画一张表的截图。|不单独运行|
|power-flow-data|no_new_diagram|主体是字段、索引和单位的查阅契约，原文表格与代码比额外图更直接。|不单独运行|
|dc-power-flow|redraw|typed_dataflow：源与脚本定义数据、矩阵、角度和潮流之间的依赖及函数返回契约。|[PNG](figures/dc-power-flow/diagram.png) · [SVG](figures/dc-power-flow/diagram.svg)|
|economic-dispatch|redraw|variable_constraint_graph：主体是变量、目标和多组同时成立的约束，不是逐步动作。|[PNG](figures/economic-dispatch/diagram.png) · [SVG](figures/economic-dispatch/diagram.svg)|
|locational-marginal-prices|redraw|paired_dependency_graph：对偶量依赖约束与单位；base/反事实是共享结构的两支及比较关系。|[PNG](figures/locational-marginal-prices/diagram.png) · [SVG](figures/locational-marginal-prices/diagram.svg)|
|state-space-linearization|no_new_diagram|很短的公式／离散化查阅卡，保留原文即可；不为流程改流程。|不单独运行|
|finite-horizon-lqr|redraw|indexed_recurrence：核心是 P[k+1] 到 K[k]/P[k] 的索引依赖和逆序递推。|[PNG](figures/finite-horizon-lqr/diagram.png) · [SVG](figures/finite-horizon-lqr/diagram.svg)|
|mpc-horizon-tuning|no_new_diagram|主体是参数指南与权衡表，无需另造流程，也不加入源未给出的验收标准。|不单独运行|
|integral-action-design|redraw|feedback_block：误差、dt、泄漏、限幅与输出相加，是反馈信号连接。|[PNG](figures/integral-action-design/diagram.png) · [SVG](figures/integral-action-design/diagram.svg)|
|ordered-window-sequencing-mip|redraw|aligned_windows_and_constraints：顺序、共享前后缀和 active-pattern overlap 适合空间对齐。|[PNG](figures/ordered-window-sequencing-mip/diagram.png) · [SVG](figures/ordered-window-sequencing-mip/diagram.svg)|
|mip-solver-and-solution-audit|keep_activity|原文明确是求解、提取、落盘、复读和审计的操作顺序，现有活动图适配。|不单独运行|
|fjsp-baseline-repair-with-downtime-and-policy|redraw|resource_timeline：主体是前序与机台／停机区间的同时约束，以及逐整数最早可行边界。|[PNG](figures/fjsp-baseline-repair-with-downtime-and-policy/diagram.png) · [SVG](figures/fjsp-baseline-repair-with-downtime-and-policy/diagram.svg)|
