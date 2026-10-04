# Claim 规范化输入指纹与复用

## 目标与授权

用户已于 2026-10-04 确认本计划。本里程碑只减少同一运行内、同一 Query 对相同自有材料的重复规范化。父 Query 在子 Query 完成后的充分性评估继续执行；验收结束后停止。

## 已确认决策

- 从现有模型输入提取纯函数，保留 Query 约束、Statement/Evidence 正文与引用字段、来源可信度。材料按节点 ID 稳定排序，JSON 键顺序稳定，指纹包含 prompt 模板和内部版本。
- 缓存属于一个 `MemoryManager` 实例，以 `(context, query_id)` 定位，每个键只保留最近一次结果。内部记录包含指纹、模型实例、原有返回结果及实际写入的绑定；不新增图字段或迁移。
- 命中跳过模型调用和图写入，返回独立副本。命中日志不进入模型输入或公开返回结构。
- 仅在非空结果完整写入后发布缓存。模型异常、解析失败、空输出、边写入返回空 ID 以及模型降级 fallback 不缓存。没有 Statement 的确定性 fallback 成功后可以缓存。
- 命中前检查 Claim 仍属于当前评估子图，来源绑定仍存在，并检查已写入的 Objective 绑定。来源绑定利用既有评估子图；Objective 边不在评估子图中，命中时通过一次全边读取检查，避免逐 Claim 查询。
- 按 context 和 Query 加锁；全局状态锁只用于建立锁记录，不覆盖模型调用。不同 Query 保持并行。

## 非目标与行为不变量

本次保留 Claim key、来源绑定、fallback、Query 状态机、portfolio、Reporter 和模型配置的现有规则。输入变化后仍完整规范化，不做增量合并或清理历史 Claim。Neo4j 继续作为事实来源，JSONL 只用于离线验证。新运行会重建 manager；缓存不跨进程持久化。

模型实例替换、模板变化、材料增删或字段变化均失效。Query 状态、子 Query 完成状态和已有 Claim 不参与输入指纹。缓存只代表规范化结果复用，不代表 Query 已充分或研究可以交付。调用方修改返回值不会修改缓存。

## 实施步骤

1. 建立缓存调用次数、失效边界、结果副本、失败重试和并发回归，确认当前实现可触发失败。
2. 提取输入构造函数，加入运行内缓存、按 Query 的锁和绑定记录，保持返回 shape。
3. 运行 Claim、Query 合同和 Reporter 读取视图回归，以及样本 17 的离线指纹验证。

## 验收标准

- 同一输入连续调用，规范化模型只调用一次，第二次没有图写入；材料顺序和字典键顺序不影响命中。
- 材料增删、内容或来源可信度变化、Query 约束变化、模板或模型实例变化会重新规范化。
- 不同 context 和 manager 相互隔离；返回值修改不污染缓存。
- Claim 删除、来源或 Objective 解绑后重新规范化；失败和降级不会留下可命中的结果。
- 同一 Query 并发不会重复调用模型，不同 Query 可以同时进入模型调用。
- 父 Query 再次评估时复用规范化结果，但仍执行充分性评估。
- 既有不相关失败保持可见，不删除测试或放宽断言。

## 验证命令

```bash
uv run python tests/test_claim_normalization_cache.py
uv run python tests/test_claim_normalization.py
uv run python tests/test_claim_normalization_regressions.py
uv run python tests/test_contract_v3.py
uv run python tests/test_marginal_portfolio.py
uv run python tests/test_report_completeness.py
uv run python tests/test_report_read_view.py
uv run ruff check src tests main.py test_wlc.py
```

## 基线与进展

确认 plan 前已运行 Claim 基线：`test_claim_normalization.py` 通过。`test_claim_normalization_regressions.py` 的六项测试中有四项失败，分别涉及空 claims 的 fallback、无效引用、缺失 Evidence 绑定和 key 碰撞。这些语义不属于本里程碑；碰撞测试会通过修改实际输入保证第二次仍执行模型，保留原断言。

- 三个实施步骤均已完成，本里程碑验收结束。
- 新增 `test_claim_normalization_cache.py` 共十四项回归全部通过。实现前已有五项失败，能够捕获重复模型调用、重复写入、父节点重评和同 Query 并发的问题；最后补充的空边 ID 回归也先验证失败，再完成修复。
- `test_claim_normalization.py`、`test_report_completeness.py` 和 Reporter 的九项 `test_report_read_view.py` 回归通过。缓存命中保留原有返回结构，充分性评估仍使用最新图谱；不同 Query 的模型调用可以同时进入屏障，未被全局锁串行化。
- Claim 的四项既有失败仍然存在，原断言全部保留。另有两项既有失败：`test_contract_v3.py` 的独立审查预期与当前交付路径不一致，`test_marginal_portfolio.py` 的 planner 返回结构预期缺少当前字段。已在独立进程加载提交前 HEAD 的 `memory_manager.py`，复现这两项失败；没有修改其预期。
- 单独执行 Query 合同中的原始请求初始化、criterion 验证和评估重试三项函数，全部通过，避免最后的既有审查失败掩盖相关验证。
- 三个改动 Python 文件的 Ruff 检查通过。全仓 Ruff 仍有 217 项既有问题，包括仓库缺少 `test_wlc.py`；改动文件没有 lint 问题。`git diff --check` 通过。

## 样本 17 的离线验证结果

验证使用本次 trace 中十二次可见规范化的实际输入和历史模型输出，以及样本 17 导出的图谱。模型边界只返回历史文本，存储边界仅修改内存数据；未调用真实模型或 Neo4j。

每次调用前，将 Query 和 Statement/Evidence 投影与 trace 输入逐项比较，并验证新纯函数的输入完全一致，只有材料顺序和 JSON 键顺序被稳定化。随后通过实际 `normalize_claims` 和 Query 评估子图投影执行重放。

十二次调用中，八次进入模型边界，四次命中缓存：`q4.1` 一次、`q4` 一次、`q4.2` 两次。命中时 Claim 和边写入计数均保持不变。这四次历史模型调用的耗时合计为 991.617 秒，约 16.5 分钟。该数值表示本次历史重复调用对应的耗时，不是优化后真实端到端运行的测速结果；缺失的并行 span 不参与统计。
