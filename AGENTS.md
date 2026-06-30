# Repository Guidelines

## 项目结构与模块组织
`main.py` 是命令行入口，负责加载 `.env`、组装研究流程并输出 `report.md`、`research_graph.jsonl`、`run.log`。核心代码在 `src/`：`agents/` 放编排与角色代理，`tools/` 放图操作、搜索、报告与状态工具，`memory/` 放图存储与 schema，`prompts/` 放提示词模板。测试主要在 `tests/`，根目录的 `test.py`、`test_wlc.py` 更偏实验脚本。`outputs/` 为运行产物，除非明确需要，不要提交生成文件。

## 构建、测试与开发命令
使用 `uv` 管理环境与依赖：

```bash
uv sync
uv run python main.py "Compare RAG and long-context LLMs"
uv run pytest tests/
uv run ruff check src tests
uv run ruff check --fix src tests
PYTHONPATH=src OPENAI_API_KEY=dummy uv run python tests/test_query_handles.py
```

`uv sync` 安装依赖；`main.py` 用于端到端调试；`pytest` 跑常规单测；`ruff` 负责 lint 与 import 排序；个别脚本测试需要显式设置 `PYTHONPATH=src`。

## 编码风格与命名约定
默认 Python 3.11+，使用 4 空格缩进、`snake_case` 命名、Google 风格 docstring。保持仓库既有导入约定：直接从 `agents`、`tools`、`memory` 导入，而不是写 `src.` 前缀；新入口或脚本需保证 `src/` 已加入 `sys.path`。Ruff 已启用 `E/F/I/D/UP/T201`，但保留 `Optional[...]` 等现有类型写法，不必为“现代化”重写老代码。

## 测试规范
新测试文件命名为 `tests/test_*.py`，优先写可复现、无外部依赖的单测。涉及 LLM、Tavily 或 Neo4j 时，优先用 `monkeypatch` 或假对象隔离；不要让默认测试依赖真实密钥。涉及图文件落盘时，建议设置临时 `REPO_BASE_DIR`，避免污染本地 `~/.graphresearcher/` 数据。

## 提交与 Pull Request 规范
现有提交多为简短中文、面向问题，例如 `修复 graph 的bug`、`增加测试 wlc 代码`。建议采用“动作 + 模块/问题”的一句话摘要，聚焦单一改动。PR 需说明背景、行为变化、已执行命令；若改动 `graph_viewer.html`、报告输出或日志流，请附截图或关键输出片段，并关联相关 issue / 任务。

## 配置与安全
从 `.env.example` 复制本地配置，至少关注 `OPENAI_API_KEY`、`TAVILY_API_KEY`、`NEO4J_*`。不要提交真实密钥、运行日志或研究图数据；分享复现步骤时优先使用占位值。
