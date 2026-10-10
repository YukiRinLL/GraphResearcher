# 运行成本优化的正确性修复

## 目标与授权

用户于 2026-10-09 确认本计划。当前里程碑修复 `1ca7851` 至 `b5ebe21` 的审核问题：合并评估缓存降级结果、熔断降级使用旧子图、后续 Query 去重不完整，以及来源模型路由变更后的测试隔离失效。

## 已确认决策

- 合并评估返回空或缺失的 `claims` 时，保留现有确定性 fallback，但不发布内存或磁盘缓存。有效模型结果完整写入后仍可复用。
- 合并规范化使用新的缓存指纹版本。旧版本合并缓存无法证明是否来自 fallback，因此统一重新计算；独立规范化缓存仍按原有版本校验。
- 合并调用熔断后，先独立规范化，再以刷新后的评估子图重新渲染 assessor prompt。纠正重试也使用这份新输入。
- 同一轮扩展中的草稿、批量结果、重试和单组补写共享已接受的查询文本。重复候选交给现有补写流程，落图前再次检查；仍无法生成有效查询时沿用现有 blocked 路径。
- 来源抽取测试在 `source_analyzer` 模型边界注入假模型，同时验证默认模型回退、专用模型选择和路由缓存隔离。

## 当前契约与历史计划的关系

`claim-normalization-reuse.md` 记录的是已完成的运行内缓存里程碑。当前分支已将缓存键扩展为 `(context, query_id, purpose)`，返回结构包含 `source`，并可在运行目录的 `.llm_cache` 下持久化规范化和 portfolio 结果。本次保留这些现有接口，并恢复“模型空输出或降级结果不缓存”的约束。

落盘结果只有在输入指纹、模型身份及当前图绑定通过检查后才能复用。标准运行入口会清理当前 context，因此磁盘缓存本身不构成图谱断点恢复能力。

## 非目标与行为不变量

本次不增加图字段、公开返回字段、配置项或状态转换规则，不改变 Reporter 合同、收敛规则、搜索预算计算和 Neo4j 事实来源地位。保留同一 Query 的规范化锁以及不同 Query 的并行能力，不重写历史 Claim，也不修复无关的既有测试失败。

## 兼容策略

只有合并规范化缓存的指纹版本改变；旧缓存按未命中处理，成功计算后覆盖同一缓存文件，不删除图数据。Query 文本沿用现有 `_normalize_query_text` 规则去重，各组仍独立绑定自己的 Gap。已有 Query 不进行事后合并或删除。

## 里程碑与验收

当前仅有一个已授权里程碑：完成上述修复、回归及文档同步后停止。

1. 在实际评估和扩展路径建立离线回归，先确认缺陷可以稳定触发。
2. 修复并验证：降级不命中内存或磁盘缓存，有效合并结果可复用，旧合并缓存失效；熔断后的 assessor 可以读取新 Claim；所有扩展来源和重试之间无重复落图，失败仍走 blocked。
3. 验证模型路由及证据定位、来源并发、Query 树、收敛脚本，运行 lint 和 diff 检查，记录既有失败。

## 验证命令

```bash
uv run python tests/test_claim_normalization_cache.py
uv run --with pytest python -m pytest -q tests/test_llm_circuit_and_portfolio_drafts.py
uv run python tests/test_runtime_config.py
uv run python tests/test_evidence_locations.py
uv run python tests/test_source_extraction_concurrency.py
uv run python tests/test_tree_state_machine.py
uv run python tests/test_convergence_livelock.py
uv run python tests/test_blocked_objective_convergence.py
uv run ruff check src tests main.py test_wlc.py
git diff --check
```

模型及图存储在测试边界替换，不运行付费端到端研究任务。

## 进展

当前里程碑已完成。

- 修复前运行缓存及规划测试，新增回归稳定触发旧合并缓存命中、空 Claim 降级缓存、熔断后的旧输入和三种重复 Query 路径。测试共报告 8 项失败（含子用例），确认断言能够捕获本次缺陷。
- 修复后，`test_claim_normalization_cache.py` 与 `test_llm_circuit_and_portfolio_drafts.py` 合计 27 项测试、22 个子用例全部通过。覆盖内存及磁盘缓存、有效结果重启复用、旧合并缓存失效、独立缓存兼容、assessor 纠正重试、跨轮规划去重、草稿与规划混用、补写预留后续组文本，以及补写失败的 blocked 行为。
- 验证命令中的 7 个独立脚本全部通过，包括 18 项 Claim 缓存测试、13 项证据定位检查，以及配置、来源并发、Query 树和两组收敛回归。来源抽取测试显式禁止构建真实模型；模型路由测试通过假模型工厂验证默认回退、专用选择及缓存隔离。
- 改动 Python 文件的 Ruff 检查和 `git diff --check` 通过。全仓 Ruff 仍有 216 项既有问题，包含缺失的 `test_wlc.py`。将修改前 HEAD 导出至临时目录后，按诊断编号、相对文件名和消息逐项比较，问题集合完全相同。
- 验证未调用真实模型或 Neo4j，没有运行付费端到端评测。
