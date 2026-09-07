# DeepResearch Bench 接入计划

## 已确认决策

用户已确认本计划。Bench I 新增根目录运行脚本，Bench II 在现有脚本上完善；两者都通过 `main.run()` 生成报告，并委托各自仓库的官方脚本评分。评测子进程使用对应 benchmark 的 `.env`，其中的值优先于父进程同名变量，不修改 agent 进程的配置。

Bench I 的提交文件是 `{id, prompt, article}` JSONL，任务来自 `data/prompt_data/query.jsonl`，支持 RACE、FACT 和完整评测。Bench II 保留 `report/<model>/idx-<n>.md`、`result.jsonl` 和汇总 CSV。两个入口都支持抽样、固定 seed、跳过已有报告、仅评测已有报告和逐题运行产物。

Bench I 的本地 `.env` 复用 GraphResearcher 的 OpenAI 兼容服务 key、URL 和 WLC 的 Jina key，使用本地官方实现的默认评测模型。Bench II 保留已有凭据与模型设置。真实凭据只保存在被 Git 忽略的本地 `.env` 中。

## 非目标与行为不变量

本次不修改 agent 核心、图谱字段、状态机、报告提交契约、官方评分算法或 Python 环境。每题仍由 `main.run()` 按输出目录隔离 Neo4j context。Bench II 仅把顶层 `prompt` 送入 agent，不把 `content` 中的评测 rubric 暴露给生成过程。原始提示词和最终报告正文保持原样，只有评测器执行其官方清洗步骤。

报告、评测中间文件和日志保存在指定输出目录。官方仓库的数据与参考报告保持原样。只评分已生成的任务，Bench I 的抽样清单与提交文件保持一致；续跑导出时保留同一输出目录中已有的任务报告。

## 里程碑

本次授权覆盖一个交付里程碑：完成两个入口、对应本地配置、使用说明和离线回归验证。真实模型、搜索、Neo4j 和付费评测的端到端运行不属于本次验证。

- [x] 新增 Bench I 生成、导出和官方评测入口。
- [x] 完善 Bench II 的环境隔离和仅评测入口。
- [x] 配置两个仓库的本地 `.env`，补充无凭据示例和中文运行说明。
- [x] 完成离线回归及改动文件的 lint。

## 兼容策略与当前差异

Bench II 已有生成、断点评分及汇总逻辑，已有回归通过。它目前直接继承父进程环境，可能覆盖其 `.env`；本次显式传入 benchmark 的配置。已有参数和默认输出布局继续可用，新增参数采用可选形式。WLC 入口保持现有行为。

Bench I 尚无 `.env`，官方 Python 模块只读进程环境，因此由新入口加载配置后传给各评测子进程。Bench I 的官方脚本通过工作目录定位 rubric 和参考报告，子进程工作目录必须是 benchmark 仓库；可变产物路径均显式指向 GraphResearcher 输出目录。

检查官方 RACE 实现后确认，它会累积已有结果，但部分语言任务新增后仍可能重新评分旧任务。适配脚本单独生成 `race_query.jsonl`，排除已有成功结果的任务；完整任务清单仍供 FACT 使用，官方评分和汇总算法保持原样。

## 验收标准与验证命令

离线测试使用临时目录和替身生成器、评测命令，验证输入映射、抽样复现、续跑导出、失败任务排除、官方命令参数、环境隔离、仅评测入口及 Bench II 的既有断点评测。配置检查只输出是否存在或匹配，不输出密钥值。CLI 帮助和本地数据加载可在不调用外部服务的情况下执行。

```bash
uv run python tests/test_deepresearch_bench.py
uv run python tests/test_deepresearch_bench_ii.py
uv run python tests/test_wlc_env.py
uv run python test_deepresearch_bench.py --help
uv run python test_deepresearch_bench_ii.py --help
uv run ruff check test_deepresearch_bench.py test_deepresearch_bench_ii.py tests/test_deepresearch_bench.py tests/test_deepresearch_bench_ii.py
```

## 验证结果

2026-09-07 完成上述全部离线回归、两个入口的 CLI 帮助检查和改动文件的 lint。另用现有解释器检查了官方 RACE、FACT 五个模块、Bench II 评分及汇总共八个入口的 `--help`，均通过；实际输入读取到 Bench I 的 100 题与 Bench II 的 132 题。没有调用真实模型、搜索或 Neo4j。

Bench I 的 `.env` 已写入，Bench II 的现有 key 与 URL 经检查与 GraphResearcher 一致并予以保留。两个仓库的 `.env` 均被 Git 忽略，凭据值未输出。全量命令 `uv run ruff check src tests main.py test_wlc.py` 报告 207 项既有问题，涉及未修改的备份文件、文档字符串、导入和测试中的 `print` 等；本次不扩大范围修复。
