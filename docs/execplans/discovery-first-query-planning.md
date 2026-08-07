# Discovery-first Query 规划改造

## 目标

让 `init_research` 先创建精简的发现 Query，用首次搜索确认研究对象和检索术语，再由证据与报告级 Objective 驱动后续 Gap 扩展。初始 planner 不再输出 `request_complexity`，也不再为 Query 指定 `importance`。

## 已确认决策

- 单一对象、单一事实目标或连贯主题只生成一条初始发现 Query。
- 多个独立研究入口可以生成多条发现 Query，但数量同时受用户明确提出的入口数量和运行时预算上限约束。
- 初始 Query 上限从总搜索预算派生：有限预算最多使用一半，绝对安全上限为 8；无限预算仍使用 8 作为安全上限。
- planner 输出中删除 `request_complexity` 和 Query `importance`。
- 初始 Query 的 `importance` 由代码固定为 `core`；后续 Query 的 `importance` 由关联 Gap 派生。
- 初始 Query 使用内部 `query_role="discovery"`；Gap 生成的 Query 使用 `query_role="evidence_gap"`。该字段不由模型输出。
- discovery Query 的后续内容研究缺口使用 horizontal expansion，成为根级研究分支。
- 旧 planner 输出中残留的 `request_complexity` 和 Query `importance` 可以被忽略；已有图节点不迁移。

## 非目标

- 不修改 `NodeType`、`EdgeType` 或 Query 状态枚举。
- 不修改 `research_state` 的状态和值域。
- 不修改 Objective schema、收敛阈值、搜索预算计数或 Reporter 提交 shape。
- 不改变 Tavily 的调用方式，也不在本里程碑实现来源偏好排序。
- 不修复时间窗口字符串的上下界解析；该问题另行处理。

## 行为不变量

- 原始 User Request 仍逐字保存，Reporter 仍从原文读取写作要求。
- 每条 Query 仍只允许一次成功 SearchRun；后续工作必须通过 Gap 扩展。
- forbidden domain 仍由代码确定性地补到每条 Query。
- Query 文本仍必须独立、可直接提交给搜索引擎，不能包含写作任务或跨 Query 指代。
- 发现 Query 消耗正常搜索预算，其来源和证据可以进入最终报告。
- 初始 Query 少于运行时上限时不得补足；去重或非法 Query 不占用额度。

## 里程碑

### 里程碑 1：planner interface 与预算上限

- 重写 `init_research` prompt，删除具体领域示例、`request_complexity` 和 Query `importance`。
- 在 prompt 中注入 `{initial_query_limit}`。
- 新增纯函数，根据 `max_search_rounds` 计算初始 Query 上限。
- 收窄初始 Query 解析与选择 interface，并保留旧输出的宽容读取。

验收：单一对象 fixture 只创建一条发现 Query；多入口 fixture 最多保留动态上限数量。

### 里程碑 2：确定性优先级与 discovery 扩展

- 初始 Query 固定为 `importance="core"` 和 `query_role="discovery"`。
- 后续 Query 使用 `query_role="evidence_gap"`，importance 只从 Gap 派生。
- follow-up query prompt 不再要求模型返回 importance。
- `assess_query` 接收 `query_role`，并为 discovery Query 生成证据或 Objective 驱动的 horizontal gaps。
- Reporter 和 context 中按 `sem`、`priority` 排序，不按 importance 字符串排序。

验收：discovery Query 能完成自身识别标准，同时生成后续根级研究分支；`core` Query 的展示顺序稳定。

### 里程碑 3：回归验证

- 更新 planner、契约、图不变量和树状态机回归脚本。
- 验证旧 planner 额外字段被忽略。
- 运行定向回归和 Ruff。

## 兼容策略

- Neo4j 节点是 schemaless property 集合，新 `query_role` 不需要迁移。
- 旧 Query 没有 `query_role` 时按普通研究 Query 处理。
- `importance`、`sem`、`priority` 和 `priority_tier` 继续保存在 Query 节点上，避免改变现有调度接口。
- UserRequest 上已有的 `request_complexity` 保留但不再读取；新运行不再写入。

## 验收命令

```bash
uv run python tests/test_marginal_portfolio.py
uv run python tests/test_contract_v3.py
uv run python tests/test_graph_invariants.py
uv run python tests/test_tree_state_machine.py
uv run python tests/test_convergence.py
uv run ruff check src tests main.py test_wlc.py
```

## 实施结果

- 里程碑 1 已完成。`init_research` 不再输出 `request_complexity` 或 Query `importance`，运行时会把动态上限注入提示词，并再次截断模型返回的 Query 列表。
- 里程碑 2 已完成。初始 Query 固定使用 `importance="core"` 和 `query_role="discovery"`；Gap 扩展 Query 使用 `query_role="evidence_gap"`，其 importance 从 Gap 派生。
- 里程碑 3 已完成。相关 planner、契约、图不变量、树状态机、收敛、搜索生命周期和报告交付回归脚本均已通过。
- 定向 Ruff 检查已通过。仓库级 Ruff 检查仍报告 208 个既有问题，主要位于备份文件和独立测试脚本；本次没有扩大范围修复这些问题。
- 未运行真实 Neo4j CRUD 和模型端到端验证，避免污染现有图数据并产生额外 API 成本。
