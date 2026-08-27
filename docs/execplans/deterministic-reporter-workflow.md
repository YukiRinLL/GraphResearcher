# Reporter 确定性 LangGraph 编排

## 目标

Reporter 由独立的 LangGraph 状态图依次完成授权、上下文导出、大纲规划、章节取证、章节写作、一次审校和最多一次修订。模型只生成受 schema 约束的 JSON 候选内容，不参与调度。

## 已确认决策

- 参考提交 `86541de205cd5c3908c19683a3dc78f982fbaf33` 的 Reporter 状态图设计，但按当前顶层 LangGraph 调整集成方式，不直接移植旧版 Orchestrator 改动。
- 顶层 `workflow.py` 的 `report` 节点直接调用嵌套 Reporter workflow，不把 Reporter workflow 暴露成由 Orchestrator 模型调用的工具。
- 保留 state contract v4 的 fail-open 交付策略。第二次最终提交或有界重试耗尽后仍交付最佳完整产物，并通过 `validated`、`issues` 和 `graph_persisted` 表达质量状态。
- 大纲和章节模型调用均使用低温 `config.reporter_model`。
- 大纲和每个章节批次最多尝试三次；每批最多处理三章。
- 首次最终提交继续执行一次独立 Review。只有 `revision_requested=true` 时才进行一轮章节修订，第二次提交不再 Review。
- Query tree 校验失败继续记录 warning，不改变当前 Reporter 放行语义。
- Reporter workflow 直接调用普通 Python 服务函数，不提供旧 Reporter Agent mapping 或 Reporter tool 集合。
- 章节提交成功时同步推进章节游标；最终提交直接消费已保存的章节候选，不生成中间草稿文件。

## Proposed shape

外部接口为无参数的 `run_report_workflow()`，返回精简结果：

```python
{
    "success": bool,
    "delivered": bool,
    "validated": bool,
    "review_status": str | None,
    "fallback_reason": str | None,
    "error": str | None,
}
```

内部状态只存在于 Reporter StateGraph，包含原始请求、报告上下文、大纲、章节游标、当前证据包、重试次数、修订反馈和最终结果。它不写入 Neo4j。

状态图拓扑：

```text
authorize -> export_context -> plan_outline
    -> prepare_chapter_batch -> draft_chapter_batch
    -> ...下一批...
    -> submit
                    | revision_requested
                    v
              prepare_chapter_batch -> ... -> submit
                    |
                    v
                   END
```

## 行为不变量

- 原始 User Request 仍逐字保存，并且是 Reporter 最高优先级的写作要求。
- Reporter 只能使用 `export_report_context` 和章节 bundle 暴露的材料，不拥有搜索工具。
- Query 只通过可读 handle 进入 Reporter-facing context。
- Evidence、Claim 和 Conflict 继续使用章节局部 `e*`、`c*`、`x*` 引用，并由 `bundle_token` 约束加载版本。
- `commit_report_outline`、`prepare_report_chapter_batch`、`commit_report_chapter_batch` 和 `submit_final_report` 的参数与返回 shape 保持稳定。
- 正文候选仍先保存再校验；校验失败不能丢弃 Reporter 已写正文。
- 最终 Markdown 仍由现有确定性编译器生成唯一参考文献区。
- 只有严格验证通过的报告才把 `ReportSection` 及证据、来源绑定写入 Neo4j。
- `main.py` 继续按 compiled、salvaged、evidence fallback 的顺序选择交付产物。

## 非目标

- 不修改 `NodeType`、`EdgeType`、Query 状态机或 `research_state` 值域。
- 不修改报告章节 schema、引用绑定规则或图谱迁移策略。
- 不改变 Review 模型、Review 输出 JSON 或 `submit_final_report` 的一次审校/一次修订契约。
- 不把参考提交中的 strict/fail-closed `main.py` 交付逻辑带入当前主线。
- 不优化 Reporter 的图谱读取次数，不引入 run-scoped 图谱快照。
- 不精简 `ReporterWorkflowState` 字段。

## 里程碑

### 里程碑 1：Reporter workflow 与阶段化 prompt

- 新增独立 Reporter StateGraph。
- 新增只负责大纲 JSON 的 prompt。
- 将 Reporter 正文 prompt 收窄为只负责一个已准备章节批次的 JSON 输出，同时保留语言、主体、证据、引用、冲突、Wikipedia 和文体约束。
- 使用 Pydantic 校验模型候选，并将错误反馈限制在当前阶段的有界重试中。

验收：模型不持有工具；大纲、章节和修订的调用顺序只能由图推进。

### 里程碑 2：顶层工作流集成

- 用 `run_report_workflow()` 替换 `workflow.py` 中的通用 Reporter Agent。
- 把授权、Query tree warning 和 `REPORTING` 状态迁移集中到 Reporter workflow。
- 顶层 `report` 节点只追加可观察摘要，不读取模型终止文本作为报告。

验收：研究图进入允许报告状态后，只经过确定性 Reporter StateGraph 到达顶层 END。

### 里程碑 3：回归验证

- 新增隔离 Reporter workflow 回归脚本。
- 验证大纲和章节有界重试、分批顺序、一次修订、fail-open 收敛以及未授权失败。
- 运行 Reporter、v4 契约、报告交付和相关 Ruff 检查。

### 里程碑 4：运行时收敛

- 删除仅传递状态的 `advance_chapter_batch`、`assemble` 和 `success` 节点。
- Reporter workflow 直接调用 `graph_manager_tools` 中的普通函数。
- 删除旧 Reporter Agent mapping、Reporter tools、Agent middleware 和 `.report_draft.md` 中间产物。
- 将仍有效的 Reporter prose 检查迁移到报告模块。

验收：Reporter StateGraph 只保留运行时需要的八个节点，生产路径中没有 Reporter `StructuredTool.invoke()` 调用。

## 运行时接口

- `.report_outline.*`、`.report_chapters/`、compiled/salvaged/best/attempt 文件保持不变。
- `graph_manager_tools` 继续持有 run-scoped 缓存目录、Review 状态和报告结果缓存。
- 模型或 provider 重复失败时，工作流调用最终提交服务生成最佳可交付产物；只有最终提交本身无法产生任何报告时才把运行标记为 `FAILED`。

## 验收命令

```bash
uv run python tests/test_reporter_workflow.py
uv run python tests/test_reporter_replay.py
uv run ruff check src/agents/reporter_workflow.py src/tools/graph_manager_tools.py src/tools/report_tools.py src/tools/middleware.py tests/test_reporter_workflow.py
uv run python -m py_compile src/agents/reporter_workflow.py src/tools/graph_manager_tools.py src/tools/report_tools.py src/tools/middleware.py
git diff --check
```

不运行真实 Neo4j CRUD 或模型端到端任务，避免污染现有 context 和消耗 API 配额。

## 实施结果

四个里程碑均已完成。当前主路径由 `src/workflow.py` 直接调用
`run_report_workflow()`。大纲与章节写作拆成两个独立 prompt，章节按最多三章一批推进，
审校后最多重写全部章节一次。Reporter 的报告服务是普通 Python 函数，旧 Agent mapping、
Reporter tool 集合和专用 middleware 已删除。

回归脚本覆盖正常顺序、精简后的节点集合、阶段 prompt、当前批次重试、三章分批、一次修订、
重试耗尽后的 fail-open 交付、未授权失败、质量检查迁移和顶层 workflow 接入。以下检查通过：

```bash
uv run python tests/test_reporter_workflow.py
uv run python tests/test_reporter_replay.py
uv run ruff format --check src/agents/reporter_workflow.py src/tools/graph_manager_tools.py src/tools/report_tools.py src/tools/middleware.py tests/test_reporter_workflow.py
uv run python -m py_compile src/agents/reporter_workflow.py src/tools/graph_manager_tools.py src/tools/report_tools.py src/tools/middleware.py
git diff --check
```

计划中列出的 `test_contract_v4.py`、`test_report_delivery.py` 和
`test_contract_v3.py` 仍会触发现有断言：前两项的 fixture 没有建立当前来源登记所要求的
Statement 到 URL Source 传递引用，后一项仍假定任意 reviewer soft issue 都会要求修订，
而当前 v4 契约只对 hard 或 critical issue 启动唯一修订轮。完整执行
`test_state_contract_v2.py` 也会在本次修改覆盖范围之前的预算优先级断言处停止：旧断言期望
`REPORT_READY`，当前实现返回 `BUDGET_EXHAUSTED`。这些失败与本次 Reporter 调度切换无关，
本次没有放宽生产校验或改写旧断言来掩盖它们；其中与新 prompt 相关的契约检查已单独通过。
