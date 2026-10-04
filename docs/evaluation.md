# 统一 Benchmark 评估

`evaluate.py` 用同一个入口运行 GraphResearcher，并调用 `Benchmark/` 中的
DeepResearch Bench、Wiki Live Challenge 和 DeepResearch Bench II。

## 准备配置

先将示例文件复制为本地配置：

```bash
cp evaluate.yaml.example evaluate.yaml
cp .env.example .env
```

`evaluate.yaml` 保存种子、样本数、运行模式和 Benchmark 参数。根目录
`.env` 保存 Agent 和评测器的密钥、API 地址与模型名称。统一入口会忽略
Benchmark 子目录中的 `.env`。

`agent.timeout_seconds` 控制每条样本从启动 Agent 到生成报告的总耗时上限，
默认是 7200 秒。正数表示限时秒数；设为 `-1` 时，统一入口会等待 Agent
子进程运行结束。`0` 和其他负数是无效配置。该设置不包含后续 Benchmark 评分，
单次模型请求超时、搜索超时、重试次数和 `agent.max_rounds` 仍各自生效。

`agent.max_retries` 设置 Agent 每次模型调用的 HTTP 自动重试次数，默认是 `3`。
该值必须是非负整数；`0` 表示仅发送首次请求，`1` 表示首次请求失败后最多
再尝试一次。它适用于证据抽取、证据评估和报告生成等使用模型工厂的调用。
统一入口将该值通过 `GR_MODEL_MAX_RETRIES` 传给 Agent 子进程，覆盖根目录
`.env` 中的同名值。Query 搜索与 Reporter 工作流的外层尝试次数、后续
Benchmark 评分的重试配置仍各自生效。

```yaml
agent:
  timeout_seconds: -1
  max_retries: 1
```

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
