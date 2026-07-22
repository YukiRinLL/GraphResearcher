# 在收敛判断前确定性刷新过期的研究组合

## 背景

`get_next_actions` 会在 `evaluated_portfolio_revision` 落后于 `portfolio_revision` 时要求执行 `evaluate_research_portfolio`。旧实现仍允许 Orchestrator 同时调用 `get_next_actions` 和 `assess_convergence`；后者看到组合评估过期后只能返回相同的下一动作。如果模型持续忽略该动作，两次成功的工具调用不会触发失败熔断，运行会反复消耗模型调用而没有状态进展。

## 决定

`assess_convergence` 将组合评估视为自身的确定性前置条件。研究状态仍为 `RESEARCHING`、Query tree 有效且组合版本过期时，它在同一个 `MemoryManager` 状态锁内先调用一次现有 `evaluate_research_portfolio`，刷新 Query 快照后再执行原有收敛判断。刷新失败时返回明确 error，不继续进行无效收敛。

Orchestrator prompt 同时禁止在同一模型回合并行调用 `get_next_actions` 和 `assess_convergence`。Prompt 只用于减少无效调用；即使模型违反顺序，工具层仍能保证状态前进。

## 影响

正常的 current-portfolio 路径不增加模型调用。stale 路径执行的 portfolio evaluation 正是状态机原本要求的调用，不会增加逐 Query 或逐 criterion 成本，也不会自动搜索、扩展 Gap 或绕过报告授权条件。
