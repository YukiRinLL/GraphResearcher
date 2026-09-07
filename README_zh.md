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
| [`src/tools/graph_manager_tools.py`](src/tools/graph_manager_tools.py) | 研究状态和 Searcher 的 typed tools，以及 Reporter workflow 使用的运行级服务。 | Reporter 服务负责当前 run 的缓存目录、审校状态和最终产物记录。 |
| [`src/tools/graph_tools.py`](src/tools/graph_tools.py) | Neo4j async GraphManager 的同步包装、context 隔离、Query 状态和图谱投影。 | `GraphManager` 方法是 async；普通运行路径使用这里的同步包装。 |
| [`src/memory/graph.py`](src/memory/graph.py) | Neo4j 图存储、节点/边 CRUD、SearchRun claim 和 context 清理。 | Neo4j 是事实来源，JSONL 只是导出和 viewer 格式。 |
| [`src/tools/research_state.py`](src/tools/research_state.py) | UserRequest 根状态、状态迁移、预算、报告授权和状态摘要。 | 高风险状态语义集中在这里，修改前应先确认 plan。 |
| [`src/tools/convergence.py`](src/tools/convergence.py) | 无模型的优先级、结构收敛、证据新颖度指标。 | 每个 run 由 `graph_manager_tools.configure()` 清理 novelty 状态。 |
| [`src/tools/report_tools.py`](src/tools/report_tools.py) | 报告大纲、章节 bundle、局部引用、章节校验、审查上下文和最终 Markdown。 | 章节候选即使校验失败也会保存；只有通过确定性校验的内容才写入报告图谱。 |
| [`src/tools/middleware.py`](src/tools/middleware.py) | 通用模型空回复和敏感词重试。 | Reporter 的顺序、重试和质量反馈由确定性 workflow 与报告模块负责。 |
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

## DeepResearch Bench I 与 II：批量运行和官方评测

两个入口都复用 `main.run()`。生成阶段读取 GraphResearcher 的配置，每题保存输入快照、`run.log`、`report.md` 和 `research_graph.jsonl`。默认抽样 5 题；`--sample-size 0` 表示全部任务，`--seed` 控制可重复抽样。两个脚本都跳过已有报告，并可在生成后加 `--evaluate` 运行官方评测，或使用 `--evaluate-only` 只评测已有报告。

以下命令应在 GraphResearcher 根目录执行。生成会消耗模型与搜索配额并访问 Neo4j；官方评分会额外消耗评测模型配额，Bench I 的 FACT 还会使用 Jina Reader。`--max-rounds 1` 适合确认流程，正式质量评测应设置足够的搜索预算。

### Bench I

[`test_deepresearch_bench.py`](test_deepresearch_bench.py) 默认读取相邻 `deep_research_bench` 仓库的 `data/prompt_data/query.jsonl`。输入保留官方整数 `id`、`prompt` 和 `language`，生成过程只把原始 `prompt` 传给 agent。

```bash
# 生成一题并运行 RACE 和 FACT。
uv run python test_deepresearch_bench.py \
  --sample-size 1 --seed 42 --max-rounds 1 \
  --output-path outputs/drb_smoke --evaluate

# 只对已有报告运行 RACE；FACT 使用 --eval-mode fact。
uv run python test_deepresearch_bench.py \
  --output-path outputs/drb_smoke --evaluate-only --eval-mode race
```

Bench I 的 `--eval-mode` 可选 `all`、`race`、`fact`，默认 `all`。`--eval-max-workers` 控制官方并发数，默认 5。`--bench-root` 可切换官方仓库位置，未指定 `--prompt-path` 时输入路径随仓库位置变化。

输出结构如下，`--model-name` 默认是 `GraphResearcher`：

```text
outputs/drb_smoke/
  report/GraphResearcher/id-<id>.md
  _runs/GraphResearcher/id-<id>/
  raw_data/GraphResearcher.jsonl
  cleaned_data/GraphResearcher.jsonl
  _evaluation/GraphResearcher/query.jsonl
  _evaluation/GraphResearcher/official_output.log
  results/race/GraphResearcher/race_result.txt
  results/fact/GraphResearcher/fact_result.txt
```

`raw_data/GraphResearcher.jsonl` 每行只有 `{id, prompt, article}`，可直接用于官方提交。每次导出会收集当前输入清单中已有的全部非空报告，因此续跑抽样不会丢掉之前的成果。评测任务清单与这份导出逐题对齐，原始提示词和带引用的正文保持不变。没有生成正文的任务不会进入评测，零份有效报告会使脚本报错。RACE 另用 `race_query.jsonl` 排除已成功评分的任务，避免续跑重复追加结果。RACE 的清洗、FACT 的引用提取和验证均由官方代码执行，结果与中间文件保存在上述输出目录。

### Bench II

[`test_deepresearch_bench_ii.py`](test_deepresearch_bench_ii.py) 默认读取相邻 `DeepResearch-Bench-II` 仓库的 `tasks_and_rubrics.jsonl`。生成阶段使用顶层 `prompt`，其中的来源限制会原样保留；`content` 中的评分 rubric 仅供官方评测器读取。

```bash
uv run python test_deepresearch_bench_ii.py \
  --sample-size 1 --seed 42 --max-rounds 1 \
  --output-path outputs/drb_ii_smoke --evaluate

uv run python test_deepresearch_bench_ii.py \
  --output-path outputs/drb_ii_smoke --evaluate-only
```

报告位于 `report/GraphResearcher/idx-<n>.md`，每题产物位于 `_runs/idx-<n>-<id>/`。官方逐题结果保存在输出根目录的 `result.jsonl`，汇总为 `agg_scores_*.csv`，评测日志在 `_evaluation/run_evaluation.log`。评测会扫描所选模型目录内累计的报告，只提交尚无成功评分的任务，再汇总累计结果。`--evaluate-only` 不进行生成或随机抽样。设置 `--prompt-path` 时，生成和评分使用同一任务文件。

### 评测配置

两个入口在启动官方子进程前，读取各自 `--bench-root` 下的 `.env`；文件中的配置覆盖父进程同名变量，agent 进程保持原配置。切换评测服务时修改对应 benchmark 的 `.env`。真实 key 不应写入示例文件或版本控制。

| 仓库 | 配置项 | URL 格式 |
| --- | --- | --- |
| `deep_research_bench` | `LLM_BACKEND=openai`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`RACE_MODEL`、`FACT_MODEL`、`JINA_API_KEY` | `OPENAI_BASE_URL` 使用 API 根路径，例如 `https://api.openai.com/v1`。 |
| `DeepResearch-Bench-II` | `OPENAI_API_KEY`、`OPENAI_API_URL`、`OPENAI_MODEL`、`OPENAI_REASONING_EFFORT` | `OPENAI_API_URL` 使用完整端点，例如 `https://api.openai.com/v1/chat/completions`。 |

Bench I 的无凭据模板在其仓库 `.env.example`，Bench II 模板为 `.env_example`。Bench I 的 OpenAI 后端默认 RACE 模型是 `gpt-5.5`，FACT 模型是 `gpt-5.4-mini`。评测模型由 benchmark 配置决定，与生成模型 `GR_MODEL` 分开；使用不同评测模型得到的分数应注明配置。FACT 需要 Jina key，只运行 RACE 则无需该项。

两个脚本均可通过 `--bench-python /absolute/path/to/python` 指定已经准备好的评测解释器。Bench I 默认使用启动当前脚本的 Python；Bench II 保留原有 `uv run --project <bench-root> --isolated python` 命令。脚本不负责安装或修改 Python 依赖环境。

续跑会复用已有报告和官方评测缓存。更换生成模型、评测模型、任务文本或搜索预算进行新实验时，应使用新的输出目录，避免混合不同配置的产物。

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
