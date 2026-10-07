# 统一运行配置与本地迁移

## 已确认范围

用户确认统一 Agent 配置解析、接入 `main.py --config` 并记录实际生效配置，同时明确要求迁移所有当前配置参数。本次覆盖 Agent、Reporter、搜索以及三套评测器当前支持的运行参数。密钥、服务地址、数据库名称与认证信息保留在根目录 `.env`。

## 配置形状与边界

- `agent` 保留现有字段，增加 `model`、`model_timeout_seconds`、`search_timeout_seconds`、`assess_query_concurrency`。
- `agent.reporter` 包含 `model`、`model_timeout_seconds`、`packet_tokens`、`output_tokens`；模型留空时继承 Agent 模型。
- 三套评测器的模型、请求超时、输出长度、后端、重试和预处理并发放入各自的 `benchmarks.<name>.runtime`；已有抽样、流程、评分参数保持现有位置。
- 优先级统一为显式 CLI、显式 YAML、兼容环境变量、代码默认值。YAML 校验时保留字段缺省信息，运行前才补齐默认值。`max_retries` 缺省时改为允许环境回退，这是本次明确修正的旧优先级差异。
- `main.py` 只解析 Agent 区块，不要求启用 Benchmark。默认读取仓库根目录的 `evaluate.yaml`（若存在），显式 `--config` 优先；无配置文件时保持环境入口。这样清理本地 `.env` 后，原来的直接运行命令仍能使用已迁移的模型和预算。CLI 的轮数和日志选项只在显式提供时覆盖 YAML。
- 配置在 runtime 模块导入和共享信号量创建前应用，每个 Agent 子进程固定一份配置，不提供热更新。
- 每个样本写入白名单字段构成的 `agent.effective.yaml`；每次评分记录有效评测器参数。跳过的已完成样本保留其原快照。

## 兼容策略与非目标

环境变量仍作为兼容输入和子进程内部传递机制。迁移本地 `.env` 前保存权限受限的本地备份，比较迁移前后解析值和服务凭据；不打印密钥或将备份纳入 Git。无调用点的旧 Reporter 参数只归档，不制造无效 YAML 字段。进一步检查发现 `NEO4J_TIMEOUT` 仅声明常量，未传入驱动，因此同样归档；本次不新增数据库超时行为。

本次不改变图谱 schema、Query 状态机、报告提交结构、搜索预算计算或评测器评分算法，也不调整模型、并发与预算的实际取值。示例中的值使用已有代码默认值，本地值以迁移前的最终生效配置为准。

## 里程碑与验收

1. 完成共享解析器和字段映射，离线验证类型、缺省、覆盖顺序及独立字段。
2. 接通两个启动入口与评测器适配，验证真实子进程在导入时读取正确配置，快照不含凭据。
3. 更新文档和配置示例，备份并迁移本地参数，比较所有映射参数的有效值和所有保留凭据。

以上三个里程碑均已获授权。完成后停止，不自动提交或运行付费端到端测试。

## 验证

运行配置解析、Agent 启动、评测器环境映射的新增离线测试，以及既有评测配置、子进程超时、模型重试、样本并发、来源并发和报告交付相关回归。修改文件通过 Ruff，并执行全仓库检查记录既有问题。

## 进展

三个里程碑均已完成。共享解析器位于 `src/run_config.py`，直接运行和统一评测都在导入 Agent runtime 前应用参数；三套评测器通过原有环境映射接收 YAML 中的运行参数。

本地迁移将 25 个已有环境参数转入 YAML，并补齐当前缺省参数。原 YAML 中的并发、重试、轮数、任务超时、抽样和输出设置保持不变。10 个无效旧变量已从 `.env` 移除，原值保存在 `outputs/config-migration/20261006-111924/` 中。该备份目录权限为 `0700`，文件权限为 `0600`，且被 Git 忽略。26 个保留变量的解析值逐项一致，迁移前后的完整有效配置以及提交前适配器实际传入的评测参数也已比较一致。

以下离线验证已通过，没有发起真实模型请求或图数据库读写：

```bash
uv run python tests/test_runtime_config.py
uv run python tests/test_evaluator_runtime_config.py
uv run python tests/test_evaluation_config.py
uv run python tests/test_evaluation_source_extraction_concurrency.py
uv run python tests/test_evaluation_model_retries.py
uv run python tests/test_evaluation_parallel.py
uv run python tests/test_evaluation_timeout.py
uv run python tests/test_source_extraction_concurrency.py
uv run python tests/test_langfuse_observability.py
uv run python evaluate.py --config evaluate.yaml --check
git diff --check
```

修改涉及的 Python 文件通过 Ruff。全仓库 `uv run ruff check src tests main.py test_wlc.py` 仍报告 216 个既有问题，包括不存在的 `test_wlc.py`。`tests/test_report_delivery.py` 在第 164 行的 context 字段集合断言失败；使用提交前的 `main.py` 和迁移前环境再次执行，复现相同失败。此次未修改相关报告字段或放宽断言。
