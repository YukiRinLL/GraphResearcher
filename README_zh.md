# GraphResearcher 中文说明

## 问题

`get_next_actions()` 目前返回动作建议，但没有把动作登记为待执行、没有校验下一次工具调用是否消费该动作，也没有对连续相同状态快照做强制熔断。模型可以在 `RESEARCHING` 状态下持续调用读工具，且这些调用不会被“重复失败”保护识别。应把动作消费改为确定性调度，至少增加 graph revision/action signature 的无进展检测。

请通过 test_wlc.py 测试并分析结果，先把 sample-size 设置小一些，因为测试比较费钱
最小运行命令：

```bash
uv run python test_wlc.py \
    --prompt-path /path/to/Wiki_Live_Challenge/data/2025_Mar_Nov/wiki_data//ga_100.json \
    --output-path outputs/wlc_tavily_baseline_6 \
    --sample-size 1 \
    --seed 42 \
    --max-rounds 20 \
    --verbose debug \
    --evaluate \
    --wlc-root /Users/yindq/projects/DeepResearch/Wiki_Live_Challenge \
    --benchmark 2025_Mar_Nov \
```

---

以下 AI 总结

## 整体运行流程

入口在 `main.py`。一次运行大致经过以下阶段：

1. `main.run()` 设置搜索预算和输出目录，把当前输出目录作为 graph context，并清理同一 context 的旧图谱。
2. Orchestrator 调用 `init_research()`。MemoryManager 从当前 run context 中读取原始 User Request，调用模型生成研究目标、Objectives 和初始 Query 树，并把根状态改为 `RESEARCHING`。
3. Orchestrator 反复调用 `get_next_actions()`。状态机可能要求执行 `dispatch_searcher`、`assess_query`、`evaluate_research_portfolio`、`expand_gaps` 或 `assess_convergence`。
4. `dispatch_searcher` 先为 Query 创建 SearchRun，然后调用 Searcher。Searcher 固定执行 Tavily 搜索、筛掉无 URL 或无正文的结果、逐来源抽取证据包，并调用 `submit_search_result()` 入图。
5. `assess_query()` 只评估当前 Query 拥有的证据，检查验收标准，生成 Gap，并推进 Query 状态。`evaluate_research_portfolio()` 再按 Objective 和边际效用选择需要继续处理的 Gap。
6. `expand_gaps()` 将选中的 Gap 转换为新的严格 Query 子树。预算、父子关系和 Query 状态由工具层校验。
7. `assess_convergence()` 判断是否进入 `REPORT_READY`、`LIMITED_REPORT_READY` 或 `BUDGET_EXHAUSTED`。若尚未满足终止条件，继续返回下一动作。
8. 研究状态允许交付后，顶层 `report` 节点启动独立的 Reporter StateGraph。状态图确定性地读取上下文、规划大纲、分批准备证据、生成章节候选、组装草稿，并执行一次审校和最多一次修订；模型只生成受 schema 约束的 JSON，不参与工具调度。
9. `main.py` 从已提交的报告工件中选择最终正文，执行交付校验，写入 `report.md`，并把 Neo4j 图导出为 `research_graph.jsonl`。

核心状态通常沿着下面的路径变化：

```text
INITIALIZING -> RESEARCHING
RESEARCHING -> REPORT_READY | LIMITED_REPORT_READY | BUDGET_EXHAUSTED | FAILED
报告授权状态 -> REPORTING -> COMPLETED
```

Query 自己还有 `pending`、`searching`、`assessing`、`needs_expansion`、`waiting_children`、`sufficient`、`blocked`、`failed` 和 `deferred` 等状态。状态迁移约束位于 `src/tools/graph_tools.py`，不要直接用普通 `upsert_node()` 绕过它。

## 重要目录和文件

| 文件或目录 | 作用 | 使用时注意 |
| --- | --- | --- |
| [`main.py`](main.py) | 单次研究入口、日志 Tee、Orchestrator streaming、报告交付和 JSONL 导出。 | `uv run python main.py "问题"` 会调用真实模型、搜索和 Neo4j。 |
| [`test_wlc.py`](test_wlc.py) | WLC 风格数据的批量运行器，并可调用官方 JSON 生成和评测脚本。 | 默认只抽样 5 条、每条最多 1 个 Searcher 轮次、debug 日志；默认不执行官方评测。 |
| [`src/workflow.py`](src/workflow.py) | 顶层 LangGraph 研究状态图，负责初始化、调度、检索、评估、收敛和 Reporter workflow 接入。 | 研究动作和报告入口都由确定性节点路由。 |
| [`src/agents/orchestrator.py`](src/agents/orchestrator.py) | 为旧版 Deep Agent 入口保留的 Orchestrator 组装代码。 | `main.py` 当前使用 `src/workflow.py`，不经过该入口。 |
| [`src/agents/searcher.py`](src/agents/searcher.py) | LangGraph 固定搜索管线：Tavily、来源筛选、证据抽取、提交。 | Searcher 不负责规划 Query，也不应自行扩展搜索。 |
| [`src/agents/memory_manager.py`](src/agents/memory_manager.py) | 研究初始化、Query 评估、Objective portfolio、Gap 扩展、搜索生命周期和报告上下文。 | 该文件同时包含模型调用和状态副作用，是排查状态问题的首要位置。 |
| [`src/agents/reporter_workflow.py`](src/agents/reporter_workflow.py) | Reporter 的确定性 LangGraph 编排，包括授权、大纲、章节批次、审校、修订和 fail-open 收敛。 | 模型只生成 JSON 候选，所有报告工具调用由状态图执行。 |
| [`src/agents/reporter.py`](src/agents/reporter.py) | 为仓库外部旧调用保留的 Reporter Agent mapping。 | 当前主运行时不再通过该 mapping 生成报告。 |
| [`src/tools/graph_manager_tools.py`](src/tools/graph_manager_tools.py) | 面向 Agent 暴露的 typed tools，包括研究状态工具、Searcher 工具和 Reporter 工具。 | 这是 Agent 的主要能力边界，不要让 Agent 直接调用 Neo4j。 |
| [`src/tools/graph_tools.py`](src/tools/graph_tools.py) | Neo4j async GraphManager 的同步包装、context 隔离、Query 状态和图谱投影。 | `GraphManager` 方法是 async；普通运行路径使用这里的同步包装。 |
| [`src/memory/graph.py`](src/memory/graph.py) | Neo4j 图存储、节点/边 CRUD、SearchRun claim 和 context 清理。 | Neo4j 是事实来源，JSONL 只是导出和 viewer 格式。 |
| [`src/tools/research_state.py`](src/tools/research_state.py) | UserRequest 根状态、状态迁移、预算、报告授权和状态摘要。 | 高风险状态语义集中在这里，修改前应先确认 plan。 |
| [`src/tools/convergence.py`](src/tools/convergence.py) | 无模型的优先级、结构收敛、证据新颖度指标。 | 每个 run 由 `graph_manager_tools.configure()` 清理 novelty 状态。 |
| [`src/tools/report_tools.py`](src/tools/report_tools.py) | 报告大纲、章节 bundle、局部引用、章节校验、审查上下文、草稿和最终 Markdown。 | 章节候选即使校验失败也会保存；只有通过确定性校验的内容才写入报告图谱。 |
| [`src/tools/middleware.py`](src/tools/middleware.py) | 研究状态门禁、空回复/敏感词重试，以及旧 Reporter Agent 的兼容 guard。 | 当前 Reporter 主路径的顺序和重试上限由 `reporter_workflow.py` 控制。 |
| [`src/prompts/`](src/prompts/) | Orchestrator、Searcher、Reporter 大纲与章节、Reviewer 和 MemoryManager 的提示词。 | Reporter prompt 只约束阶段内容和 JSON，不承担工具调度。 |
| [`evaluation_dashboard.html`](evaluation_dashboard.html) | 浏览器端运行产物查看器，展示图谱、搜索轨迹、写作尝试和诊断。 | 默认页面有内置演示数据；加载本地 run 后才显示实际运行。 |
| [`graph_viewer.html`](graph_viewer.html) | 较轻量的 JSONL 图谱查看器。 | 只适合看导出的节点和边，不包含 dashboard 的报告诊断。 |
| [`tests/`](tests/) | 独立回归脚本和可被 pytest 收集的测试。 | 很多文件会 monkeypatch `graph_tools`；`test_graph_tools.py` 需要真实 Neo4j。 |

## `test_wlc.py`：批量运行和官方评测

输入文件必须是 JSON 数组，每个元素至少包含：

```json
{
  "id": 82,
  "title": "Ring of Nestor",
  "question": "Write a Wikipedia article ..."
}
```

最小运行命令：

```bash
uv sync
uv run python test_wlc.py \
  --prompt-path /path/to/wiki_data.json \
  --output-path outputs/wlc_local \
  --sample-size 1 \
  --seed 42 \
  --max-rounds 1 \
  --verbose debug
```

主要参数：

- `--prompt-path`：输入 JSON；默认是项目外部的 WLC 数据集绝对路径。
- `--output-path`：顶层 Markdown 输出目录，默认 `outputs/wlc_reports`。
- `--sample-size`：随机抽样数量；小于等于 0 表示全部数据。
- `--seed`：抽样随机种子。不设置时每次抽样可能不同。
- `--max-rounds` 或 `-r`：每条任务允许的 Searcher dispatch 次数；`0` 表示不限制。
- `--verbose` 或 `-v`：复用 `main.py` 的 `quiet`、`normal`、`debug` 预设。

每条任务的目录是 `OUTPUT_PATH/_runs/{id}-{safe_title}/`，包含：

```text
input.json                 原始输入快照
run.log                    完整 console、tool call、warning 和 traceback
report.md                  对外报告
research_graph.jsonl       当前 run 的 Neo4j 图导出
.report_outline.json       Reporter 大纲
.report_chapters/          章节正文和章节 meta
.report_attempt.json       最近一次报告提交结果
.compiled_report.md        通过校验的报告正文（若存在）
.best_report.md            当前可交付的最佳报告工件
```

如果顶层同名 `{title}.md` 已经存在，`run_one()` 会直接跳过该任务；这对断点续跑有用，但也可能让旧报告掩盖新代码结果。开始新一轮评测前应使用新的输出目录，或确认已有文件确实来自当前配置。

加上 `--evaluate` 后，脚本会：

1. 把生成的 Markdown 复制到 `eval-work-dir/md_data`。
2. 调用 WLC 项目的 `scripts/generate_json.py`，默认步骤为 `extract,fetch`。
3. 调用 `scripts/run_evaluation.py all`，生成 citation、verifiability 和 writing 结果。

示例：

```bash
uv run python test_wlc.py \
  --prompt-path /path/to/wiki_data.json \
  --output-path outputs/wlc_eval \
  --sample-size 5 \
  --seed 42 \
  --max-rounds 6 \
  --evaluate \
  --wlc-root /path/to/Wiki_Live_Challenge \
  --benchmark 2025_Mar_Nov \
  --eval-work-dir outputs/wlc_eval/_wlc_eval
```

`test_wlc.py` 会捕获单条任务的异常并继续处理下一条，因此批量命令返回成功并不等于每条任务都有报告。应检查终端输出、各 run 的 `run.log` 和最终报告数量。

## `evaluation_dashboard.html`：查看运行产物

这是一个纯前端 HTML 页面，使用 CDN 提供的 `vis-network` 绘制图谱。可以直接在浏览器打开：

```bash
open evaluation_dashboard.html       # macOS
# 或在浏览器中打开项目根目录下的 evaluation_dashboard.html
```

页面初始显示的是内置的 `RUN4_DEMO` 示例，不代表当前 Neo4j 或某个真实 run 的结果。要查看真实运行：

1. 点击“选择运行目录”。
2. 选择包含 `research_graph.jsonl` 的单个 run 目录，或选择包含多个 `_runs` 子目录的上层目录。
3. 如果识别出多个 run，在下拉框中选择目标目录，再点击“加载选中的本地目录”。
4. 页面会读取 `research_graph.jsonl`，并尽量读取同目录下的 `run.log`、`.report_attempt.json`、`.compiled_report.md`、`.best_report.md` 和 `report.md`。

四个主要页签的内容：

- “记忆图结构”：vis-network 图、节点详情、类型筛选、图谱预设、密度/树形布局和当前视图数据表。
- “规划与搜索轨迹”：Objectives、Query、Gap、冲突以及从 `run.log` 提取的初始化和搜索时间线。
- “写作轨迹”：Reporter 的提交尝试、校验问题、保留章节数、引用/来源统计和报告工件预览。
- “问题与缺陷”：根据图节点、状态、冲突、报告尝试和日志 warning 生成的诊断提示。

导入逻辑有几个边界：

- 必须有可解析的 `research_graph.jsonl`，否则该目录不会被识别为 run。
- 图谱 JSONL 逐行解析，非法行会被跳过并写入浏览器 console warning。
- `run.log` 只识别特定文本标记，例如 `[AIMessage → tool]`、`[get_next_actions result]`、`[submit_final_report result]` 和 `State summary:`；未采用这些标记的日志不会进入时间线。
- 部分诊断是基于节点状态和日志的启发式推导，并不是对完整 Agent 事件流的逐事件回放。
- 图谱节点过多时，页面默认按预设和节点上限截取可视子图；切换“展开”或调高节点上限后再判断结构。
- 图谱颜色配置写入浏览器 `localStorage`，不是运行产物的一部分。

对于持续循环等问题，优先同时打开“规划与搜索轨迹”和 `run.log`：dashboard 能显示已解析的工具调用，但原始日志仍是判断调用顺序、参数和异常的事实依据。
