# GraphResearcher 修改方案

本文基于当前代码库与 `outputs/run5` 的真实运行结果撰写。目标不是修补单个 prompt，而是结合 Tavily-only 搜索链路已经落地的事实，重新定义下一阶段改造重点。

当前系统已经不再处于“搜索抓不到正文”的阶段。新的主问题是：

1. 搜索输入质量提升后，系统在极少轮次里就会写入大量原子节点，但缺少预算控制、压缩层和交付层过滤。
2. Reporter 仍然直接面向大量细粒度 evidence 工作，缺少章节级写作资产，导致成稿泄漏内部结构并出现失真。
3. 收敛与交付校验仍然过宽，已经发现的报告问题不会阻止 run 被标记为 `COMPLETED`。

本文只给方案，不直接改代码。凡是涉及字段、数据结构、图谱对象类型、运行时状态语义和收敛门槛的部分，都属于待确认 plan；确认后再进入实现。

## 0. 结论先行

`run5` 说明，GraphResearcher 的风险已经从“搜不到”切换为“搜得太多但交付不受控”。

- 搜索工具已正确调用，Tavily 可以抓到 `raw_content`。
- 仅 2 次成功 SearchRun，就写入了 237 条 `Statement`、159 条 `Evidence`、11 个 `Document`、7 个 `Source`。
- 单个 query 的写入量已达到 `172 statements / 119 evidence` 与 `65 statements / 40 evidence`。
- 最终报告只显式使用了 2 个来源，却把内部 `evidence_id` 直接写进正文，出现了 `（证据：2026...）` 这类用户可见的内部标识。
- `report_validation_issues` 已经发现正文引用了时间窗口外来源，但 run 仍被标记为 `COMPLETED`。

这说明当前系统的问题不再只是“Reporter 没吃到足够事实”，而是四层设计同时失配：

1. 初始规划层仍偏向少量粗 query。
2. Searcher 抽取层缺少 statement/evidence 预算与 salience 控制。
3. Reporter 上游没有章节级压缩产物，只能直接消费海量原子 evidence。
4. convergence / delivery gate 不能阻止内部 ID 泄漏、时间窗口违规和弱引用质量报告通过。

## 1. run5 暴露出的新问题

### 1.1 内部证据标识泄漏到用户可见报告

`outputs/run5/report.md` 中多处出现：

- `（证据：20260701222726445506_d4e6f244、...）`

这不是单纯文风问题，而是内部图谱标识越过了产品边界。

根因在于：

- Reporter prompt 明确允许模型使用“证据 ID”，但没有明确禁止把这些 ID 写进正文。
- `submit_final_report` / report compiler 只校验 `source_ids` 与 `evidence_ids` 是否存在，没有把“正文包含内部 node id”视为 hard failure。
- Reporter 当前面对的是 `evidence_items` 原子列表，而不是已经整理过的章节 brief / evidence bundle，因此更容易把内部追踪 id 当成“引用形式”直接复制进 prose。

这类问题必须在交付层强拦截，而不应只靠 prompt 约束。

### 1.2 搜索成功后节点膨胀过快

`run5` 中只有 2 个 SearchRun succeeded，但已写入：

- `Statement`: 237
- `Evidence`: 159
- `Document`: 11
- `Source`: 7

写入量本身说明 `raw_content` 已经显著提升了 Searcher 的抽取能力；但当前系统没有“抽取预算”概念，导致 Searcher 会把长正文里的大量细碎事实全部升级成正式节点。

根因在于：

- 每个来源默认可带入最多 20k 字符的 `raw_content`。
- analyzer prompt 要求抽 statement + evidence，却没有上限、优先级、章节相关性或 objective-aware 过滤。
- `_merge_source_packets()` 会把所有抽出来的 statement/evidence 无差别写进 evidence_package。
- Query 评估和 Reporter bundle 读取也默认面向这些全量原子节点工作。

这会带来三个直接后果：

- 图谱噪声升高，低价值 statement 淹没高价值 statement。
- query sufficiency 容易被“证据密度”虚高。
- Reporter 被迫在大量原子 fact 中自行做压缩，稳定性下降。

### 1.3 图谱很大，但实际成稿只使用了极少来源

`run5` 最终报告只使用了 2 个来源，而图里已有 7 个 `Source`、11 个 `Document`。

这说明问题已经不是“没有证据”，而是：

- 没有把证据组织成可写作的章节资产。
- 没有对 evidence 做优先级压缩。
- 没有在交付前检查“图中事实密度”和“成稿实际引用覆盖”之间是否严重失衡。

换句话说，当前系统把“大量入图”误当成“准备好写作”。

### 1.4 交付校验发现问题，但不会阻止放行

`run5` 已被标记为：

- `research_state = COMPLETED`
- `report_readiness_score = 1.0`
- must objectives 全部 `satisfied`

但同一运行里仍存在：

- `report_validation_issues`: 正文引用了窗口外来源

这说明当前 convergence / readiness gate 仍然把报告校验当成“提醒”，而不是 stop condition。

对于真实交付，这种语义是不够的。至少以下问题应具备 hard-gate 属性：

- 内部 node id / evidence id 泄漏到正文
- forbidden source / out-of-window source 违规
- 正文无有效来源映射
- 章节虽有 prose，但无法绑定真实来源

## 2. 现状诊断

### 2.1 问题 A：写作素材仍然缺失

即便 Tavily 与 `raw_content` 已经解决“材料输入太薄”的问题，Reporter 上游仍然没有持续生产真正可写的对象。

- `export_report_context()` 仍然只输出 goal、queries、objectives、limitations、冲突和 `reference_registry`。
- `prepare_report_chapter_bundle()` 仍然按 query 拉取全量 `evidence_items`，没有章节级压缩。
- Reporter prompt 要求按主题组织章节，但缺少 `section_brief`、`entity_profile`、`comparison_slot`、`lead_candidate`、`timeline_slice` 这类一等写作资产。

因此，Reporter 虽然“有很多 facts 可用”，却没有“清晰的章节施工面”。

### 2.2 问题 B：搜索规划仍然偏粗，但抽取层已变得很重

原方案已经指出：query 规划过于依赖少量 coarse query。`run5` 证明这一点在 Tavily 时代变得更危险：

- coarse query 不再只是“搜歪”
- 它会直接带来“长正文 + 大量原子抽取 + 图谱膨胀”

也就是说，当前问题不是 Searcher fan-out 不够，而是：

- 上游 query 太粗
- 中游 source packet 太肥
- 下游 statement/evidence 升级门槛太低

这三者叠加后，图会在极少轮次内被撑大。

### 2.3 问题 C：当前 evidence model 仍把“抽到”近似等同于“值得入图”

现有主链：

- Query -> SearchRun -> Source / Document / Statement / Claim / Evidence

方向本身没有错，但缺少中间层：

- source-level extraction artifact
- chapter-level evidence bundle
- objective-aware salience filter

因此，所有抽取到的内容几乎都会直接进入正式知识图谱节点，导致：

- 高价值事实与低价值事实混杂
- 同一来源内部冗余 statement 大量堆积
- Report bundle 读取成本与 token 成本迅速上升

### 2.4 问题 D：delivery gate 仍然太弱

当前系统会在以下情况下仍然放行：

- must objective 已经“看起来满足”
- novelty / marginal utility 不再明显上升
- report compiler 接受了章节结构

但这些信号都不能保证：

- 正文没有泄漏内部结构
- 时间窗口和禁源约束已被满足
- 成稿真正覆盖了图中的主要证据资产

这意味着现有 gate 更像“研究流程结束判断”，而不是“最终交付通过判断”。

## 3. benchmark 影响面

### 3.1 deep_research_bench/query.jsonl

这类任务的风险依然是：

- 代表性对象不完整
- 结构化覆盖面不足
- 看似有结论，但证据覆盖不稳

在 Tavily 时代，还新增一个风险：

- 少量 query 就可能写入很多低价值事实，导致 coverage 虚高

### 3.2 DeepResearch-Bench-II/tasks_and_rubrics.jsonl

这类任务新增的主要风险是：

- 图里有很多 statement/evidence，但表格或 rubric 槽位仍未填满
- 时间窗口违规不会阻止最终通过
- section completeness 与 citation hygiene 没有被 hard-gate 化

### 3.3 Wiki Live Challenge / ga_100.json

WLC 类任务的风险比原方案更明显：

- 海量原子 evidence 不会自动转化为条目骨架
- lead、timeline、section hierarchy 仍然缺少专门资产
- 内部证据 ID 泄漏到正文，会直接破坏成稿可读性

## 4. 建议保留、替换与新增主线

### 4.1 建议保留

- 以 objective 作为 report-level contract 的方向应保留。
- Query -> SearchRun -> Source/Document/Statement/Claim/Evidence 的事实可追溯主链应保留。
- Searcher 与 Reporter 的角色分离应保留。
- `expand_gaps()` 这类从缺口到 follow-up query 的机制应保留，但要换 gap taxonomy 与调度规则。

### 4.2 建议彻底替换

- “最小 initial query 集覆盖 must objectives”作为默认规划目标，应替换为“按任务 archetype 输出阶段化 query portfolio”。
- “must objective = satisfied 或 blocked_best_effort 即可过关”的收敛规则，应彻底替换。
- “只要 evidence 足够多，就默认更接近 ready”的隐式语义，应替换为“evidence 经过预算控制、压缩和章节化之后，才有资格进入 readiness 判断”。

### 4.3 建议新增主线

在原方案的基础上，再新增两条一等改造主线：

1. extraction budget / salience control
2. citation hygiene / delivery validation hard gate

这两条现在已经不是增强项，而是 P0/P1 级问题。

## 5. 搜索与抽取改造方案

### 5.1 搜索规划仍应改为阶段化覆盖

保留原方案判断：

1. Horizontal discovery
2. Slot completion
3. Vertical deep dive / verification

但现在要明确补充：不同阶段不仅 query 粒度不同，抽取预算也必须不同。

### 5.2 新增 extraction budget 概念

建议引入三层预算：

- `per_source_extraction_budget`
- `per_query_statement_cap`
- `per_query_evidence_cap`

示意：

```text
discovery phase:
  每个来源只允许保留高 salience summary + 少量 top statements/evidence

slot completion phase:
  优先保留能补齐 table / roster / section slot 的 facts

deep dive phase:
  仅对高价值对象或冲突对象放宽抽取预算
```

### 5.3 Statement / Evidence 的升级门槛要提高

当前“抽到就入图”的策略需要改成两层：

第一层：

- 保留 source-level extraction artifact
- 允许完整保留较多来源内信息

第二层：

- 只有高 salience、与 objective / section / slot 有关、可独立支持结论的事实，才升级为正式 `Statement` / `Evidence`

也就是说，不是所有 analyzer 抽取结果都值得成为正式知识图谱节点。

### 5.4 去重与压缩不应只发生在 URL 层

当前主要靠 URL 去重，这远远不够。

需要新增：

- 同源 statement 近重复折叠
- 同义 evidence 聚合
- query 内 top-fact 选取
- objective-aware fact ranking

否则同一篇长文里的多个近义陈述会把图和 Reporter bundle 一起淹没。

## 6. 中间产物改造方案

原方案中“补 section_brief / entity_profile / comparison_slot / lead_candidate / readiness_checkpoint”这一方向应保留，而且重要性比原来更高。

### 6.1 仍建议第一阶段只正式拆出 `Objective` 与 `Gap`

这部分判断不变：

- `Analysis(objective)` -> `Objective`
- `Analysis(gap)` -> `Gap`

`Insight` 与写作中间产物第一阶段仍可继续留在 `Analysis` 子类型里，避免 schema 震荡过大。

### 6.2 但要新增两类过渡性对象

除了原方案中的写作资产，还建议新增：

- `source_packet_summary`
- `query_evidence_digest`

用途：

- `source_packet_summary`：承接来源级完整抽取，不要求全部升格成 statement/evidence
- `query_evidence_digest`：把 query 下的大量原子证据压缩成可供 MemoryManager / Reporter 消费的高层摘要

这样能在不立刻重构全部 schema 的前提下，把“完整抽取”和“正式入图”分层。

## 7. Reporter 上游与交付改造方案

### 7.1 Reporter 当前最缺的是“压缩后的章节施工面”

原方案已经指出，Reporter 缺的不是“更多事实”，而是“可直接写的组织单元”。`run5` 说明现在这个结论更强：

- Reporter 不是 facts 太少
- 而是 facts 太多、太原子、太贴近内部结构

### 7.2 chapter bundle 不应再默认拉取全量 evidence_items

当前 `prepare_report_chapter_bundle()` 会把 query 下所有 evidence/claim 分页全量取出。

建议改为：

- 默认提供 `section_brief`
- 默认提供 `top_evidence_items`
- 默认提供 `entity_profile`
- 默认提供 `comparison_slots`
- 默认提供 `lead_candidates`
- 如用户或章节 plan 明确需要，再按需展开更深层 evidence

也就是说，chapter bundle 应从“原子事实传输层”变成“章节写作输入层”。

### 7.3 必须禁止内部 ID 出现在最终正文

这是本轮方案必须新增的硬要求。

建议新增 deterministic 校验：

- 检测正文中的 `evidence_id` / `claim_id` / 长 node id
- 检测 `证据：2026...`、`e\d+`、`st\d+`、长时间戳式 node id
- 一旦发现，直接 `revision_requested = true` 或拒绝最终提交

内部 traceability 应只存在于：

- `source_ids`
- `evidence_ids`
- `disclosed_conflict_ids`
- ReportSection 绑定元数据

不应进入用户可见 prose。

### 7.4 citation hygiene 应进入 Reporter contract

当前 prompt 只要求“每个事实性段落都必须带引用”，但还不够。

建议再明确要求：

- 正文只允许出现编译器生成的 `[n]` 式引用
- 不得手写内部 source id / evidence id
- 不得把 `source_ids` / `evidence_ids` 当作正文的一部分输出

## 8. convergence / delivery gate 改造方案

### 8.1 原方案中的两层 gate 方向应保留

1. Evidence convergence
2. Delivery readiness convergence

### 8.2 现在必须再加第三层：delivery validation gate

建议 stop condition 拆成三层：

1. `evidence_converged`
2. `delivery_ready`
3. `delivery_validated`

第三层回答：

- 最终草稿是否满足时间窗口、禁源约束、引用规范、内部标识隔离等硬规则

只有三层都过，才能把 run 标成 `COMPLETED`。

### 8.3 建议提升为 hard gate 的问题

- out-of-window source 在非背景段落出现
- forbidden source 出现在正文
- 正文出现内部 node id / evidence id
- 正文章节没有有效来源绑定
- section content 与 `source_ids` 明显不匹配

这些不应只进入 `report_validation_issues`，而应能阻止最终放行。

## 9. gap / portfolio / utility 改造补充

原方案中的 gap taxonomy 方向仍然成立，但现在要补一个新维度：

- `extraction_overload`
- `evidence_noise`
- `citation_hygiene_failure`

这些不是传统 research gap，却会直接影响最终交付质量。

utility 也不应只考虑“再搜一轮值不值”，还要考虑：

- 当前 query 是否已经明显过载
- 进一步扩大 evidence 是否会恶化 Reporter 输入质量

换句话说，未来某些 query 应该优先触发“压缩/整理”而不是“继续搜索”。

## 10. 模块级改动清单

### 10.1 `src/prompts/memory_manager_prompts.py`

建议修改：

- `init_research`
  - 输出 task archetype + delivery contract + 分阶段 query portfolio
- `assess_query`
  - 除了判断 sufficiency，还要判断 evidence overload / chapter readiness
- `evaluate_portfolio`
  - 读取 readiness summaries，而不是只看 query summaries
- `assess_convergence`
  - 增加 delivery validation blockers
- `plan_followup_query`
  - 支持 slot completion query，不再只服务原子补洞

### 10.2 `src/agents/searcher.py`

建议修改：

- 引入 `per_source_extraction_budget`
- 引入 `per_query_statement_cap`
- 引入 `per_query_evidence_cap`
- 在 `_extract_source_packet()` 后增加 salience filter / near-duplicate collapse
- 区分“source-level完整抽取”与“正式入图 statement/evidence”
- submit 前生成 `query_evidence_digest`

### 10.3 `src/prompts/analyzer.md`

建议修改：

- 从“尽量多抽”改成“优先抽与 query objective 最相关、最可复用、最能支持章节写作的事实”
- 增加 top-k / salience / anti-dup 指令
- discovery 与 deep dive 阶段使用不同抽取预算

### 10.4 `src/prompts/reporter.md`

建议修改：

- 明确禁止在正文输出任何内部 id
- 明确正文只允许 reader-facing prose + 编译引用
- 要求优先消费 section briefs / lead candidates / entity profiles / comparison slots
- 要求面对过量证据时先压缩后写，而不是平铺原子 evidence

### 10.5 `src/tools/report_tools.py`

建议修改：

- chapter bundle 默认提供压缩后的高层资产，而不是全量 evidence_items
- `submit_final_report` 新增 internal-id leakage 检查
- `report_validation_issues` 中的时间窗口/禁源/内部 ID 问题升级为 hard gate
- 增加“图中来源数 vs 成稿实际引用来源数”这类 coverage sanity check

### 10.6 `src/tools/convergence.py`

建议修改：

- 不再把 `blocked_best_effort` 当作天然通过状态
- 增加 delivery validation gate
- 把 `report_validation_issues` 纳入 stop / continue 语义

### 10.7 `src/agents/memory_manager.py`

建议修改：

- `export_report_context()` 输出更多章节级与对象级写作资产
- `assess_convergence()` 不再只看 objective / utility，还要看 delivery validation
- readiness 不再与“图里证据多”近似等价

## 11. 优先级与实施顺序

### P0

- 修正 delivery gate：内部 ID 泄漏、时间窗口违规、禁源违规不得放行
- 修正 Reporter contract：禁止内部 id 出现在正文
- 引入 extraction budget / salience control
- 防止长正文在少量 query 下制造海量低价值 statement/evidence

这批改动最可能首先提升：

- 最终成稿可用性
- 交付正确性
- 图谱规模可控性

### P1

- 引入 task archetype 和 delivery contract
- 重写 initial query planning，按阶段输出 discovery / slot completion / deep dive
- 扩展 gap taxonomy，加入 roster/table/section/lead 类缺口
- 引入 `section_brief`、`entity_profile`、`comparison_slot`、`lead_candidate`、`query_evidence_digest`

这批改动最可能首先提升：

- 横向 coverage
- 章节组织质量
- Bench-II / WLC 的结构完成度

### P2

- 将 `Analysis(objective)`、`Analysis(gap)` 拆为 `Objective`、`Gap`
- 视验证结果决定是否继续拆 `Insight` 或升级更多中间产物为正式 NodeType
- 引入更细的 benchmark instrumentation

这批改动更偏 schema 固化与产品化。

## 12. 建议的实施路径

### Step 1

先修交付硬故障：

- 禁止内部 id 泄漏到正文
- 将时间窗口/禁源违规升级为 hard gate
- 让 report validation 真正影响最终放行

目标是先确保“不会继续产出明显坏报告”。

### Step 2

再修搜索成功后的节点膨胀：

- 引入 extraction budget
- 加入 salience filter / anti-dup
- 增加 source-level artifact 与 query-level digest

目标是先把“搜得太多”的问题从图谱层和 Reporter 输入层同时压住。

### Step 3

随后补章节级写作资产：

- `section_brief`
- `entity_profile`
- `comparison_slot`
- `lead_candidate`
- `readiness_checkpoint`

目标是让 Reporter 吃到真正可写的材料，而不是海量原子 evidence。

### Step 4

最后再推进 task archetype、delivery contract 与 `Objective` / `Gap` 拆分。

这样风险最低，也最容易逐步回归验证。

## 13. 验证方案

### 13.1 `run5` 定点复测

建议继续用当前“具身智能技术路线与代表公司”任务做定点复测，重点观察：

- 正文是否完全消失 `（证据：2026...）` 这类内部 id
- 是否不再出现窗口外来源在正文硬段落中被引用
- 2-3 个 query 下 statement/evidence 数量是否明显收敛
- 成稿实际引用的 source 覆盖是否不再严重落后于图中 source 数

### 13.2 小规模脚本级回归

建议至少覆盖：

1. 一个 open research 题
2. 一个 Bench-II 强结构题
3. 一个 comparative matrix 题
4. 一个 WLC entity article 题

每类只挑 1 到 3 个样本，先观察运行态信号。

### 13.3 新增强制测试项

建议新增或扩展：

- `tests/test_report_delivery.py`
  - 正文出现内部 evidence id 时必须拒绝
- `tests/test_search_budgeting.py`
  - 验证单 query / 单 source 抽取预算
- `tests/test_evidence_dedup.py`
  - 验证同源近重复 statement/evidence 折叠
- `tests/test_convergence.py`
  - report validation issues 不得继续放行
- `tests/test_task_archetype_contract.py`
  - archetype 与 delivery contract shape
- `tests/test_slot_completion.py`
  - roster / table / section slot 补齐逻辑
- `tests/test_wlc_readiness.py`
  - article readiness gate

### 13.4 benchmark 抽样评估

建议对三类 benchmark 分别抽样：

- deep_research_bench：10 个短开放题
- Bench-II：10 个强结构题
- WLC：10 个 entity article

重点关注五组指标：

- 搜索覆盖质量
- 图谱规模与噪声水平
- 结构完整度
- 成稿质量
- 收敛与交付正确性
