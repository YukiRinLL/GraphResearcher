# 为状态契约 v2 清空当前研究上下文

状态契约 v2 不兼容迁移旧的研究状态。实施切换时清空当前 Neo4j run context，并让后续运行只生成 v2 数据；不改写同库其他 context，也不删除历史报告和导出文件。这样避免把旧 `blocked_best_effort` 与 `report_readiness_score` 静默解释为新语义，代价是当前 context 中尚未交付的研究进度不会保留。
