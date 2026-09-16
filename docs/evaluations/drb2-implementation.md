# DRB II 改造实现说明

本轮实现把 DRB II 交付要求映射到 GraphResearcher 现有的 Research Graph、Reporter 和确定性 compiler，
没有修改 Query 状态机或 Neo4j 的 NodeType/EdgeType 枚举。

## 默认链路

1. Query 可以携带 `target_components`、`target_sections`、`analysis_mode` 和
   `required_evidence_types`。
2. Reporter 前执行 fail-open 的 `run_analysis_pass()`，为需要分析的 Query 写入
   `Analysis(research_note)`，并绑定到 Evidence。
3. Reporter packet 保存 AnswerContract、ResearchNotes 和 component buckets。
4. 没有既有 outline 时，Reporter 根据 Query delivery metadata 创建默认章节 outline。
5. chapter bundle 只暴露章节 Query 的 evidence、ResearchNotes 和冲突；chapter commit
   拒绝未知 evidence、citation 或 analysis refs。
6. 最终验证通过后写入 `.report_commit_proof.json`，记录报告、章节和 citation registry hash。

## DRB II 适配

`src/tools/drb2_diagnostics.py` 提供纯函数 adapter：

- `project_drb2_task()` 将单个任务投影为通用 delivery metadata；
- `build_drb2_research_plan()` 生成 Objective/Query 计划草案；
- `load_drb2_tasks()` 读取 JSONL，不修改运行状态；
- `diagnose_packet()` 检查 objective、section、ResearchNotes 和 evidence gaps。

blocked URL 只进入 contract 和诊断结果，不会被重新访问或作为引用来源使用。

## 验证限制

本环境没有可用的 `python` 或 `uv` 命令，因此本轮只能执行静态 diff 检查；部署环境应运行仓库约定的
相关独立测试和 `ruff`。
