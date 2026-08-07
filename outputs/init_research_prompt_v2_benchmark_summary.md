# init_research Prompt benchmark 抽样测试

## 测试条件

- 模型：`gpt-5.6-luna`
- `max_search_rounds`：20
- 动态初始 Query 上限：8
- 未执行网页搜索
- 未连接或修改 Neo4j

## 最终结果

| Benchmark | 样本 | Objective | 初始 Query | 禁止 URL | Query 域名约束 | 结果 |
|---|---|---:|---:|---:|---|---|
| Wiki Live Challenge | Ring of Nestor | 1 | 1 | 1/1 | 与 `excluded_domains` 一致 | 通过 |
| DeepResearch-Bench-II | task7 土地财政 | 5 | 4 | 3/3 | 未扩大具体 URL 为禁止域名 | 通过 |
| DeepResearch-Bench-II | task1+ 南亚社会保障 | 3 | 4 | 6/6 | 未扩大具体 URL 为禁止域名 | 部分通过 |
| Deep Research Bench | id 6 具身智能 | 3 | 1 | 0/0 | 无额外域名 | 通过 |
| Deep Research Bench | id 52 投资哲学比较 | 1 | 3 | 0/0 | 无额外域名 | 通过 |

所有模型生成的 Query 均通过运行时 `_select_initial_queries` 校验。

## 主要观察

- Wiki 样本只生成一条精确名称发现 Query。Objective 不再包含导言、章节、引文编号或参考文献区段等写作安排。
- 土地财政样本保留了用户明确要求的数据年份、指标、负面后果、转型机制、住房政策和四种税制，没有压缩成一个笼统 Objective。
- 南亚社会保障样本按四个明确国家建立四个入口，完整保留 6 个禁止 URL。第一轮测试曾错误地把这些 URL 所在域名写成 `-site:` 条件；补充一致性规则后已消除。
- 具身智能样本仍使用一条上游分类发现 Query，没有预先列举模型记忆中的路线或公司。
- 三位投资人的比较任务为三个明确对象分别建立入口，没有继续按投资哲学属性拆分。

## 未完全解决的问题

- 南亚社会保障样本的 `language`、Objective 和 Query 都是英文，但 `research_goal` 仍偶发使用中文。Prompt 已明确要求自然语言字段与报告语言一致，说明在当前模型温度下仍存在随机性。
- Prompt 只能保存禁止 URL 和域名，不能用现有 schema 表达禁止文章的标题、作者及其他镜像身份。
- `time_window` 仍无法区分报告截止日期、研究对象时期和来源发表日期。这属于运行时语义问题，不在本次 Prompt-only 改动范围内。

## 文件

- `outputs/init_research_prompt_v2_benchmark_results.json`：第一轮结果，用于记录发现的问题。
- `outputs/init_research_prompt_v2_benchmark_results_final.json`：补充呈现隔离、域名一致性和语言规则后的最终结果。
