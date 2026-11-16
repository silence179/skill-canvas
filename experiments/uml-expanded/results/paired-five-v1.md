# 五任务 UML 辅助 skill 初步对照

状态：全部槽位已结束；正常结束 7/10；可纳入完整配对计量 3/5。

模型 `deepseek/deepseek-flash`，OpenCode 1.19.5；每任务每组 1 次。两组均强制全文，image 组额外提供 PNG。13 张图已逐资源核验。

尚在收集可评分结果。

| 任务 | 得分 文/图 | 工具调用 文→图 | 总 token 文→图 | token 变化 | Agent 秒 文→图 |
|---|---|---|---|---|---|
| 前缀缓存回放 | 1.0/1.0 | 5→4 | 68624→77396 | +12.8% | 12.0→17.2 |
| 电价与拥塞分析 | 1.0/1.0 | 25→22 | 718480→703491 | -2.1% | 232.5→387.8 |
| R2R 控制器 | 1.0/1.0 | 31→40 | 1021273→2071916 | +102.9% | 509.1→649.2 |
| 考试排程 | 未评分/未评分 | 0→37 | 0→1968011 | 未纳入 | None→None |
| 制造排程修复 | 1.0/0.0（测试未执行） | 29→24 | 732630→757353 | 未纳入 | 359.4→538.4 |

总 token 包含辅助标题请求；缓存命中已在输入内，不能再相加。表中变化为图片组相对文字组，负数表示减少。基础设施错误、未完成或证据不完整的行保留，计量纳入条件另列于 JSON。

## 实验材料与过程

- [13 张图、UML 与原文索引](../FIGURES.md)
- [准备和运行说明、环境适配](../README.md)
- [独立图片识读检查](vision-sanity.json)：同一路由仅给两张 PNG，不给原文，三个空间定位和文字问题均正确；只验证基本识图能力，不计入 benchmark 成绩。
- [原始 campaign 与比较结果](/home/silence/myfiles/SkillCanvas/jobs/uml-expanded/paired-five-v1/comparison.md)

只有两组都完成评分、传递检查通过、原始 usage 与汇总相符且 task digest 与健康参考解一致的配对才纳入。传递检查核对任务请求中 PNG 与全文的顺序和哈希；通过能证明图片被发送，不能证明模型注意或使用了图片。错误请求保留，不因重试后恢复就被删除。

制造任务的在线依赖启动曾超时，因此在该任务两组启动前适配为预装同版本工具与离线缓存。原评分脚本从创建日志目录开始的尾部、测试调用和 reward 分支逐字节一致，Python 评分断言和阈值也逐字节一致。参考解得 1，空输出得 0；具体修订和前后哈希留在 campaign。其余任务预装依赖，评分脚本不变。

首轮原始环境失败、后续修复与参考解尝试都保留；它们未计入模型通过率。部分较早模型试验与参考解计算重叠，因此时间数据只作观察，不是严格的性能基准。

## 如何解读

每任务只有一次对照，差异可能来自采样、推理和求解路径。通过率相同也可能存在评分上限效应。不能据此证明稳定的认知增强。下一轮应增加重复，并把图中同样的提炼步骤以文字提供给第三组，以区分总结内容与图像形式的作用。

详细逐请求/逐结果证据哈希、全部控制实验及限制见同名 JSON。

## 本轮观察

可纳入的 3 个配对合计：文字组 1,808,377 token，图片组 2,852,803 token（+57.8%）。这是这些任务的加权合计，容易受单个长轨迹支配，不代表平均任务或总体效应。

| 任务 | 任务模型调用 文→图 | 首请求输入 文→图 | 输出 token 文→图 | 缓存输入 文→图 | 估算费用 USD 文→图 |
|---|---:|---:|---:|---:|---:|
| 前缀缓存回放 | 5→5 | 11859→13260 | 2,046→2,778 | 55,040→62,080 | 0.00624684→0.00746748 |
| 电价与拥塞分析 | 26→22 | 13467→15718 | 20,167→24,512 | 676,736→655,360 | 0.034733916→0.04043226 |
| R2R 控制器 | 24→38 | 9819→11599 | 39,086→52,074 | 954,368→1,981,440 | 0.060975108→0.08589804 |

工具调用数作为这里的 step 指标；一次工具调用可能执行多个命令。首请求输入是各组第一次成功任务请求的输入量，包含不同入口说明，不能当作服务商单独报告的图片 token。输出 token 包含代码与回答等内容，不能直接视作推理质量。费用为框架记录的估算值，实际账单以服务商为准。强制全文/图片每轮重发可命中缓存，因此总 token 变化不等同费用变化。

- 考试排程未纳入完整配对：text: ACP error -32603: Internal error: litellm.InternalServerError: InternalServerError: DeepseekException - Cannot connect to host api.deepseek.com:443 ssl:<ssl.SSLContext object at 0x7f9092738050> [Connection reset by peer]. Received Model Group=runtime-deepseek-deepseek-flash
Available Model Group Fallbacks=None | provider unavailable (HTTP 500)；image: ACP error -32603: Internal error: litellm.InternalServerError: InternalServerError: DeepseekException - Cannot connect to host api.deepseek.com:443 ssl:<ssl.SSLContext object at 0x7fa7e7000050> [Connection reset by peer]. Received Model Group=runtime-deepseek-deepseek-flash
Available Model Group Fallbacks=None | provider unavailable (HTTP 500)
- 制造排程修复未纳入完整配对：text: ['experiment_fidelity/skill_delivery: provider rejected main call at line 1']；image: Native reward exists but no captured test execution; dependency bootstrap failure must not count as model quality.
