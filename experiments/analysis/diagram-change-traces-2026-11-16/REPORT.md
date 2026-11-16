# 换图后的效果与执行轨迹对比

本报告只读取已保存结果、模型请求、工具轨迹和输出文件，未启动任何新实验、求解器或模拟器。实验保持停止。

本轮可用证据是 9 个完成的唯一运行，形成 6 个对比；同一评测环境的多行共用当轮旧图控制。考试运行被用户中断，没有原生结果；制造运行没有启动。不能把二者计作新图失败。

结论需要分成三项：原生分数没有下降；效率多数下降；保存输出中存在评分器漏掉的电价符号退化，而 LQR 的保存日志显示控制误差改善。

## 1. 量化对比

以下均为旧图→新图，token 为含缓存输入的累计请求用量，耗时为 Agent 阶段秒数。费用另见完整对比表。

|被替换的 skill|新图表示|分数|总 token|token 变化|Agent 秒|主请求次数|保存输出补充检查|
|---|---|---|---|---:|---|---|---|
|prefix-cache-replay|状态机|0→1|59,319→77,953|+31.4%|11.1→12.2|4→5|参数化用例 7/10→10/10；频率状态更新正确|
|dc-power-flow|数据依赖图|1→1|301,688→599,951|+98.9%|112.9→300.1|12→20|每场景 510 个母线电价与旧图恰好反号；已有扰动检查支持符号问题|
|economic-dispatch|变量约束图|1→1|301,688→1,228,703|+307.3%|112.9→474.8|12→33|两场景所有电价与旧图一致至保存精度；未见对应最终收益|
|locational-marginal-prices|双场景依赖图|1→1|301,688→345,759|+14.6%|112.9→127.7|12→14|与 DC 新图一样，两个场景各有 510 个母线电价反号|
|finite-horizon-lqr|索引递推图|1→1|485,971→1,003,861|+106.6%|113.5→432.1|18→25|统一 4–5 秒误差 0.2272→0.0316 N；最终控制参数文件与旧图内容相同，新增状态估计|
|finite-horizon-lqr + integral-action-design|递推图 + 反馈框图|1→1|485,971→654,085|+34.6%|113.5→133.6|18→20|统一 4–5 秒误差 0.2272→0.0913 N；无法拆出两张图各自贡献|

[完整计量表](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/COMPARISON.md)；[可复算数据及原始文件哈希](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/comparison.json)。9 个完成运行的既有证据哈希重新核验通过。本文不将原生通过等同于完整语义正确。

## 2. 电力相关 skill：同一处单位问题，走出了三种不同路径

### 旧图控制：修正单位和方向，较快结束

旧图运行在 T06–T07 写出并运行第一版求解程序，也先采用了源文档的 `dual * baseMVA` 示例。T08–T09 检查线性成本、约束对偶与发电机边际成本，随后在 T10 把电价改为 `-dual / baseMVA`，T11 重跑，T12–T13检查输出后结束。

它采用统一的向量化节点平衡 `G @ Pg - Pd_pu == B @ theta`，所有母线的等式方向一致，最终结果与后续 HiGHS 及已有负荷扰动检查吻合。

[旧图执行轨迹](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/energy-market-pricing__baseline.md)。

### economic-dispatch 新图：反复确认，最后重新实现求解器

T05–T06 第一版同样出现百万数量级的电价，而最优成本已经接近最终值。T09 用负荷增加 1 MW 的成本差，发现示例电价高了约 10,000 倍；T13再次确认单位，T14修正单位。随后 T16 发现部分母线仍然反号：母线 9 报告 -32.33，已有扰动成本差却为 +32.33；母线 1266、1709 也类似。

T19–T24连续做小模型、对偶方向及标准形检查；T26–T28重新写了一套 SciPy/HiGHS 线性规划；T29–T31逐点及抽样复核，T32结束。由此主请求从 12 增至 33，工具从 13 增至 32。

这些检查帮助该次运行摆脱了自己的错误，但相对旧图，保存结果中的两场景总成本和全部 2,869 个母线电价均相同至保存精度。因而此处主要是更昂贵的纠错路径，不能把额外检查自动算成相对旧图的质量收益。

[T16：反号与有限差分矛盾](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/energy-market-pricing__economic-dispatch.md:822)；[T24：等式方向小模型](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/energy-market-pricing__economic-dispatch.md:1253)；[T29：更换求解器后的交叉检查](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/energy-market-pricing__economic-dispatch.md:1497)。

### dc-power-flow 新图：先误诊为数值病态，最终只修正了量级

T07 已经得到接近最终的总成本，但价格量级异常。T08–T16继续检查网络连通性、角差约束重写、正则化强度以及小型对偶模型。T11还用状态为 `optimal_inaccurate` 的变体做敏感性对比，进一步放大了对数值病态的怀疑。T12、T14尝试多种正则化仍无助于单位错误。直到 T17 才将电价从乘 `baseMVA` 改为除 `baseMVA`。

最终程序 T17只对母线 1、64、629做负荷扰动检查；这三者均不含发电机，检查通过。但程序逐母线构造平衡等式，对于有发电机的母线，左侧是优化表达式；没有发电机时，空求和退化为数值常量。对偶方向因此不能用未经归一的同一符号直接套用。它统一采用 `+dual / baseMVA`，漏掉了发电机母线的符号问题。

保存输出显示，两个场景各有 **510/2,869（17.8%）** 个母线电价与旧图恰好反号；这些母线的集合恰好等于全部发电机母线集合。母线 9、1266、1709 的反号与上面 economic-dispatch 运行中已有的扰动证据一致。这里不能用“多重最优解的自然差异”解释这个与表达式类型完全对齐的符号模式。

[DC 新图轨迹](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/energy-market-pricing__dc-power-flow.md)。机制判断结合了保存代码、输出差异和同输入下已有扰动证据；本报告没有重新求解整个网络，也没有单独对每个母线做新扰动验证。

### locational-marginal-prices 新图：更快纠正量级，同样漏掉分类覆盖

T08出现异常电价，T10–T11只选母线 1、64、1501进行扰动检查，T12–T13修正量级，T14–T15检查报表后结束。这三个抽样母线也均不含发电机，因此没有触发另一类等式的符号问题。保存结果与 DC 新图一样，在每个场景的 510 个发电机母线上反号。

这解释了“为什么多花 token 还会输出更差”：额外检查没有覆盖造成错误的结构分支，检查数量多并不等于覆盖完整。

[LMP 新图轨迹](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/energy-market-pricing__locational-marginal-prices.md)。

### 为什么评分器没有表现出来

现有评分器检查结构、成本差与 delta 的内部一致性、最优成本和松弛约束后成本不增加，并明确不逐个比较 LMP。电价全部统一缩放或部分反号，仍可能满足它检查的项目。四次电力运行都得到 1 分，不代表四份价格表质量相同。

[原评分器](/home/silence/myfiles/SkillCanvas/.runtime/uml-expanded/prepared-tasks/energy-market-pricing/verifier/test_outputs.py:1)。

## 3. LQR：大量调参导致效率下降，但保存的控制轨迹改善

旧图运行 T05–T15做原型和权重／预测长度搜索，T16写最终控制器，T17–T18运行并检查结果。它直接使用带噪声的测量做反馈，增加泄漏积分。

LQR 单图运行 T08–T24反复搜索权重、滤波器噪声、积分系数、参考斜坡及切换方式；T06有一次 `python` 命令缺失，T15有一次辅助脚本 `KeyError`，但主要耗时并非这些小错误。仅 T22 的精细搜索就有 `4×5×5=100` 组参数，每组 5 个种子，共 500 次本地模拟，工具执行约 81.8 秒。这些是该次 agent 自行进行的调参模拟，并非 500 次独立 benchmark 重复。

该运行早期已经使用 Riccati 递推；T25再做终端代价和 horizon 验证。因此不存在“新递推图让 agent 不会写 Riccati 公式”的证据。最终 `controller_params.json` 与旧图解析后的内容完全相同；实现的主要差别是状态估计和去掉积分，收益更多来自噪声处理路径。

[T08：初版已经使用有限时域递推](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/r2r-mpc-control__finite-horizon-lqr.md:472)；[T22：100 组 × 5 种子的搜索](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/r2r-mpc-control__finite-horizon-lqr.md:1198)；[T25：终端代价比较](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/r2r-mpc-control__finite-horizon-lqr.md:1439)。

组合图运行走了较短的开发路径，在 T04–T11测试控制和滤波，T12–T15修正状态估计的更新／预测顺序，T16–T20生成输出并验证。它用了 20 次主请求，远少于单图的 25 次，耗时 133.6 秒，也明显低于单图的 432.1 秒。组合图相对旧图仍更贵，但不能据此认为加入积分框图已被证明“抵消了”递推图的负面作用：每种配置只有一次，开发路径本身有随机性。

[组合图轨迹](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/r2r-mpc-control__combined.md)。

三次运行原先各自报告的稳定时间使用了不同误差带，时长也分别为 5、8、6.2 秒，不能直接横比。因此从保存日志重新计算共同的 0–5 秒区间：

|运行|4–5 秒各节平均绝对误差 N|2N 带稳定时间 s|2% 带稳定时间 s|最高张力 N|
|---|---:|---:|---:|---:|
|旧图|0.2272|1.17|4.45|45.0471|
|LQR 单图|0.0316|0.73|1.23|44.0123|
|LQR + 积分组合图|0.0913|1.02|1.14|43.9764|

稳定时间从 0.5 秒阶跃起算，要求此后至共同观察窗末端持续在带内；2% 带取每节 `max(0.1 N, 2%×最终参考张力)`。这些是单次已保存轨迹的描述，不是重新验证控制器的独立多种子结果。

因此 LQR 的恰当描述是“以更长的调参过程换到了更平滑的这一次控制轨迹”。仅比较原生 1 分或原先不同定义的 metrics，会把这部分收益漏掉。

## 4. 缓存 skill 是反例：明确的状态语义对应了一处实际修正

旧图运行 T02把驻留队列 `S/M` 的频率存成队列值，同时额外维护 `freq` 字典。命中时只更新字典，淘汰时却从队列值读频率，因而读到陈旧值。最终 hit_tokens 为 2,394,147，final_cache_blocks 为 2,527。

状态机图运行 T03在命中时同步更新 `S[h]` 或 `M[h]`，淘汰时能读到正确值。最终 hit_tokens 为 2,394,659，final_cache_blocks 为 2,535，参数化用例由 7/10 到 10/10。旧 CTRF 表按测试名归并成 3/6 和 6/6，不能与实际用例数混用。

状态机上明确标注驻留状态、freq 更新、迁移时保留 freq，和这次代码差异相吻合；这支持它是一个值得保留的候选，但单次结果仍不能证明图本身必然防止该 bug。

[旧图缓存轨迹](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/llm-prefix-cache-replay__baseline.md)；[新图缓存轨迹](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/llm-prefix-cache-replay__prefix-cache-replay.md)。

## 5. token 增加的直接机制：轮次增加与历史累积

最大退化的 economic-dispatch，首次主请求输入是 **16,273→16,264 token**，没有增加；主请求次数却从 **12→33**，最后一次输入从 **31,872→60,586**。新图本身的首次编码开销不能解释累计 token 增加 307%。

LQR 单图首次输入仅 **12,019→12,248（+1.9%）**，主请求 **18→25**，最后输入 **40,338→73,839**。总输入从 467,725 到 974,776，输出从 18,246 到 29,085。工具脚本和结果进入历史后，每个后续请求又携带增长的上下文，这会放大调参和排错的成本。

新图确实更宽、面积更大：DC 约为旧图 2.00 倍面积，LQR 1.48 倍，economic-dispatch 仅 1.14 倍。然而面积与最差 token 增长不对应，且服务商没有单独报告可用图像 token。宽图缩放可能影响可读性，但本轮没有测量到足以将其确认为主因的证据。

所有完成运行的图像／全文传递检查通过，框架记录的 provider_retry_wait 均为 0。未发现材料漏传或重试风暴能解释这些差异。计量中包含缓存 token，不能等同于新增计费用量：例如 LMP 新图总 token 增加 14.6%，框架费用估算仅增加 0.3%；economic-dispatch 费用估算增加 191.7%，小于总 token 的 307.3%。费用估算不是供应商账单。

## 6. 本次选图有什么不足，能归因到哪一层

可以确认的直接原因，是实现路径、单位／方向错误、检查覆盖不足、参数搜索以及反复携带历史。**不能确认这些路径为什么一定由某一图型引发。** 同轮控制、源文档、模型和框架保持一致，但每个变体仅一次，没有固定温度／随机种子来分离随机路径差异，也同时改变了摘要重点、版面和图像面积。

这次选图的不足，是把“skill 的知识结构适合用什么表示”放在前面，没有把“原来的执行顺序与验证关口必须保留”当成同等强的条件。

一个可见例子是 LMP：旧流程图把“检查等式方向和单位，再应用源示例”放在主路径；新依赖图在价格节点中直接出现 `dual*baseMVA`，而检查方向／单位放在旁注。源文档本身已有该不一致示例，新旧图都有保留，但新的视觉层级可能让错误示例更突出、检查更弱。这是图设计层面的可检验解释；不能从传递记录推断模型实际看了哪个节点。

同样，LQR 的递推依赖图较清楚地表达了索引关系，却没有为该次运行的主要瓶颈——噪声处理、调参范围和验证口径——带来直接收敛帮助。该瓶颈仍需 agent 自行识别。这不说明需要根据具体 task 反向画图，而说明单靠“知识类型→图型”映射不足以保证执行效率。

当前判断：缓存状态图有一次正向证据；DC/LMP 新图应记录为“更贵且存在保存输出的符号退化”；economic-dispatch 新图是“更贵、最终未见对应收益”；LQR 是“更贵、保存轨迹更平滑”。这些结论比“流程图最好”或“换图都变差”更符合现有证据。本轮没有新增无图组，因此也无法由此判断哪些 skill 去图会更好。

## 7. 已中断的考试轨迹只用于定位问题

考试运行留下 37 个工具调用、32 个带用量的主请求，但没有原生结果。轨迹中先后出现模拟退火的撤销操作错误、前置大块限制漏掉、C 编译问题、浮点异常，以及候选序列退化为同一块重复 24 次。这些是中断前的具体问题，不能推成最终成绩。

例如 T24 的候选目标 3,772 但前置限制检查为 False，T25 得到可行候选 4,049；之后的 C 搜索在 T36–T37打印目标 0、重复块序列。这说明候选表示／排列不变量的维护出现问题，没有证据证明是窗口图导致，也没有完成的新旧成绩可比较。

[T24–T25：可行性修复](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/exam-block-sequencing__combined.md:1658)；[T36–T37：重复块候选](/home/silence/myfiles/SkillCanvas/experiments/analysis/diagram-change-traces-2026-11-16/traces/exam-block-sequencing__combined.md:3225)。

分析过程仅生成本目录的报告、离线计量和去重轨迹摘录。没有修改被冻结的图、任务、评分器或实验逻辑，没有恢复或追加实验。
