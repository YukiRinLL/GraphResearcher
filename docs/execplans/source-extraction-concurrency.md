# 来源并行抽取执行计划

## 目标与已确认决策

用户已确认在 Query 内并行抽取来源，并用进程内共享信号量限制所有 Query 的 analyzer 调用总并发。每个 Query 按实际来源数创建线程池，所有来源处理完成后按原始顺序合并，沿用完整证据包的一次提交路径。

评测 YAML 增加可选字段 `agent.source_extraction_concurrency`。显式配置必须为正整数，优先级为 YAML、根目录 `.env` 中的 `GR_SOURCE_EXTRACTION_CONCURRENCY`、内置默认值 3。配置在启动时读取；值为 1 时，进程内的来源模型调用串行。评测器通过子进程环境传递配置，直接运行 `main.py` 使用环境变量或默认值。

## 第一阶段的非目标与行为不变量

本次不改变 Query 派发并发、图谱 schema、Query 状态机、证据包字段、引用校验或数据库事务边界，也不增加运行时 YAML 加载入口和配置热更新。

- 抽取任务独立复制调用上下文，只返回自己的 packet；图写入仍由既有提交路径完成。
- 给定相同的抽取结果，合并顺序、引用编号和证据包内容与串行路径一致。
- 共享名额只覆盖 analyzer 模型调用，调用退出时自动释放，快照读取、合并和写图不占用名额。
- 抽取异常时取消尚未开始的任务，等待已开始的任务退出，再向上抛出；失败 Query 不提交部分证据包，继续走既有 `fail_search` 路径。
- 正常返回的空 packet 继续按现有规则处理；空来源不调用模型。
- 多进程各自限流，所有进程的总并发可能达到样本并发数乘以来源并发上限。

## 兼容策略与影响面

YAML 未填写新字段时不注入覆盖值，保留环境配置。显式填写 `null`、布尔值、小数、零或负数会在启动子进程前被拒绝。改动集中在 Searcher、runtime 配置、评测配置和子进程启动边界，以及示例和离线测试。

基线中 `tests/test_tavily_searcher_pipeline.py` 因短内容被现有过滤规则丢弃而失败，`tests/test_search_lifecycle.py` 因 `statement_refs` 不满足现有校验而失败。本次保留这些规则和断言，不将它们作为并发改造的一部分修复。流水线测试的顺序型模型替身需要按来源绑定结果，以避免并发调度改变测试输入与输出的对应关系。

## 里程碑一：来源并行抽取

完成并发抽取、共享限流和 YAML 传递，并通过离线测试验证：单 Query 并行、跨 Query 总上限、有序合并、上下文隔离、失败释放与不提交、成功只提交一次、空来源以及配置校验与优先级。使用同步事件和计数器验证并发，不以耗时阈值判断是否正确。

实现完成并达到验收标准后停止，不扩大到来源过滤修复、共享线程池或图谱事务改造。

## 验证命令

```bash
uv run python tests/test_source_extraction_concurrency.py
uv run python tests/test_evaluation_source_extraction_concurrency.py
uv run python tests/test_evaluation_config.py
uv run python tests/test_evaluation_model_retries.py
uv run python tests/test_evidence_locations.py
uv run python tests/test_tavily_searcher_pipeline.py
uv run python tests/test_search_lifecycle.py
uv run ruff check src tests main.py test_wlc.py
```

## 执行记录

已完成上述单一里程碑。Searcher 在来源数为零、一个或上限为 1 时使用直接调用路径，其余情况按实际来源数创建线程池；所有路径共用同一个 analyzer 信号量。正常返回的空 packet 沿用合并规则。合并函数、提交节点和 MemoryManager 写图实现均保持原样。

以下六个独立回归脚本通过：`test_source_extraction_concurrency.py`、`test_evaluation_source_extraction_concurrency.py`、`test_evaluation_config.py`、`test_evaluation_model_retries.py`、`test_evidence_locations.py` 和 `test_evaluation_parallel.py`。其中证据位置测试通过 13 项检查。并发测试覆盖来源数不足上限、跨 Query 上限为 1 和 2、乱序完成、快照调用上下文及 LangChain 标签/元数据/回调传递、排队任务取消、运行中任务回收、异常后完整名额恢复，以及成功只提交一次。

`test_tavily_searcher_pipeline.py` 和 `test_search_lifecycle.py` 仍分别在上述基线问题处失败。流水线替身已按 URL 绑定结果，输入断言按来源顺序读取，原有业务断言保留。

所有本次修改和新增的 Python 文件通过 Ruff，`git diff --check` 通过。全仓库检查仍报告 216 项既有问题，其中包含命令指定的 `test_wlc.py` 不存在；修改前的流水线测试另有一项导入排序问题，本次随新增导入整理。其余改动文件的基线 Ruff 问题数为零。

所有验证均使用本地替身或离线子进程，没有调用真实模型、Tavily 或 Neo4j。真实 API 下的速度收益尚未测量。本次工作至此完成，不进入其他改造。

## 里程碑二：Query 派发并发的 YAML 配置

用户已另行确认新增可选字段 `agent.search_dispatch_concurrency`，沿用 YAML、根目录 `.env` 中的 `GR_SEARCH_DISPATCH_CONCURRENCY`、默认值 3 的优先级。字段必须为正整数，校验与来源抽取并发一致。省略字段时保留环境配置；配置在启动时传入 Agent 子进程，既有调度器和派发线程池继续读取 `SEARCH_DISPATCH_CONCURRENCY`。

本阶段只修改评测配置校验、子进程环境映射、配置示例与相关离线测试。本地 `evaluate.yaml` 增加 Query 并发值 3，保留用户设置的来源并发值 5。直接运行 `main.py` 的配置入口、调度实现、搜索预算、来源限流和写图逻辑继续沿用现状。

验收要求是两个字段分别通过正整数校验，子进程正确读取默认值、环境回退和 YAML 覆盖值，单独设置其中一个字段不会覆盖另一个字段，输入环境字典不会被修改。验证继续复用配置传递测试，并运行配置、样本并发、模型重试及来源并发的离线回归。

本阶段已完成。配置校验与环境映射复用两个并发字段的既有模式；两个字段均保持可选，不在 YAML 默认值中提前填入覆盖值。已核对本地 `evaluate.yaml` 的 Query 并发为 3、来源并发为 5；示例文件提供相同字段和作用范围说明。

`test_evaluation_source_extraction_concurrency.py`、`test_evaluation_config.py`、`test_evaluation_parallel.py`、`test_evaluation_model_retries.py` 和 `test_source_extraction_concurrency.py` 五个离线回归脚本通过。真实子进程测试验证了缺省配置、环境回退、单字段 YAML 覆盖、双字段覆盖和串行值 1，并确认启动函数没有修改输入环境字典。两个字段的非法 YAML 值和环境值均被拒绝。

本阶段修改的 Python 文件通过 Ruff，`git diff --check` 通过。全仓库 Ruff 仍报告与第一阶段相同的 216 项既有问题。本阶段没有调用真实模型、搜索服务或 Neo4j，调度和写图实现没有变化。工作在本里程碑完成处结束。
