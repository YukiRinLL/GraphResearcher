# Reporter 并行章节写作与全文润色

## 目标

Reporter 在生成大纲后并行撰写相互独立的章节。每章正文和证据元数据分别持久化，执行状态只保存在 LangGraph state 中。所有章节分支结束后，缺失章节使用现有确定性正文补齐，完整草稿再经过一次模型调用统一行文并交付。全文润色使用独立的 600 秒请求超时；润色失败时直接交付按大纲组装完成的章节草稿。

## 已确认决策

- 章节模型调用并行执行，默认并发数为 3，并通过 `GR_REPORTER_CHAPTER_CONCURRENCY` 允许用户调整。
- 报告大纲只保存标题、章节顺序、章节目标、Query 绑定和章节规划，不持久化章节执行状态。
- 每章继续保存独立 Markdown 正文和证据 meta。证据 meta 不参与写作 prompt，只保留局部引用映射、校验结果和后续证据追踪能力。
- 某章重试耗尽不会取消其他章节。所有分支结束后，失败章节使用 `_fallback_chapter_content()` 生成基础正文。
- 即使存在确定性补齐章节，完整草稿仍进入一次最终润色调用。
- 最终润色只改善表达、术语一致性和章节衔接，不改变章节顺序、事实、数值、限定条件或数字引用。
- 全文润色通过 `GR_REPORTER_POLISH_TIMEOUT` 配置单次请求超时，默认值为 600 秒。
- 润色失败不改变章节草稿；工作流通过现有直接交付路径返回组装结果，并在 `fallback_reason` 中保留失败原因。
- 当前里程碑不增加润色结果校验或信息保留率检查。

## Proposed shape

状态图目标拓扑：

```text
authorize -> export_context -> plan_outline -> prepare_all_chapters
    -> Send(draft_chapter, chapter 1)
    -> Send(draft_chapter, chapter 2)
    -> Send(draft_chapter, chapter N)
    -> assemble_draft -> polish_report -> submit -> END
                                      \-> finalize_best_effort -> END
```

章节分支只向带 reducer 的 `chapter_results` 写入一个终态结果。主图在 fan-in 后按 `chapter_id` 排序，不依赖并发完成顺序。

持久化职责：

```text
.report_outline.json                 静态报告计划
.report_outline.md                   静态报告计划的 Markdown 视图
.report_chapters/chapter_XX.md       章节正文
.report_chapters/chapter_XX.meta.json 证据映射和校验元数据
.compiled_report.md                  润色后的最终报告
```

## 行为不变量

- `OutlineCandidate`、`ChapterDraftCandidate`、章节 bundle 和章节提交 payload 的 shape 保持不变。
- Evidence、Claim 和 Conflict 继续使用章节局部 `e*`、`c*`、`x*` 引用，并由 `bundle_token` 约束加载版本。
- 章节 prompt 每次只包含当前章节的证据包，同时保留完整报告大纲作为结构上下文。
- 章节正文在校验结果为 false 时仍然保存，维持现有 fail-open 章节提交语义。
- 最终章节顺序只由大纲中的 `chapter_id` 决定。
- 润色异常只影响行文增强；已持久化章节仍按大纲顺序组装，并成为本次运行的最终交付物。
- `get_compiled_report()` 和 `main.py` 的最终交付读取接口保持不变。
- 旧运行产物如果仍把动态章节字段保存在 outline 中，读取时继续兼容。

## 非目标

- 不修改 `NodeType`、`EdgeType`、Query 状态机或 `research_state` 值域。
- 不修改 Evidence、Claim、Conflict 或 Reporter 候选 JSON schema。
- 不新增 checkpoint、进程重启恢复或跨运行续写。
- 不实现章节依赖分析或按依赖分层调度。
- 不新增独立的润色模型名称或模型选择规则。
- 不在本轮实现润色输出校验或压缩率检查。

## 里程碑

### 里程碑 1：分离静态大纲与章节动态元数据

- `commit_report_outline()` 不再写入章节执行状态。
- `commit_report_chapter_batch()` 只写当前章节正文和 meta，不再改写 outline。
- `_load_committed_report()` 和严格交付从 chapter meta 读取动态字段，并兼容旧 outline。
- 确定性缺章补齐只更新对应章节文件和 meta。

验收：提交任意章节前后，outline 内容保持不变；现有严格交付、Review context 和图谱绑定测试继续通过。

### 里程碑 2：并行章节分支

- 使用 `Send` 为每章创建独立写作任务。
- 章节重试预算进入分支局部逻辑，分支只聚合 `chapter_results`。
- 并发数由 `GR_REPORTER_CHAPTER_CONCURRENCY` 控制，默认值为 3。
- 所有分支结束后再执行确定性缺章补齐和草稿汇总。

验收：章节模型调用存在真实重叠，并发峰值不超过配置值；完成顺序不影响最终报告顺序；单章失败不阻断其他章节。

### 里程碑 3：单次全文润色与交付

- 新增只处理完整草稿的 `reporter_polish` prompt。
- 草稿汇总后恰好调用一次 Reporter 模型。
- 润色结果通过现有最终报告缓存与文件路径交付。

验收：包含确定性补齐章节的草稿也会进入润色；最终读取接口返回润色后的 Markdown；章节 prompt 和润色 prompt 的职责保持隔离。

### 里程碑 4：长文本润色超时与直接交付

- 全文润色使用独立模型句柄，单次请求超时由 `GR_REPORTER_POLISH_TIMEOUT` 配置，默认值为 600 秒。
- 润色超时、连接失败、响应格式错误或其他异常时，工作流进入 `finalize_best_effort`。
- `finalize_best_effort` 使用现有确定性组装结果交付完整报告，不退回按 Query 罗列的 Evidence 报告。

验收：正常润色仍提交模型返回的完整 Markdown；模拟请求超时时返回 `success=true` 和 `delivered=true`，最终调用顺序为 `assemble`、`deliver`，且 `fallback_reason` 保留润色失败原因。

## 兼容策略

- 新写 outline 不包含 `status`、`validated`、`source_ids`、`evidence_ids`、`disclosed_conflict_ids` 或 `validation_issues`。
- 新写 chapter meta 继续包含当前证据映射和动态校验字段。
- 加载旧产物时，如果 chapter meta 缺少某个动态字段，则读取旧 outline 中的同名字段。
- 对外的 `graph_manager_tools` 章节准备和提交函数签名不变。

## 验收命令

```bash
uv run python tests/test_contract_v4.py
uv run python tests/test_report_delivery.py
uv run python tests/test_reporter_workflow.py
uv run python tests/test_state_contract_v2.py
uv run ruff check src tests main.py test_wlc.py
uv run python -m py_compile src/agents/reporter_workflow.py src/tools/graph_manager_tools.py src/tools/report_tools.py src/config.py
git diff --check
```

不运行真实 Neo4j CRUD 或模型端到端任务，避免污染已有 context 和消耗 API 配额。

## 当前进度

- 里程碑 1：已完成。
- 里程碑 2：已完成。
- 里程碑 3：已完成。
- 里程碑 4：已完成。

## 里程碑 1 实施结果

报告大纲现在只保存静态写作计划。正常章节提交和确定性缺章补齐都只更新对应章节的 Markdown 与 meta，不再改写 outline JSON 或 Markdown。报告加载与严格提交优先从 chapter meta 读取动态校验和证据绑定字段；没有相应 meta 字段的旧产物继续从 outline 读取。

新增 `tests/test_reporter_artifact_persistence.py`，覆盖静态 outline、chapter meta 加载、严格提交状态恢复、确定性缺章补齐和旧产物兼容。以下检查通过：

```bash
uv run python tests/test_reporter_artifact_persistence.py
uv run python tests/test_reporter_replay.py
uv run ruff check src/tools/report_tools.py tests/test_reporter_artifact_persistence.py --ignore UP031
uv run python -m py_compile src/tools/report_tools.py tests/test_reporter_artifact_persistence.py
git diff --check
```

`tests/test_contract_v4.py` 和 `tests/test_report_delivery.py` 仍在本次修改之前的 Source–Statement fixture 处失败，未执行到章节持久化断言。既有 Reporter ExecPlan 已记录相同基线问题，本里程碑没有通过放宽来源登记或引用校验来改变它。

## 里程碑 2 实施结果

Reporter 在大纲提交后先按工具的三章批量上限准备全部证据包，再通过 LangGraph `Send` 为每章创建隔离写作分支。每个分支拥有自己的三次重试预算，只向带 reducer 的 `chapter_results` 返回终态；章节正文和证据 meta 仍按章节独立保存。所有分支完成后才调用现有交付路径，因此失败分支不会取消其他章节，缺失正文会先由确定性逻辑补齐。

运行时通过 `GR_REPORTER_CHAPTER_CONCURRENCY` 控制分支并发，默认值为 3，非正整数配置会在启动时被拒绝。测试覆盖了真实重叠调用、配置上限、单章失败继续交付、反序提交后按大纲排序，以及原有章节重试语义。以下检查通过：

```bash
uv run python tests/test_reporter_artifact_persistence.py
uv run python tests/test_reporter_replay.py
uv run ruff check src/agents/reporter_workflow.py src/config.py src/tools/report_tools.py tests/test_reporter_workflow.py tests/test_reporter_artifact_persistence.py --ignore UP031
uv run python -m py_compile src/agents/reporter_workflow.py src/tools/report_tools.py src/config.py tests/test_reporter_workflow.py tests/test_reporter_artifact_persistence.py
git diff --check
```

`tests/test_reporter_workflow.py` 中除既有的 prompt 文案精确匹配检查外，其余 18 个回归函数均通过。完整脚本仍因 `reporter_outline.md` 缺少既有断言要求的“材料不会沿父子或兄弟关系自动合并”而提前失败；这与并行编排无关，本里程碑没有修改 prompt 合同。`tests/test_state_contract_v2.py` 仍在既有的预算耗尽状态优先级断言处失败，本次改动尚未进入 Reporter 相关断言。

## 里程碑 3 实施结果

章节 fan-in 后新增 `assemble_draft` 和 `polish_report` 两个节点。草稿组装会先调用现有确定性缺章补齐，再按大纲顺序生成包含参考文献的完整 Markdown；润色节点只调用一次 Reporter 模型，并要求返回完整报告。润色后的正文不会覆盖章节文件或证据 meta，而是通过现有 `.compiled_report.md` 路径登记为最终交付物。

新增 `reporter_polish.md`，将可编辑范围限制为句式、术语一致性和章节衔接，并要求保留标题层级与顺序、事实、数值、限定条件、引用编号和参考文献。按照已确认范围，本里程碑只检查润色响应的 JSON shape 和非空正文，不实现内容保留校验、重试或失败回退。

测试覆盖了完整草稿注入、恰好一次润色、章节重试耗尽后仍然润色、无效润色响应不交付草稿，以及润色结果写入现有最终缓存。以下检查通过：

```bash
uv run python tests/test_reporter_artifact_persistence.py
uv run python tests/test_reporter_replay.py
uv run ruff check src/agents/reporter_workflow.py src/config.py src/tools/report_tools.py tests/test_reporter_workflow.py tests/test_reporter_artifact_persistence.py --ignore UP031
uv run ruff check src/tools/graph_manager_tools.py --ignore UP031,D301
uv run python -m py_compile src/agents/reporter_workflow.py src/tools/graph_manager_tools.py src/tools/report_tools.py src/config.py tests/test_reporter_workflow.py tests/test_reporter_artifact_persistence.py
git diff --check
```

除未修改的既有大纲 prompt 精确文案检查外，`tests/test_reporter_workflow.py` 的其余 21 个回归函数均通过。

## 里程碑 4 实施结果

全文润色现在使用独立的惰性模型句柄，默认单次请求超时为 600 秒，不改变大纲、章节写作和审查模型的超时。润色节点发生异常时进入现有 `finalize_best_effort` 节点，由该节点重新读取已提交章节并按大纲顺序组装，随后登记为最终报告。正常润色提交路径和最终报告 payload 保持不变。

回归测试覆盖独立超时配置、正常润色使用专用 phase，以及模拟 `Request timed out.` 后交付章节组装稿。以下检查通过：

```bash
uv run python tests/test_reporter_artifact_persistence.py
uv run python tests/test_reporter_replay.py
uv run ruff check src/agents/reporter_workflow.py src/config.py tests/test_reporter_workflow.py
uv run python -m py_compile src/agents/reporter_workflow.py src/config.py tests/test_reporter_workflow.py
git diff --check
```

本里程碑新增的三个定向回归函数均通过；排除既有的大纲 prompt 精确文案检查后，
`tests/test_reporter_workflow.py` 的其余 22 个回归函数也全部通过。完整脚本仍因
`reporter_outline.md` 缺少既有断言要求的“材料不会沿父子或兄弟关系自动合并”而失败，
该失败与润色超时和直接交付逻辑无关。
