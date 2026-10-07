# 生成与评估流水线

## 已确认决策

用户确认实现生成与评估的流水线调度。新增布尔字段 `execution.pipeline`，默认 `false`；仅在 `run_and_evaluate` 模式开启阶段重叠。`agent.max_workers` 和 `execution.evaluation_max_workers` 分别控制生成与评估样本并发，均支持大于 1。本地配置开启流水线并显式保留评估并发 1，现有生成并发和来源抽取并发保持原值。

## 行为边界

每个生成任务返回、报告及生成状态写入完成后，调度器将该样本提交到独立评估池。评估队列可以等待，不占用生成名额。汇总等待两个池全部结束；同一样本先写生成状态，再写评估状态，调度器最后以评估结果更新内存汇总。

关闭流水线时保持整批生成后评分。`run` 和 `evaluate` 模式保持各自独立执行；续跑跳过的已完成报告可直接进入评分。继续按已有文件资格规则评测失败或超时后留下的报告，并保留生成失败状态；无报告的生成任务不进入评分。已记录的失败和 `fail_fast` 的既有异常处理口径保持不变，正在运行的子进程不新增强制取消行为。

## 非目标与兼容策略

不改变图谱、报告格式、评分算法、服务配额、重试策略或进程内抽取限流。不新增跨进程模型限流，不调整现有并发数值。旧 YAML 省略开关时继续分阶段执行。新增开关必须是布尔值。

## 里程碑与验收

1. 接入配置与调度：评估目录和快照在派发前准备好，评估任务在生成任务交接后执行。
2. 离线回归：用事件同步证明阶段重叠，证明关闭开关保留阶段屏障，验证两个池大于 1 时的独立上限、续跑、失败报告、结果写入和单独运行模式。
3. 更新配置和文档：开启本地流水线，示例明确默认行为，完成相关测试和修改文件 Ruff 检查。

三个里程碑均属于本次授权范围。验证使用离线替身，不调用真实模型或图数据库；完成后不自动提交。

## 验证命令与进展

三个里程碑均已完成。调度逻辑提取到 `_execute_samples()`，生成任务交接后即提交评估；评估结果在所有生成结果收集后合入最终汇总，避免被较早的生成结果覆盖。配置和文档已同步，本地 `execution.pipeline` 为 `true`。

新增离线回归通过事件和屏障验证 `1+1`、`2+2`、`2+1`、`1+2` 的阶段重叠与独立并发上限，以及关闭流水线后的阶段屏障。测试还覆盖生成状态持久化后才评分、评分结果与汇总一致、续跑跳过生成、超时报告仍评分、无报告时跳过评分、评分异常以及单独运行模式。

以下检查全部通过，未发起真实 API 请求或图数据库读写：

```bash
uv run python tests/test_evaluation_pipeline.py
uv run python tests/test_evaluation_config.py
uv run python tests/test_evaluation_parallel.py
uv run python tests/test_evaluation_summary.py
uv run python tests/test_evaluation_timeout.py
uv run python tests/test_evaluation_model_retries.py
uv run python tests/test_evaluation_source_extraction_concurrency.py
uv run python tests/test_runtime_config.py
uv run python tests/test_evaluator_runtime_config.py
uv run python evaluate.py --config evaluate.yaml --check
uv run ruff check src/benchmarking/config.py src/benchmarking/orchestrator.py tests/test_evaluation_config.py tests/test_evaluation_pipeline.py
git diff --check
```
