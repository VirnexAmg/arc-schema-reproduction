# 术语

- **真实环境动作**：实际提交给 ARC `env.step()` 的动作。模型调用和 world
  model 内搜索均不计入。
- **模型调用**：一次 agent 发起的逻辑请求；同一次请求内的网络重试另计为
  **API attempt**。
- **observation snapshot**：去除 GUID、触发动作等非状态字段后的确定性状态，
  包括游戏状态、关卡进度、合法动作和最后一帧 RLE。
- **world model**：模型输出的确定性有限状态机，不是 Python 代码。
- **backtest**：将真实历史 transition 按顺序送入 world model，严格比较每个
  预测 snapshot；返回第一个不一致。
- **prediction mismatch**：计划动作提交真实环境后，实际 snapshot 与规划时的
  目标状态不完全一致。发生后剩余计划立即作废。
- **score**：直接读取 ARC scorecard 的 run score；mock 环境使用明确的玩具分数。
- **完成**：整局状态为 `WIN`；`levels_completed` 单独记录。
- **tamper-evident**：修改已有日志会破坏哈希链，但不声称能阻止拥有文件写权限
  的攻击者重建整条链。
