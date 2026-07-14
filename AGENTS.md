# AGENTS.md —— 共享协作规则

这个文件是本仓库里所有编码代理（Claude、Codex 等）的共享工作约定。开始修改之前先通读
它，然后再遵循 `CLAUDE.md` 这类面向具体代理的补充说明。

---

## 最高优先级协作规则

- 涉及字段、数据结构或实现逻辑变更时，必须先和用户确认 plan。plan 需要说明 proposed
  shape、行为边界和影响面。用户确认后，可以在 plan 范围内自主实现，不需要每个小改动都
  再次授权；如果实施过程中发现需要超出已确认 plan 的字段、runtime 语义、图谱状态机、
  报告提交 shape、迁移策略或校验规则，必须暂停并通知用户讨论。讨论中的草案不能当成已
  批准的实现。

---

## 基本工作方式

- 用小步、可验证的方式推进工作。
- 优先复用现有模式，不要轻易引入新抽象。
- 除非出于安全性或正确性必须扩大范围，否则把改动控制在当前任务内。
- 保留用户已经做过的修改，不要回退无关工作。
- 提交应当是有意义的最小单元，不要积攒成大批量改动。

---

## 项目现状

这个仓库是一个由 `uv` 管理、面向 Python 3.11+ 的单体 Python 项目。

- 运行时入口位于仓库根目录，主要包括 `main.py` 和 `test_wlc.py`。
- 源码位于 `src/` 下，核心目录包括 `src/agents/`、`src/tools/`、
  `src/memory/`、`src/prompts/`，以及 `src/config.py`。
- 图谱存储当前以 Neo4j 为准。`graph_viewer.html` 读取导出的 JSONL 快照做可视化；
  JSONL 在这里是 viewer / export 格式，不是主数据库。
- `tests/` 下有不少文件是独立回归脚本，它们会 monkeypatch `tools.graph_tools`，
  因而可以在没有真实 Neo4j 实例的情况下运行。不要默认整个测试面都是传统的 pytest 套件。
- `CLAUDE.md` 仍然有参考价值，但如果它和当前代码冲突，以代码和 `pyproject.toml`
  为准。

---

## 代码风格

优先采用 **pure core, imperative shell**。

在这个仓库里，优先把下列逻辑写成纯函数或接近纯函数的数据变换：

- 图节点、边和 payload 的组装
- prompt section、report section、validation issue 的构造
- 过滤、分组、去重、排序、打分和派生集合
- query / evidence / source 视图模型的投影

优先使用 Python 里可读性好的不可变式写法，例如：

- list / dict / set comprehensions
- `any`, `all`, `sorted`, `sum`, `zip`, `enumerate`
- 小而明确的命名 helper
- 先组装数据，再执行副作用

当顺序、局部状态或资源生命周期本身就是语义的一部分时，保留命令式写法：

- agent orchestration loops
- middleware retries / nudges / guardrails
- async session / event-loop lifecycle
- Neo4j read-write flows
- 文件导出、日志镜像、批处理脚本

可读性优先于炫技。

---

## Async 与副作用

- `src/memory/graph.py` 里的 `GraphManager` 方法是 async 的；`src/tools/graph_tools.py`
  提供同步包装，并维护一个持久后台 event loop。修改图谱读写逻辑时，先看清楚当前调用链在
  用哪一层，不要随意混用。
- 纯计算逻辑尽量放在易测的 helper 里；LLM、Neo4j、web search、文件系统这些副作用留在
  边界层。
- 新增跨模块副作用时，优先复用现有边界：`config` 负责模型和 prompt 装配，
  `memory` 负责图存储，`tools` 负责 agent-facing capability。
- 如果功能依赖 run context，请保持 `set_context` / `clear_current_context` /
  导出 JSONL 这套隔离语义一致。不要悄悄把“单次运行隔离”退化成“全局共享图”。

---

## 数据与运行时契约

下列内容都属于高风险协作面，修改前需要先给用户 plan：

- `NodeType` / `EdgeType` 枚举
- Query 状态机与状态迁移约束
- `research_state` 的 runtime 语义
- Reporter 提交的 payload shape、章节 schema、引用绑定规则
- 图谱校验、收敛判定、query handle 解析、claim normalization 等核心规则

额外约束：

- Neo4j 是当前的事实来源。`export_graph_jsonl()` 只负责把当前 context 导出给
  viewer，不要在新实现里默认回退到“每次 mutation 直接写 JSONL 文件”。
- 任何影响报告可交付性的规则，都要同时考虑 `report_tools`、`middleware`、
  `main.py` 的最终交付路径，而不是只看单个 helper。
- 改动 query tree、objective coverage、search budget 或 report delivery 时，
  优先补齐或运行对应的独立回归脚本。

---

## 模块与导入约定

- 这个仓库的运行时导入约定是把 `src/` 放进 `sys.path`，然后使用裸包名导入：
  `agents.`, `tools.`, `memory.`, `prompts.`, `config`。
- 不要在源代码里写 `src.xxx` 或假定 `deep_research` 是日常运行时 import path。当前项目
  的入口脚本和测试主要依赖 `PYTHONPATH=src` 或显式 `sys.path.insert(...)`。
- 新的仓库根目录脚本、一次性回归脚本或独立测试，如果要导入 `src/` 下模块，
  也要显式处理这件事。
- 路径操作优先用 `pathlib.Path`。不要把 Windows / WSL 路径分隔符硬编码进新逻辑。

---

## 文档与注释（中文写作）

Comments、README、`CLAUDE.md`、`AGENTS.md`、`方案.md`、测试说明和其他面向未来维护者的
文档，都要写成让人顺着读得下去的文字，而不是压缩过的提交日志。

- 解释、推导和说明性的段落用完整、自然的句子。避免电报式碎片表达。
- 表格、清单、步骤这类本来就该紧凑的形式可以保持简洁；这条规则主要约束散文段落。
- 中英文混排只在英文确实是代码标识符、环境变量或专有名词时才使用，例如
  `GraphManager`、`submit_final_report`、`OPENAI_BASE_URL`。
- 新写的 commit message 正文、调试说明和 runbook 也适用这条规则。

---

## 复杂改造的执行计划

涉及多个模块、多个运行时契约或需要分阶段迁移的改造，应当维护独立的 ExecPlan。

- ExecPlan 要列明已确认决策、非目标、里程碑、行为不变量、兼容策略、验收标准和验证命令。
- 每次只实施用户明确授权的里程碑；达到当前里程碑的验收标准后停止，不自动进入下一阶段。
- schema 迁移、业务语义变化和新增能力应尽量拆成不同里程碑。
- 不得通过删除测试、放宽断言或改变无关预期来使实现通过。
- 当前代码与既有 plan 不一致时，应先记录差异并更新 plan，不能静默扩大实施范围。

---

## 测试

验证强度要和改动风险相匹配。

- 依赖 / 环境准备：`uv sync`
- Lint：`uv run ruff check src tests main.py test_wlc.py`
- 自动修复格式和 import 问题：`uv run ruff check --fix src tests main.py test_wlc.py`
- 独立回归脚本：`uv run python tests/test_<name>.py`
- 真实图谱 CRUD 集成验证：`uv run python tests/test_graph_tools.py`

说明：

- `tests/` 里不少文件既可以被 pytest 风格收集，也可以直接当脚本跑；在不确定整体测试基建
  是否完整时，优先运行与改动最相关的单个文件。
- `tests/test_graph_tools.py` 会触达真实图数据库配置。运行前确认 Neo4j 环境是否可用，并尽量
  使用独立 context，避免污染已有数据。
- `uv run python main.py "..."` 和 `uv run python test_wlc.py ...` 属于高成本验证：
  会消耗模型/API 配额，运行时间也可能较长。只有在任务确实需要端到端验证、并且用户已知晓
  成本时才运行。

---

## 环境与密钥

- 运行时配置来自 `.env` / `.env.example`。常见变量包括 `OPENAI_API_KEY`、
  `OPENAI_BASE_URL`、`GR_MODEL`、`GR_MODEL_TIMEOUT`、`TAVILY_API_KEY`、
  `NEO4J_URI`、`NEO4J_USERNAME`、`NEO4J_PASSWORD`、`NEO4J_DATABASE`。
- 不要提交真实密钥，不要把用户本地 `.env` 的值写回仓库。
- `REPO_BASE_DIR` 只在旧的 JSONL 备份实现里出现；除非用户明确要求恢复那套行为，否则不要把
  新功能建立在这个遗留变量上。