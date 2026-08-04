# Schema-style Harness 实验汇报页

本页以实验报告口径汇总 `arc-schema-reproduction` 的实现迭代和真实实验结果，重点展示：

- Full Schema harness 与 batched direct baseline 的最终同上限对照；
- 四级证据口径、实验系列概览和 28 条代表性运行登记；
- 从 FSM、Program WM、B4/B5 到 Codex C1/C2 的设计变更；
- Full run 中基于 notes、hypotheses、world model 和真实行动结果整理的外显理解修订；
- `ls20` L1–L3 的真实视觉帧和颜色/对象角色说明；
- Harness 动作协议、工程审计、当前结论边界和下一步确认性实验。

基础设施失败、协议失败和空结果目录单列，不计入能力统计。

页面不展示或虚构模型不可见的私有 chain-of-thought。页面中的“理解修订”仅来自实验中实际保存、可复核的外部产物。

从仓库根目录启动任意静态文件服务后，访问：

```text
/docs/harness-results/
```

页面不依赖外部库或网络资源，可直接静态托管。

`evidence/` 保存了页面引用的两组 `experiment.json`、Full harness 最终 notes 和 trace index 副本；它们来自只读实验产物，便于页面独立托管时继续核验。
