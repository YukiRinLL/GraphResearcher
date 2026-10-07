# 统一 Benchmark 评估

`evaluate.py` 用同一个入口运行 GraphResearcher，并调用 `Benchmark/` 中的
DeepResearch Bench、Wiki Live Challenge 和 DeepResearch Bench II。

## 准备配置

先将示例文件复制为本地配置：

```bash
cp evaluate.yaml.example evaluate.yaml
cp .env.example .env
```

`evaluate.yaml` 保存 Agent 的模型、超时、重试、并发、报告预算，以及抽样和
Benchmark 参数。根目录 `.env` 保存密钥、API 地址、Neo4j 连接和 Langfuse
认证信息。统一入口会忽略 Benchmark 子目录中的 `.env`。

运行参数按显式命令行选项、显式 YAML、兼容环境变量、代码默认值的顺序解析。
没有填写的 YAML 字段会逐项回退，补齐的默认值不会提前覆盖旧环境配置。
日常调整统一在 YAML 中进行；旧环境变量仍可用于兼容历史配置。

直接运行 Agent 和评测入口共用同一套 Agent 配置解析：

```bash
uv run python main.py "研究问题" --config evaluate.yaml
uv run python evaluate.py --config evaluate.yaml
```

`main.py` 只读取 `agent` 区块，不要求启用任何 Benchmark。未传 `--config` 时，
它读取仓库根目录的 `evaluate.yaml`（若存在）；无配置文件时使用环境配置。
显式 `--max-rounds` 和 `--verbose` 覆盖 YAML 的对应字段。
`agent.max_workers` 和 `agent.timeout_seconds` 由评测器管理子进程时使用。

`agent.timeout_seconds` 控制每条样本从启动 Agent 到生成报告的总耗时上限，
默认是 7200 秒。正数表示限时秒数；设为 `-1` 时，统一入口会等待 Agent
子进程运行结束。`0` 和其他负数是无效配置。该设置不包含后续 Benchmark 评分，
单次模型请求超时、搜索超时、重试次数和 `agent.max_rounds` 仍各自生效。

`agent.max_retries` 设置 Agent 每次模型调用的 HTTP 自动重试次数，默认是 `3`。
该值必须是非负整数；`0` 表示仅发送首次请求，`1` 表示首次请求失败后最多
再尝试一次。它适用于证据抽取、证据评估和报告生成等使用模型工厂的调用。
统一入口将最终值通过 `GR_MODEL_MAX_RETRIES` 传给 Agent 子进程。YAML 显式
填写时覆盖旧环境值；省略时读取环境值，最后回退到 3。Query 搜索与 Reporter 工作流的外层尝试次数、后续
Benchmark 评分的重试配置仍各自生效。

```yaml
agent:
  model: deepseek-v4-pro
  model_timeout_seconds: 180
  search_timeout_seconds: 30
  timeout_seconds: -1
  max_retries: 1
  search_dispatch_concurrency: 3
  source_extraction_concurrency: 5
  assess_query_concurrency: 3
  reporter:
    model: ""
    model_timeout_seconds: 600
    packet_tokens: 48000
    output_tokens: 40000
```

`search_dispatch_concurrency` 控制同时派发的 Query 数量，
`source_extraction_concurrency` 是这些 Query 共用的来源 analyzer 调用上限，
`assess_query_concurrency` 控制证据评估并发。`reporter.model` 留空时继承
`agent.model`，Reporter 请求超时和 token 预算分别由其子字段控制。

每套评测器通过自己的 `runtime` 区块配置模型和请求参数：

```yaml
benchmarks:
  deep_research_bench:
    enabled: true
    runtime:
      backend: openai
      race_model: gpt-5.5
      fact_model: gpt-5.4-mini
      model_timeout_seconds: 600
      max_output_tokens: 64000
```

Wiki Live Challenge 的 `runtime` 包含 `extract_model`、`verifier_model`、
`writing_model`、`embedding_model`、`model_timeout_seconds`、`max_retries` 和
`concurrency`。Bench II 包含 `model`、`reasoning_effort`、`max_output_tokens`
和 `model_timeout_seconds`。这些参数与原有 `evaluation` 区块中的评分线程数、
外层重试等选项分别作用于原生评测器的对应层级。

每个样本目录中的 `agent.effective.yaml` 保存实际生效的 Agent 参数，包括
默认值和环境回退结果，可直接作为 `main.py --config` 的输入。每次评分的
`evaluator.snapshot.json` 保存实际评测模型和 `runtime` 参数。两者均不包含
服务凭据；续跑时跳过的已完成样本保留原有效配置快照。根目录
`config.snapshot.yaml` 继续保留首次启动时的原始 YAML。

在消耗 API 配额前检查配置、密钥和样本数：

```bash
uv run python evaluate.py --config evaluate.yaml --check
```

## 运行

```bash
uv run python evaluate.py --config evaluate.yaml
```

`mode` 支持以下值：

- `run`：只运行 Agent 并保存报告。
- `evaluate`：评测 `input.run_dir` 中的统一运行结果，或者评测
  `input.native` 中的 Benchmark 原生报告。
- `run_and_evaluate`：运行 Agent 后立即评测。

### 并行运行样本

`agent.max_workers` 控制同时运行 Agent 的样本数，默认是 `1`，表示串行运行。
例如，抽取 5 条样本、最多同时运行 3 条，可以设置：

```yaml
sample_count: 5
agent:
  max_workers: 3
execution:
  evaluation_max_workers: 1
```

每条样本在独立子进程中运行，报告、日志和图谱 context 使用各自的样本目录。
`agent.timeout_seconds` 和 `agent.max_retries` 也分别应用于每条样本。

`execution.evaluation_max_workers` 控制后续同时评分的样本数，默认同样是 `1`。
在 `run_and_evaluate` 模式下，统一入口先等待这一批 Agent 运行结束，再开始评分。
Benchmark 配置中的 `evaluation.max_workers` 控制评测器内部并发，可与样本评分并发叠加。

结果默认保存在 `outputs/evaluations/<run_id>/`。每个样本的
`sample_result.json` 记录运行时间、评测时间、状态和指标。每次评测会在
`evaluations/<evaluation_id>/` 下生成独立的 `summary.json` 和可选的
`summary.md`。

Markdown 汇总只计算算术平均值。某个 Benchmark 的有效评测样本少于 10 个时，
报告会列出每个样本的指标和耗时；达到 10 个时只显示平均值。失败、超时和跳过的
样本不按零分计入平均值。

## 单独评测已有结果

将 `mode` 设为 `evaluate`，并指向已有运行目录：

```yaml
mode: evaluate
input:
  run_dir: outputs/evaluations/20260918-153012-graphresearcher
  native:
    deep_research_bench_jsonl: null
    wiki_live_challenge_markdown_dir: null
    deep_research_bench_ii_report_dir: null
```

如果报告并非由统一入口生成，可以使用原生格式导入：

```yaml
mode: evaluate
input:
  run_dir: null
  native:
    deep_research_bench_jsonl: imported/drb/graphresearcher.jsonl
    wiki_live_challenge_markdown_dir: imported/wiki/md_data
    deep_research_bench_ii_report_dir: imported/drb2/graphresearcher
```

DeepResearch Bench JSONL 使用 `id`、`prompt`、`article` 字段；Wiki Live Challenge 文件名
使用文章名称；DeepResearch Bench II 文件名使用 `idx-N.md`。
