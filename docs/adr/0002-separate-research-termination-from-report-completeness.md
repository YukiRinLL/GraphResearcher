# 分离研究终止、报告授权与内容完整度

状态契约 v2 将 Objective 的搜索终止、全局报告授权和报告内容完整度建模为三个独立概念：Objective 使用 `open`、`satisfied`、`blocked`、`deferred`，有限交付使用独立的 `LIMITED_REPORT_READY`，Report Completeness 仅作为 must objectives 的质量指标。Reporter 可以根据完整或有限交付模式约束写作，但内部停止原因不得成为读者可见内容；这一拆分避免被阻塞的目标再次被误算为已满足并提前授权完整报告。
