# 复算结果

负号表示图片组更低；token=input+output，缓存输入不重复相加。超时保留原生失败和实际已记录消耗；其用量可能不完整。

|版本|任务结构代理|得分 文/图|token 文→图|变化|工具 文→图|秒 文→图|估算费用变化|配对|
|---|---|---|---|---:|---|---|---:|---|
|v1|前缀缓存：状态迁移／策略比较|1/1|68,624→77,396|+12.8%|5→4|12.0→17.2|+19.5%|同分通过|
|v1|电价分析：数据契约／网络约束／数值优化|1/1|718,480→703,491|-2.1%|25→22|232.5→387.8|+16.4%|同分通过|
|v1|R2R 控制：数学递推／反馈控制／参数权衡|1/1|1,021,273→2,071,916|+102.9%|31→40|509.1→649.2|+40.9%|同分通过|
|v1|考试排程：有序窗口约束／求解交付|1/0|1,734,749→1,766,242|+1.8%|38→35|722.7→1500.1|+10.5%|超时／证据不全|
|v1|制造排程：时序资源约束／局部修复|0/1|703,904→639,778|-9.1%|23→26|340.7→1294.5|+2.2%|异分完整|
|v2|前缀缓存：状态迁移／策略比较|1/1|67,276→61,117|-9.2%|4→3|10.4→9.0|+1.3%|同分通过|
|v2|电价分析：数据契约／网络约束／数值优化|1/1|1,534,634→366,785|-76.1%|38→14|595.4→127.9|-73.6%|同分通过|
|v2|R2R 控制：数学递推／反馈控制／参数权衡|1/0|516,242→172,688|-66.5%|21→10|132.2→51.3|-57.1%|异分完整|
|v2|考试排程：有序窗口约束／求解交付|0/0|2,808,117→997,719|-64.5%|50→21|1500.1→1500.1|-37.0%|超时／证据不全|
|v2|制造排程：时序资源约束／局部修复|1/1|325,994→746,114|+128.9%|15→26|494.1→377.4|+28.1%|同分通过|
|crystal-v1|晶体分析：大型 API 参考／任务入口|1/1|491,396→161,328|-67.2%|19→8|64.6→15.7|-64.0%|同分通过|

## 聚合口径

|版本|配对子集|n|token 文→图|合计变化|逐任务变化中位数|
|---|---|---:|---|---:|---:|
|v1|all_recorded|5|4,247,030→5,258,823|+23.8%|+1.8%|
|v1|complete|4|2,512,281→3,492,581|+39.0%|+5.3%|
|v1|both_pass_complete|3|1,808,377→2,852,803|+57.8%|+12.8%|
|v2|all_recorded|5|5,252,263→2,344,423|-55.4%|-64.5%|
|v2|complete|4|2,444,146→1,346,704|-44.9%|-37.9%|
|v2|both_pass_complete|3|1,927,904→1,174,016|-39.1%|-9.2%|
|crystal-v1|all_recorded|1|491,396→161,328|-67.2%|-67.2%|
|crystal-v1|complete|1|491,396→161,328|-67.2%|-67.2%|
|crystal-v1|both_pass_complete|1|491,396→161,328|-67.2%|-67.2%|

both_pass_complete 是事后条件描述，不是无偏处理效应；不能通过筛掉失败得出有效率的结论。

## 同样文字包的跨轮波动

|任务|文字 token v1→v2|文字得分 v1→v2|图像 token 效应变号|
|---|---:|---|---|
|前缀缓存|-2.0%|1→1|True|
|电价分析|+113.6%|1→1|False|
|R2R 控制|-49.5%|1→1|True|
|考试排程|+61.9%|1→0|None|
|制造排程|-53.7%|0→1|True|

## 13 个 skill 的结构标注与图面指标

activity/if/loop 仅统计 PlantUML 语法语句；不等于渲染节点／边数，也不等于内容保真度。

|skill|结构|原文 bytes|PNG 宽×高|活动/条件/循环|候选主图＋辅图|
|---|---|---:|---|---|---|
|prefix-cache-replay|state_transition|9,283|708×2151|12/4/3|state_machine＋event_sequence|
|cache-policy-comparison|decision|5,970|601×1516|10/4/1|decision_table＋state_machine|
|power-flow-data|data_contract|4,367|796×893|7/0/0|schema_map＋mapping_table|
|dc-power-flow|data_contract|2,882|818×1457|13/2/1|dataflow＋equation_card|
|economic-dispatch|mathematical_dependency|4,932|1611×1287|10/4/0|constraint_graph＋equation_card|
|locational-marginal-prices|mathematical_dependency|4,746|778×1158|9/0/0|dataflow＋unit_contract|
|state-space-linearization|mathematical_dependency|1,018|1026×1009|9/3/0|equation_dependency＋equation_card|
|finite-horizon-lqr|mathematical_dependency|1,078|832×881|5/0/2|indexed_recurrence＋feedback_block|
|mpc-horizon-tuning|decision|1,197|1011×841|6/1/0|tradeoff_table＋validation_cycle|
|integral-action-design|feedback|1,104|653×1178|9/2/1|feedback_block＋validation_cycle|
|mip-solver-and-solution-audit|audit|10,797|803×2081|16/3/0|artifact_gate＋activity|
|ordered-window-sequencing-mip|temporal_constraint|10,905|1024×1539|12/1/0|window_timeline＋constraint_graph|
|fjsp-baseline-repair-with-downtime-and-policy|temporal_constraint|4,824|975×2268|14/1/2|resource_timeline＋invariant_checklist|
