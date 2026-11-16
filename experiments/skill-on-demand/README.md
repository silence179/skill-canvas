# 按需加载 skill 的输入协议

后续实验入口为 `runner.py`，协议名 `skill-on-demand-v1`。本目录独立于历史 `forced-prefix-v1`：没有覆盖旧材料、评分或调用轨迹。

## 输入行为

1. 开始时保留 OpenCode 原生输入：任务、工具定义及可用 skill 的目录信息。实验层不添加任何 skill 正文或图。
2. 模型自行调用 `skill({name: ...})`，由 OpenCode 读取原始 `SKILL.md`，返回正文、目录和配套文件路径。YAML 元信息用于目录发现，正文进入工具结果。
3. 文字组保留这个工具结果原样；图片组仅为该次成功加载的 skill 附加对应 PNG，与正文一起供下一次模型请求使用。不加载其他尚未调用的 skill。
4. 对 OpenAI-compatible 接口，图像作为紧接完整工具结果批次的多模态消息传输，并绑定 skill 名及 tool_call_id。它不是开场 user prompt，也不伪造模型工具调用。并行调用时先收齐该批全部工具结果，防止打断调用与结果配对。
5. 之后按正常历史回放这些结果和附件，每个已加载调用只有一个附件位置；不会逐轮追加新副本。历史经压缩后，消失的工具结果不会因为摘要提到 skill 而重新注入。

这是代理层的多模态传输适配，原生 `skill` 工具本身和选 skill 的逻辑没有改写。OpenCode 本身也会为不支持工具结果内媒体的提供方，把工具附件转成随后的一条媒体消息；本实现选择相同的传输边界。

原始 `SKILL.md` 逐字节保留，不再改成“去读 GUIDE.md”的入口。脚本、参考文件、共享资源保留；不是把整个资源目录展开进模型上下文。Agent 主动读取额外文件仍属于原生行为。没有调用 skill 是允许的结果，审计单列 `no_activation`，不因没有看图就剔除该运行。

## 材料与入口

可选择原 v1 UML、完整资源 v2 UML 或本次结构图 v3。这里只复用已有 PNG，不重新画图。v3 中未重画的 skill 延用 v2 背景图；晶体仅有原 v1 图。文字组和图片组的原始 skill 文件及资源一致，图片组只多对应 PNG。

离线预览，不启动 Docker、模型或评分器：

```bash
repos/benchflow/.venv/bin/python experiments/skill-on-demand/runner.py \
  --task r2r-mpc-control --arm image --figures uml-v1 --dry-run
```

未来获得新的运行授权后，使用新的空结果目录运行；不能用本协议续跑旧协议的 jobs：

```bash
repos/benchflow/.venv/bin/python experiments/skill-on-demand/runner.py \
  --task r2r-mpc-control --arm text --jobs-dir jobs/skill-on-demand-v1/r2r/text
repos/benchflow/.venv/bin/python experiments/skill-on-demand/runner.py \
  --task r2r-mpc-control --arm image --figures uml-v1 \
  --jobs-dir jobs/skill-on-demand-v1/r2r/uml-v1
```

同一固定 OpenCode 1.19.5、公共工具镜像、模型路由、任务环境及原生评分逻辑继续使用；只更换 skill 传递协议和恢复原始入口文件。历史强制全文结果不能作为新协议下的直接配对对照。

## 验证范围

`test_protocol.py` 检查未激活时不注入、只返回已调用 skill、失败调用不加图、并行结果边界、历史不累积、压缩后不复活、正文完整性、错误附件拒绝、原生代理预算检查保留，以及零激活运行不被排除。

`wire_smoke.py` 使用真实 BenchFlow callback 和 LiteLLM 序列化，向本机假接口发送请求。覆盖六任务及可用的三套图，包括每个 skill 的逐次激活。保存 `wire-check.json`，不调用外部模型，也不跑任务或评分器。**skill 工具结果是遵循固定版本源码的模拟数据；这不等于完成了真实 OpenCode 进程与服务商的端到端验证。**

参考固定版本源码：[skill 工具返回格式](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/skill.ts)、[工具媒体的提供方适配](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/session/message-v2.ts)。

```bash
LITELLM_LOCAL_MODEL_COST_MAP=True repos/benchflow/.venv/bin/python \
  -m unittest discover -s experiments/skill-on-demand -p 'test_*.py' -v
LITELLM_LOCAL_MODEL_COST_MAP=True repos/benchflow/.venv/bin/python \
  experiments/skill-on-demand/wire_smoke.py
```
