# Reporter 共享读取视图

## 目标与授权

用户已于 2026-10-04 确认本计划。本里程碑只实施 Reporter 一次读图、共享引用表和修正分页停止；验收完成后停止，不进入其他性能或业务语义改造。

## 已确认决策

- Reporter 获得授权后，从当前 Neo4j context 各读取一次完整节点和边，建立本次报告专用的 `ReportReadView`。
- 视图保存节点字典、入边和出边索引、完整引用表及 Query 证据投影缓存，通过内部参数传递给上下文导出、组包、确定性草稿和最终编译。已有写作重试复用同一视图。
- 引用表构建一次；每个 Query 的完整投影最多生成一次。分页只切片，返回值不得让调用者修改缓存。
- 单 Query 预算放不下下一条证据时结束该 Query；全局预算放不下时结束 findings 收集。重复证据不消耗预算。预算截断采用当前排序下的连续前缀。
- 视图不跨 run/context 复用，不形成进程级缓存。独立调用没有共享视图时读取新的数据。

## 非目标

本次不修改 Claim 规范化、恢复 owner、portfolio、来源抽取并发、模型配置或完整 prompt 预算，不压缩或移除 `draft_report`。不修改图节点字段、枚举、状态机、报告提交 shape、引用绑定与交付校验规则，也不迁移已有图数据。

## 行为不变量与兼容策略

Neo4j 继续作为事实来源，JSONL 只用于离线验证。一次读图指证据全图加载，不包括授权检查和报告持久化；节点与边的两次查询不承诺事务级原子快照。报告阶段研究证据已经稳定，报告章节写入仍走原有同步存储边界。

完整证据投影、来源追溯、引用编号、Query 引用解析和确定性草稿保持既有规则。模型工具参数与返回结构保持一致。预算停止修复可能改变边界附近的 findings，必须独立验证，不能以整个 packet 完全相同作为该项验收条件。

## 实施步骤

1. 建立小型图 fixture，保存优化前的投影、引用表、草稿和编译结果，并补充读取次数及预算边界回归。
2. 提取可接收内存数据的 Query resolver 和评估子图 helper，实现内部读取视图及纯投影。
3. 将视图显式贯穿 Reporter 上下文、组包、重试和引用编译，修正分页停止。
4. 运行定向回归和 Ruff，并用样本 17 快照离线比较输出、读取次数与耗时。

## 验收标准

- 共享 Reporter 证据路径只执行一次 `get_all_nodes` 和一次 `get_all_edges`，引用表只构建一次，分页不触发逐节点数据库读取。
- 同一快照的完整证据投影、引用表、来源关系、确定性草稿和固定正文的编译结果一致。
- 单 Query/global 预算不足、首条过大、恰好达到预算、重复证据以及正常跨页均有回归。
- 不同 context 的视图相互隔离，调用方修改返回结果不会污染缓存。
- 报告编译、落盘、写作重试和最终交付路径通过定向回归。样本重放只访问导出的快照，不调用模型或真实数据库。

## 验证命令

```bash
uv run python tests/test_report_read_view.py
uv run python tests/test_reporter_global_workflow.py
uv run python tests/test_report_context.py
uv run python tests/test_query_handles.py
uv run python tests/test_report_delivery.py
uv run python tests/test_report_validation.py
uv run python tests/test_reporter_artifact_persistence.py
uv run python tests/test_reporter_replay.py
uv run python tests/test_graph_invariants.py
uv run python tests/test_tree_state_machine.py
uv run ruff check src tests main.py test_wlc.py
```

## 基线与进展

- 修改前，`test_reporter_global_workflow.py`、`test_report_context.py`、`test_query_handles.py` 和 `test_report_validation.py` 通过。
- 修改前，`test_report_delivery.py:164` 因上下文 key 集合与当前实现不一致而失败；本里程碑不放宽该断言。
- 修改前，`test_reporter_artifact_persistence.py` 在 `commit_report_chapter_batch` 读取缺失的 `analysis_refs` 时失败；本里程碑不修复该既有章节路径问题。
- 四个实施步骤均已完成。本里程碑验收结束，未进入非目标范围。
- 新增的 `test_report_read_view.py` 共九项回归全部通过，覆盖固定图的优化前结果、共享读取、缓存副本隔离、context 隔离、Query 引用解析、分页预算、独立调用重新加载，以及真实编译与落盘路径。写作重试使用假模型，第一次无效引用被拒绝，第二次成功，并通过 `main.py` 的最终交付检查。
- `test_reporter_global_workflow.py`、`test_report_context.py`、`test_query_handles.py`、`test_report_validation.py` 和 `test_reporter_replay.py` 的独立脚本通过。另逐项调用全局 Reporter 测试文件中的八个测试函数，七项通过；`test_task_requirements_extract_explicit_structure` 对标题提取的预期失败，已在 HEAD 原始代码上复现。
- 扩展回归发现另外两项既有失败，也已在 HEAD 原始代码上复现：`test_graph_invariants.py:62` 未拒绝测试中的非法 Query 状态迁移；`test_tree_state_machine.py:258` 期望选中两个 gap，实际因冷却得到空列表。连同上面的交付、章节持久化和标题提取问题，共有五项既有失败，本里程碑未修改这些规则或测试预期。
- 全仓 Ruff 仍报告 217 项问题，其中包括仓库不存在 `test_wlc.py` 的 E902。按文件、规则和消息与 HEAD 比较，五个改动源码文件没有新增问题，已有问题从 24 项降为 23 项；新增回归文件和 `memory_manager.py`、`reporter_global_workflow.py` 的定向 Ruff 检查通过。

## 样本 17 的离线验证结果

验证读取 `outputs/evaluations/drb1/deepseek-v4-pro/samples/deep_research_bench/17/research_graph.jsonl`，用假存储边界计数，不调用真实 Neo4j 或模型。优化前先保存完整输出，优化后比较引用表、报告上下文、全部 Query 证据页、确定性草稿和固定正文的编译结果，五类结果均完全一致。

优化前的组包路径触发 426,898 次图读取，其中 `get_node` 为 315,204 次，`get_node_edges` 为 111,272 次。优化后的冷启动视图加载、上下文导出和组包总计约 0.086 秒，只触发一次 `get_all_nodes` 和一次 `get_all_edges`；findings 为 219 条，草稿为 106,416 字符，prompt 为 259,687 字符。此前优化前的同类内存组包耗时约 7.6 秒。

这些时间用于说明离线计算与调用次数的变化，不能直接作为真实数据库的端到端提速比例。实际运行仍包含节点和边两次数据库查询、模型写作与报告持久化；原日志中约 1,995 秒的组包耗时尚未在真实数据库环境下复测。
