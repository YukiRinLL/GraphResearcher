# DeepResearch Agent 统一评估执行计划

## 目标

为仓库中的 DeepResearch Agent 提供一个统一评估入口，支持
DeepResearch Bench、Wiki Live Challenge 和 DeepResearch Bench II。运行参数由根目录
`evaluate.yaml` 管理，密钥和 API 地址只从根目录 `.env` 读取。

## 已确认决策

- 支持 `run`、`evaluate` 和 `run_and_evaluate` 三种模式。
- 全局种子与 Benchmark 名称共同决定抽样，各 Benchmark 的样本集相互独立。
- 每个样本记录 Agent 运行时间和评测时间。
- JSON 汇总始终生成；Markdown 汇总可关闭。
- Markdown 中只展示平均值。有效评测样本少于 10 个时，先逐项展示后再给出平均值；达到 10 个时只展示平均值。
- 失败、超时和跳过的样本不按零分计入平均值。
- 三套 Benchmark 保留各自的评分语义，不计算跨 Benchmark 总分。

## 非目标

- 不修改 Research Graph schema、Query 状态机、`research_state` 语义或 Reporter payload。
- 不改变 Benchmark 的评分 prompt 和计分公式。
- 不将 JSONL 恢复为图谱主存储。

## 行为不变量

- 选中的样本 ID 在首次运行时写入 `selected_samples.jsonl`，恢复和单独评测不重新抽样。
- 每个 Agent 样本使用独立输出目录和进程。
- 每次评测写入新的 evaluation attempt，不覆盖旧分数。
- 配置快照不包含密钥。

## 里程碑与验收

1. 配置、环境与抽样：`--check` 可以在不调用 API 的情况下完成校验，相同种子产生相同样本 ID。
2. Agent 运行：生成样本级报告、日志、状态和运行时间，支持超时与恢复。
3. Benchmark 适配：可分别调用三套原生评测器，保存样本级分数与评测时间。
4. 汇总：生成 `summary.json` 和可选 `summary.md`，并正确实现 10 个样本的展示阈值。
5. 回归：通过 Ruff、配置/抽样/汇总单元测试和无 API 的 `--check` 验证。

## 验证命令

```bash
uv sync
uv run ruff check src tests main.py evaluate.py
uv run python tests/test_evaluation_config.py
uv run python tests/test_evaluation_selection.py
uv run python tests/test_evaluation_summary.py
uv run python evaluate.py --config evaluate.yaml.example --check
```
