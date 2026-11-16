# 完整来源与语义复核

本版先阅读五个任务全部本地 skills 目录，再重写 13 张图。共 16 个不同源文件：13 份 SKILL.md、1 个 Python 脚本、1 份子目录参考、1 份 skills 根目录共享参考。显式引用的兄弟 skill 也纳入来源闭包。

这不是新增知识检索：外部网站/论文链接作为本地文献索引记录，不把其未附带内容假装读入。没有用 task.md、实例、oracle、verifier 或历史模型代码来补写算法。材料重建发生在旧结果之后，后续评测需单独登记。

原文与资源保留逐字节副本。图是完整资源的流程提炼，不是每句文字的逐字转换；背景、文献和示例中不构成流程的部分单独说明。来源中的歧义被标记，没有按旧实验评分静默修正原文。

## llm-prefix-cache-replay

### prefix-cache-replay

Keep pre-access hit accounting distinct from all-hash mutation; show M/G helper transitions, preserved promotion frequency, rounding and ghost exclusion.

- S1: [prefix-cache-replay/SKILL.md](tasks/llm-prefix-cache-replay/source/prefix-cache-replay/SKILL.md) — Keep pre-access hit accounting distinct from all-hash mutation; show M/G helper transitions, preserved promotion frequency, rounding and ghost exclusion.
- S2: [cache-policy-comparison/SKILL.md](tasks/llm-prefix-cache-replay/source/cache-policy-comparison/SKILL.md) — Companion policy specification: do not follow S3FIFO transitions when a different eviction policy is declared.

### cache-policy-comparison

Include LFU initial frequency=1 and insertion-order ties; follow the linked full S3FIFO skill. ARC is named but no algorithm is supplied.

- S1: [cache-policy-comparison/SKILL.md](tasks/llm-prefix-cache-replay/source/cache-policy-comparison/SKILL.md) — Include LFU initial frequency=1 and insertion-order ties; follow the linked full S3FIFO skill. ARC is named but no algorithm is supplied.
- S2: [prefix-cache-replay/SKILL.md](tasks/llm-prefix-cache-replay/source/prefix-cache-replay/SKILL.md) — Explicitly linked sibling: full S3FIFO transitions and prefix-hit accounting.

## energy-market-pricing

### power-flow-data

Preserve MATPOWER columns, non-contiguous bus labels, MW/per-unit conversion, reserve fields and large-JSON reading advice.

- S1: [power-flow-data/SKILL.md](tasks/energy-market-pricing/source/power-flow-data/SKILL.md) — Preserve MATPOWER columns, non-contiguous bus labels, MW/per-unit conversion, reserve fields and large-JSON reading advice.

### dc-power-flow

Add executable-resource contract: build_susceptance_matrix returns three objects; calculate_line_flows reuses saved susceptances, keeps original IDs and uses zero loading when rating<=0. CLI only prints matrix diagnostics.

- S1: [dc-power-flow/SKILL.md](tasks/energy-market-pricing/source/dc-power-flow/SKILL.md) — Add executable-resource contract: build_susceptance_matrix returns three objects; calculate_line_flows reuses saved susceptances, keeps original IDs and uses zero loading when rating<=0. CLI only prints matrix diagnostics.
- S2: [dc-power-flow/scripts/build_b_matrix.py](tasks/energy-market-pricing/source/dc-power-flow/scripts/build_b_matrix.py) — Both callable helpers, their return contracts, zero-X/zero-rating behavior and diagnostic CLI.

### economic-dispatch

Add reference-only MODEL=1 breakpoint costs and marginal costs. Flag general-polynomial layout versus the GUIDE example treating NCOST>=3 as quadratic; do not invent an unprovided piecewise optimization implementation.

- S1: [economic-dispatch/SKILL.md](tasks/energy-market-pricing/source/economic-dispatch/SKILL.md) — Add reference-only MODEL=1 breakpoint costs and marginal costs. Flag general-polynomial layout versus the GUIDE example treating NCOST>=3 as quadratic; do not invent an unprovided piecewise optimization implementation.
- S2: [economic-dispatch/references/cost-functions.md](tasks/energy-market-pricing/source/economic-dispatch/references/cost-functions.md) — Polynomial and piecewise-linear formats, coefficient units, marginal-cost formula; examples and bibliography context reviewed.

### locational-marginal-prices

Preserve source extraction and counterfactual workflow. Mark source dual*baseMVA scaling / sign as requiring review of the actual equation; do not inject a formula learned from previous verifier outcomes. Distinguish None->0 source fallback from an available market dual.

- S1: [locational-marginal-prices/SKILL.md](tasks/energy-market-pricing/source/locational-marginal-prices/SKILL.md) — Preserve source extraction and counterfactual workflow. Mark source dual*baseMVA scaling / sign as requiring review of the actual equation; do not inject a formula learned from previous verifier outcomes. Distinguish None->0 source fallback from an available market dual.

## r2r-mpc-control

### state-space-linearization

Include all four stated R2R partial derivatives and both discretization choices. Invertibility is an explicit mathematical precondition of the supplied inverse expression, not a new discretization algorithm.

- S1: [state-space-linearization/SKILL.md](tasks/r2r-mpc-control/source/state-space-linearization/SKILL.md) — Include all four stated R2R partial derivatives and both discretization choices. Invertibility is an explicit mathematical precondition of the supplied inverse expression, not a new discretization algorithm.

### finite-horizon-lqr

Preserve P-next versus P-current order, gain storage and first-action-only receding horizon. Returned/logged states are an interface summary, not a new controller.

- S1: [finite-horizon-lqr/SKILL.md](tasks/r2r-mpc-control/source/finite-horizon-lqr/SKILL.md) — Preserve P-next versus P-current order, gain storage and first-action-only receding horizon. Returned/logged states are an interface summary, not a new controller.

### mpc-horizon-tuning

Separate parameter selection and evaluation. Show both horizon guidelines without making them simultaneous hard limits; flag continuous ARE example versus discrete-model conventions.

- S1: [mpc-horizon-tuning/SKILL.md](tasks/r2r-mpc-control/source/mpc-horizon-tuning/SKILL.md) — Separate parameter selection and evaluation. Show both horizon guidelines without making them simultaneous hard limits; flag continuous ARE example versus discrete-model conventions.

### integral-action-design

Separate timestep integration/clipping from post-trial tuning advice. This is an editorial clarification: the source gives tuning advice but does not mandate online gain adaptation.

- S1: [integral-action-design/SKILL.md](tasks/r2r-mpc-control/source/integral-action-design/SKILL.md) — Separate timestep integration/clipping from post-trial tuning advice. This is an editorial clarification: the source gives tuning advice but does not mandate online gain adaptation.

## exam-block-sequencing

### mip-solver-and-solution-audit

Preserve installed-solver discovery, solver-required method, incumbent extraction, truthful certificates, exact disk reload before metrics, objective consistency and explicit formulation contents.

- S1: [mip-solver-and-solution-audit/SKILL.md](tasks/exam-block-sequencing/source/mip-solver-and-solution-audit/SKILL.md) — Preserve installed-solver discovery, solver-required method, incumbent extraction, truthful certificates, exact disk reload before metrics, objective consistency and explicit formulation contents.

### ordered-window-sequencing-mip

Retain both representations, all linearization bounds, ordered keys, successor labels, masks, boundary conditions, active-pattern overlap and full optimized objective.

- S1: [ordered-window-sequencing-mip/SKILL.md](tasks/exam-block-sequencing/source/ordered-window-sequencing-mip/SKILL.md) — Retain both representations, all linearization bounds, ordered keys, successor labels, masks, boundary conditions, active-pattern overlap and full optimized objective.

## manufacturing-fjsp-optimization

### fjsp-baseline-repair-with-downtime-and-policy

Incorporate the shared baseline-repair context. Keep integer scan and same-order commitment explicit. Flag conflicting heuristic priorities and the sample safety-bound return not proving feasibility; preserve all original guidance/resources.

- S1: [fjsp-baseline-repair-with-downtime-and-policy/SKILL.md](tasks/manufacturing-fjsp-optimization/source/fjsp-baseline-repair-with-downtime-and-policy/SKILL.md) — Incorporate the shared baseline-repair context. Keep integer scan and same-order commitment explicit. Flag conflicting heuristic priorities and the sample safety-bound return not proving feasibility; preserve all original guidance/resources.
- S2: [reference.md](tasks/manufacturing-fjsp-optimization/source/reference.md) — Shared skills-root resource: baseline-repair commitments, FJSPLib provenance, difficulty taxonomy and literature. No instance-specific solution is supplied.

