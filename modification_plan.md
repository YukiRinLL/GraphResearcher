# GraphResearcher 修改方案

本文基于当前 GraphResearcher 代码库撰写，目标不是修补单个 case，而是系统性解决两类问题：

1. 研究链路偏向“事实可追溯”，没有持续生产“可写作素材”。
2. 搜索链路没有真正实现“横向铺开 + 纵向深挖”，并且当前收敛逻辑会把“分数涨不动”误判成“报告基本可交付”。

本文只给方案，不直接改代码。凡是涉及字段、数据结构、图谱对象类型、运行时状态语义和收敛门槛的部分，都属于待确认 plan；确认后再进入实现。

## 0. 结论先行

当前系统的问题不在单一 prompt，也不在 Searcher 是否偶尔搜歪，而在三层设计共同叠加：

1. 初始规划层把“最小 query 数覆盖 objective”作为默认最优解，天然偏向少量大 query。
2. 搜索执行层被明确限制为“基本逐字检索，不 fan-out”，因此无法在执行期弥补上游 query 过粗的问题。
3. 评估与收敛层把 query sufficiency、objective coverage 和 marginal utility 当成主信号，但这些信号并不直接衡量“是否已形成可成稿的章节素材包”。

因此，系统会稳定地产生一种假阳性：

- 图里已经有不少 source、statement、evidence、claim。
- LLM 也能给出看似合理的 objective coverage/confidence。
- 但 Reporter 仍然拿不到章节 brief、实体画像、时间线、对比矩阵、lead 候选、证据束这类写作中间产物。
- 最后表现为 coverage 似乎够了，成稿却仍然不平衡、不连贯、不像高质量文章。

`outputs/run5` 当前不存在。我实际参考了 `outputs/run4`。该运行里只有 3 个 query，却已经将多个明显属于“章节素材未补齐”的 gap 打成 `deferred_low_value`，同时 `company_profiles` objective 在 `coverage=0.6` 的情况下被标为 `blocked_best_effort`。这与用户指出的问题完全一致。

## 1. 现状诊断

### 1.1 问题 A 的根因

根因不是 Reporter 写得不够好，而是上游没有生产它真正需要的对象。

- `MemoryManager.init_research()` 会把任务压成少量 initial queries，并且 `_select_initial_queries()` 明确追求“最小 query 集覆盖 must objectives”，这会奖励“大而全 query”，而不是可写作分层。[`src/agents/memory_manager.py:237`](src/agents/memory_manager.py:237) [`src/agents/memory_manager.py:380`](src/agents/memory_manager.py:380)
- `assess_query` prompt 要求的是 query sufficiency 和 atomic gaps，但 gap 类型仍是事实/验证导向，没有“章节是否可写”的判断框架。[`src/prompts/memory_manager_prompts.py:86`](src/prompts/memory_manager_prompts.py:86)
- `evaluate_portfolio` prompt 只看 objective coverage/confidence，没有 section completeness、table completeness、lead support、article balance 之类的结构信号。[`src/prompts/memory_manager_prompts.py:215`](src/prompts/memory_manager_prompts.py:215)
- `export_report_context()` 给 Reporter 的输入仍然非常薄，只包含 goal、queries、objectives、limitations、冲突和 reference registry，没有 chapter brief、entity profile、comparison slots、timeline、lead facts 等写作资产。[`src/agents/memory_manager.py:2133`](src/agents/memory_manager.py:2133)
- Reporter prompt 已经明确要求按主题组织、写 lead、形成章节，但上游没有提供与这些要求一一对应的结构化材料，Reporter 只能从分散 evidence 中临时拼接。[`src/prompts/reporter.md:12`](src/prompts/reporter.md:12)

表象包括：

- 章节不平衡。
- 叙事更像拼接摘要而不是成稿。
- 表格或对比槽位容易缺格。
- WLC lead 难写，正文像 evidence aggregation。

### 1.2 问题 B 的根因

根因不是 Searcher 能力不足，而是系统默认工作流把“query 规划”和“执行 fan-out”都收得过紧。

- `init_research` prompt要求 initial queries 是 compact、coarse，并由代码选择最小覆盖集合，这会把任务天然压成少量粗 query。[`src/prompts/memory_manager_prompts.py:11`](src/prompts/memory_manager_prompts.py:11) [`src/agents/memory_manager.py:380`](src/agents/memory_manager.py:380)
- `web_searcher` prompt 明确要求基本逐字执行 query，并且禁止拆成多个改写查询，不允许在 Searcher 层做真正的横向展开。[`src/prompts/web_searcher.md:4`](src/prompts/web_searcher.md:4)
- `expand_gaps()` 目前是一种“缺啥补啥”的后继机制，而且每个 search subject 最多只生成一个 child query，更像局部 repair，而不是预先设计的阶段化搜索。[`src/agents/memory_manager.py:1270`](src/agents/memory_manager.py:1270)
- `evaluate_research_portfolio()` 采用 deficit + impact + confidence_gain 的 utility，且对已有 search subject 给较高 redundancy 惩罚，这会早早压制横向补齐型 gap，尤其是 roster、taxonomy、table-cell 这类需要广铺的工作。[`src/agents/memory_manager.py:1135`](src/agents/memory_manager.py:1135)

表象包括：

- 先用一个超大 root query 粗抓资料。
- 再只对 fatal conflict 或少数显性缺口继续展开。
- 横向 coverage hole 被当成低收益 deferred。
- 代表性对象不全、taxonomy 不稳、矩阵槽位不满。

### 1.3 收敛误判的根因

这是当前最危险的问题，属于机制级误判，不是 prompt 波动。

- objective coverage/confidence 主要来自 LLM 评估，若拿不到可靠值，就退回 query 的最高 sufficiency_score。[`src/agents/memory_manager.py:1037`](src/agents/memory_manager.py:1037)
- 当 objective 未达到 coverage/confidence 阈值，但连续几轮 realized gain 低，就会被标成 `blocked_best_effort`。[`src/agents/memory_manager.py:1080`](src/agents/memory_manager.py:1080)
- `assess_convergence()` 只要 must objectives 全部处于 `satisfied` 或 `blocked_best_effort`，就视作 objectives_ready。[`src/agents/memory_manager.py:1525`](src/agents/memory_manager.py:1525)
- `tools.convergence.structurally_converged()` 也重复了同样的逻辑，把 `blocked_best_effort` 视作结构收敛。[`src/tools/convergence.py:98`](src/tools/convergence.py:98)
- 现有测试已经把“低 gain 两轮后变成 blocked_best_effort”固化成预期，这说明问题不是偶发现象，而是代码与测试共同确认的当前产品语义。[`tests/test_tree_state_machine.py:251`](tests/test_tree_state_machine.py:251)

这会导致一个错误等价：

- “继续搜，分数涨不动”
- 被当成
- “这个必须目标可以按 best effort 通过”

但对于写作型任务，尤其是 Bench-II 和 WLC，这两者并不等价。

## 2. benchmark 影响面

### 2.1 deep_research_bench/query.jsonl

这类任务多为开放研究题、短 prompt、目标边界松。

风险不是完全答不上来，而是：

- 只回答到显眼主线，没有把横向对象铺开。
- 比较维度不稳定。
- 代表性 roster 不完整。
- 看起来“已经有结论”，但缺少支持结论的覆盖面。

这类任务最容易被“大 query + early convergence”伤害。

### 2.2 DeepResearch-Bench-II/tasks_and_rubrics.jsonl

这类任务通常有强结构、强时间边界、强表格、强禁源约束、强分部分交付。

风险是：

- objective 分数看起来不低，但 rubric 槽位未填满。
- section completeness 不足。
- table cell completeness 不足。
- time-bounded coverage 没被硬性约束到 section/cell 级别。
- forbidden source constraint 没进入 gap 和 convergence gate。

这类任务不能只用“must objective 是否涨不动”来判断是否可交付。

### 2.3 Wiki Live Challenge / ga_100.json

这类任务是典型实体文章写作，lead、section hierarchy、文风、摘要能力和引用组织都很关键。

风险是：

- 图里 facts 很多，但没有 lead facts、entity profile、timeline、section evidence bundle。
- Reporter 只能临时拼写，不容易形成百科文章常见的稳定骨架。
- 正文像“按来源摘录的摘要”，不像 article。

WLC 需要单独的 article readiness gate，而不应与一般 research report 共用一套弱收敛逻辑。

## 3. 建议保留、替换与渐进演化

### 3.1 建议保留

- 以 objective 作为 report-level contract 的方向应保留。
- Query -> SearchRun -> Source/Document/Statement/Claim/Evidence 的事实可追溯主链应保留。
- Searcher 与 Reporter 的角色分离应保留。
- `expand_gaps()` 这类从缺口到 follow-up query 的机制应保留，但要换 gap taxonomy 和调度规则。

### 3.2 建议彻底替换

- “最小 initial query 集覆盖 must objectives”作为默认 query 规划目标，应替换为“按任务 archetype 生成阶段化 query portfolio”。
- “must objective = satisfied 或 blocked_best_effort 即可过关”的收敛规则，应彻底替换。
- 只围绕事实缺口/冲突缺口的 gap taxonomy，应替换为“事实 + 结构 + 写作素材”混合 taxonomy。

### 3.3 建议渐进演化

- `Analysis` 的现状已经明显过载。第一阶段应先把任务合同层的
  `objective`、调度缺口层的 `gap` 从 `Analysis` 中拆出，分别形成
  `Objective`、`Gap` 正式节点类型。
- `Insight` 第一阶段可以暂时留在 `Analysis`，避免一次性把证据层分析、
  阶段性总结和写作中间产物全部同时重构。
- 写作素材对象和 readiness 对象第一阶段仍可继续复用 `Analysis`
  子类型承载，等 Reporter、收敛和 benchmark 验证中证明有效，再决定
  是否把其中一部分继续上升为正式 NodeType。

这条路径最符合当前仓库“先小步验证，再固化契约”的协作方式。

## 3.4 `Analysis` 拆分方案

当前实现里，`Analysis` 同时承担了三层职责：

1. report-level 研究目标：`Analysis(objective)`
2. query-level 缺口：`Analysis(gap)`
3. query-level 阶段性总结：`Analysis(insight)`

而在原始 KG schema 语义里，`Analysis` 更适合回到证据管理层，用于承载
围绕 `Claim / Statement / Evidence` 的中间分析结果。基于当前确认的实施
范围，建议第一阶段先拆出两类正式节点：

- `Objective`
  - 替代当前 `Analysis(objective)`
  - 仅允许挂在 `UserRequest` 下
  - 保留现有字段：`objective_key`、`description`、`requirement`、
    `weight`、`acceptance_criteria`、`coverage`、`confidence`、`status`、
    `low_gain_streak`、`last_evaluated_successful_rounds`、`assessment_reason`
- `Gap`
  - 替代当前 `Analysis(gap)`
  - 仅允许挂在 `Query` 下
  - 保留现有字段：`gap_key`、`description`、`importance`、`status`、
    `gap_category`、`objective_keys`、`search_subject_key`、
    `decision_impact`、`confidence_gain`、`estimated_search_rounds`、
    `acceptance_criteria`、`marginal_utility`、`objective_deficit`、
    `resolution_reason`

第一阶段明确不做：

- 不把 `Insight` 拆成正式节点类型
- 不立即重做证据层 `Analysis`
- 不立即把所有写作中间产物都升级成正式节点类型

第一阶段的目标是先把当前最容易污染图谱语义、最影响收敛和调度逻辑的
两类对象拆干净：

- `UserRequest -HAS_OBJECTIVE-> Objective`
- `Query -HAS_GAP-> Gap`

与此同时，`Analysis` 暂时保留两类用途：

- `insight`
- 写作中间产物 / readiness checkpoint 的过渡性承载容器

这样可以先把任务合同层和调度层拆清楚，再单独决定证据层分析与写作素材层
是否继续细分。

## 4. 任务分型方案

建议引入 task archetype classification，并把它当成 research contract 的一部分。

### 4.1 待确认的 proposed shape

建议在 `UserRequest` 运行时 contract 中增加一组任务元信息：

```json
{
  "task_archetype": "open_research|structured_report|comparative_matrix|entity_article|timeline_history|causal_analysis",
  "delivery_contract": {
    "required_sections": ["..."],
    "required_dimensions": ["..."],
    "required_tables": [
      {
        "table_key": "stable-key",
        "columns": ["..."],
        "row_expectation": "enumerated|at_least_n|derived_from_scope"
      }
    ],
    "time_boundary": "string|null",
    "forbidden_sources": ["..."],
    "style_contract": "research_report|wikipedia_article"
  }
}
```

这里是 plan shape，不是建议直接落库。是否进入正式 runtime contract，需要用户确认。

### 4.2 archetype 的实际作用

- `open_research`：关注 coverage breadth、代表性对象、核心争议与主要结论。
- `structured_report`：关注 section completeness、part completeness、时间边界和限制项。
- `comparative_matrix`：关注 roster completeness 和 table-cell completeness。
- `entity_article`：关注 lead coverage、section skeleton、timeline completeness、人物或实体 profile。
- `timeline_history`：关注时间轴节点连续性、阶段转折和关键事件证据。
- `causal_analysis`：关注因果链节点、机制解释、反例或限制条件。

不同 archetype 应决定：

- 初始 query portfolio 的形状。
- gap 类型优先级。
- utility 加权。
- convergence gate。
- Reporter 上游素材结构。

## 5. 搜索规划改造方案

### 5.1 规划目标从“最小覆盖”改为“阶段化覆盖”

建议把当前 query 规划拆为三阶段，而不是一开始就问“几个 coarse query 最能覆盖所有 objective”。

1. Horizontal discovery
2. Slot completion
3. Vertical deep dive / verification

### 5.2 第一阶段：horizontal discovery

目标不是把每个 objective 做深，而是先把“写作骨架需要的主对象/主维度/主路线”铺出来。

不同 archetype 的第一阶段产出应该不同：

- open_research：路线、学校、流派、公司、国家、主要争议。
- comparative_matrix：候选对象 roster、比较维度、时间边界。
- entity_article：章节骨架、关键时期、关键人物、主要作品/事件。
- structured_report：章节主问题、表格槽位、限制条件、国家/案例清单。

建议 query 粒度改为“单一搜索意图 + 单一主题簇”，而不是“把整个任务塞进一条 query”。

粒度建议：

- 一条 query 最多服务一个主主题簇。
- 一条 query 最多覆盖一个主要 roster 发现任务，或一个主要维度补齐任务。
- 如果 query 文本里同时出现“路线 + 公司 + 产品 + 商业化 + 融资 + 团队”，基本就已经过粗。

### 5.3 第二阶段：slot completion

这一步是当前系统缺失最明显的层。

目标是把第一阶段暴露出的写作槽位补齐，而不是继续泛搜新事实。

典型 slot 包括：

- 每条路线的代表公司 roster。
- 每家公司的固定画像维度。
- 每张表的 cell。
- 每个章节的 lead facts。
- 每个 timeline 段的关键事件。

这一步应该优先于 fatal conflict 深挖之外的大多数“额外细节”。

### 5.4 第三阶段：vertical deep dive / verification

只有在以下情况才进入真正纵深：

- 槽位已经大体齐全，但某个高影响维度还不可靠。
- 出现影响主结论的 conflict。
- 需要 primary source 验证。
- 需要对高权重对象做 deeper profile。

### 5.5 对当前代码的落地建议

- 改 `init_research` prompt，不再要求 compact coarse query，而是要求输出 `phase_1_queries` 和 `phase_2_expectations`。
- `_select_initial_queries()` 不再只做最小覆盖，而是做“每个 must objective 至少保留一个 discovery query + 必要的 slot discovery query”。
- `plan_followup_query` 不再只服务 atomic gaps，还要能服务 slot-completion gap。
- Searcher 仍然不做任意自由 fan-out，但允许在同一 phase contract 下执行“同一 search subject 的受控子查询集合”。

## 6. 中间产物改造方案

这是提升 WLC 写作质量和 Bench-II 完整度的关键。

### 6.1 第一阶段的节点策略

当前 `NodeType` 已经较稳定，而且 AGENTS 明确把结构修改视作高风险协作面。[`src/memory/graph.py:21`](src/memory/graph.py:21)

在本轮已确认范围内，建议第一阶段只新增两个正式节点类型：

- `Objective`
- `Gap`

其余新增中间产物暂时继续复用 `Analysis` 节点，新增若干 `analysis_type`：

- `section_brief`
- `chapter_brief`
- `entity_profile`
- `timeline_slice`
- `comparison_slot`
- `lead_candidate`
- `evidence_bundle`
- `readiness_checkpoint`

这样做的好处是：

- 只对当前最过载、最影响主流程的 `Analysis(objective)` 和
  `Analysis(gap)` 做结构拆分。
- `UserRequest` 和 `Query` 的父子关系会变得更清晰，收敛、调度和状态机
  也更容易理解。
- 仍然避免一次性把 `Insight` 和写作中间产物都升级为正式节点类型。
- 可以先验证这些对象是否真的改善 Reporter 和 convergence。
- 便于回滚和迭代 shape。

### 6.2 待确认的 proposed shape

建议这些对象统一带上三组字段：

```json
{
  "analysis_type": "section_brief|entity_profile|comparison_slot|...",
  "artifact_key": "stable-key",
  "owner_scope": {
    "objective_keys": ["..."],
    "query_ids": ["..."],
    "chapter_id": 1,
    "entity_name": "optional",
    "slot_key": "optional"
  },
  "content": {
    "summary": "...",
    "fields": {},
    "status": "draft|usable|weak|missing",
    "coverage": 0.0,
    "confidence": 0.0
  },
  "source_ids": ["..."],
  "evidence_ids": ["..."]
}
```

### 6.3 谁生产，谁消费

- MemoryManager 生产：
  - section/chapter brief
  - comparison slot
  - readiness checkpoint
- Searcher submit 后的归纳逻辑生产：
  - entity profile
  - timeline slice
  - lead candidate
  - evidence bundle
- Reporter 消费：
  - 章节大纲
  - 每章 evidence bundle
  - entity profile
  - timeline
  - comparison slots
  - lead candidates
- Convergence 消费：
  - readiness checkpoint
  - section/table/lead completeness

### 6.4 最重要的新增对象

如果只能先做一小批，我建议优先做这五个：

1. `entity_profile`
2. `comparison_slot`
3. `section_brief`
4. `lead_candidate`
5. `readiness_checkpoint`

它们分别对应：

- 比较型任务的横向整理。
- Bench-II 表格与维度填充。
- WLC 和长报告的章节搭骨架。
- lead 写作。
- 收敛防误判。

## 7. gap / portfolio / utility 改造方案

### 7.1 现有 gap taxonomy 的问题

当前 gap 类型是：

- `missing_core_evidence`
- `fatal_conflict`
- `enrichment`
- `additional_example`
- `verification`
- `detail`

它本质上还是证据工程 taxonomy，不是交付工程 taxonomy。[`src/prompts/memory_manager_prompts.py:95`](src/prompts/memory_manager_prompts.py:95)

### 7.2 建议新增 gap taxonomy

建议把 gap 分成三组：

第一组，事实与验证型：

- `missing_core_evidence`
- `fatal_conflict`
- `verification`
- `primary_source_missing`

第二组，覆盖与结构型：

- `coverage_hole`
- `roster_hole`
- `taxonomy_hole`
- `table_cell_missing`
- `time_slice_missing`
- `country_case_missing`

第三组，写作素材型：

- `section_brief_missing`
- `entity_profile_missing`
- `lead_support_missing`
- `chapter_bundle_missing`
- `section_balance_missing`

### 7.3 utility 公式为什么会压制横向扩展

当前公式的核心问题有三点：

- deficit 是按 objective 阈值缺口算的，而不是按“尚缺多少对象/槽位/章节素材”算的。
- redundancy 对已探索 subject 惩罚过强，导致同一路线下的补齐工作被判成重复劳动。
- rounds 惩罚会压低 roster/table 补齐型工作，因为这类工作天然要多轮铺开。

因此，一旦 objective 已接近阈值，横向补齐几乎都会被降成低 utility。

### 7.4 建议的新 utility 组成

建议把 utility 改成按 archetype 可配置的四项组合：

```text
utility =
  structure_gap_weight * structure_deficit
  + coverage_gap_weight * coverage_deficit
  + evidence_gap_weight * evidence_deficit
  + decision_impact_weight * decision_impact
  - redundancy_penalty
  - cost_penalty
```

其中最关键的是加入：

- `structure_deficit`
- `roster_deficit`
- `table_completion_deficit`
- `lead_support_deficit`

对比型任务和 WLC，这些项应高于普通 evidence_gain。

### 7.5 调度规则建议

- 在 archetype 未完成基础骨架前，`coverage_hole`、`roster_hole`、`table_cell_missing`、`section_brief_missing` 不能被轻易 defer。
- `fatal_conflict` 仍可强制优先。
- `enrichment` 和 `detail` 只有在结构骨架完整后才有资格竞争。

## 8. convergence 改造方案

### 8.1 必须改掉的核心规则

必须禁止：

- must objective 仅凭 `blocked_best_effort` 就视为 ready。

更准确地说，不是完全删除 `blocked_best_effort`，而是降低它的语义：

- `blocked_best_effort` 只能表示“该 objective 在当前预算或公开资料下继续提升困难”。
- 它不能单独作为报告通过条件。

### 8.2 新的两层 gate

建议把收敛拆成两层：

1. Evidence convergence
2. Delivery readiness convergence

第一层回答：

- 继续搜索是否还能显著提升事实可靠性。

第二层回答：

- 现有材料是否足以交付目标 archetype 所要求的文章或报告。

只有两层都过，才能进入 Reporter。

### 8.3 待确认的 proposed shape

建议新增 `readiness_checkpoint` 的统一结构：

```json
{
  "analysis_type": "readiness_checkpoint",
  "checkpoint_type": "global|section|table|lead|article",
  "artifact_key": "stable-key",
  "status": "ready|not_ready|blocked",
  "metrics": {
    "coverage": 0.0,
    "confidence": 0.0,
    "structure_completeness": 0.0,
    "slot_completeness": 0.0,
    "lead_support": 0.0
  },
  "blocking_reasons": ["..."]
}
```

### 8.4 archetype-specific gate

建议至少定义四套 gate：

- `open_research`
  - 主结论 coverage 过线
  - 代表性 roster 达到最低覆盖
  - 关键争议有披露
- `structured_report`
  - required sections 全部可写
  - required tables/cells 达到阈值
  - 时间边界与禁源约束通过
- `comparative_matrix`
  - roster 完整度过线
  - 核心比较维度缺格率低于阈值
- `entity_article`
  - lead_support 过线
  - article skeleton 稳定
  - timeline 与主要主题 section 均有 evidence bundle

### 8.5 WLC 单独 gate

WLC 建议单独加一个 `article_readiness_gate`，至少检查：

- lead 是否有足够 high-salience facts 支撑。
- 是否已经形成稳定 section skeleton。
- 每个主 section 是否有至少一个可写 evidence bundle。
- 是否有 timeline 或 life-cycle 素材支持过渡。

### 8.6 Bench-II 单独 gate

Bench-II 建议单独加 `section_table_completion_gate`：

- required section 是否全部 ready。
- required table 的列与行是否达到预期。
- 是否仍有 forbidden source 风险。
- time-bounded evidence 是否覆盖到 section/cell。

## 9. Reporter 上游改造建议

### 9.1 当前 Reporter 缺的不是“更多事实”，而是“可直接写的组织单元”

Reporter prompt 本身并不差，它已经在要求：

- 先提大纲。
- 再按章读取 bundle。
- 写连贯 prose。
- 写 lead。

问题在于 `export_report_context()` 和 chapter bundle 目前没有提供足够强的上游结构。[`src/prompts/reporter.md:13`](src/prompts/reporter.md:13) [`src/agents/memory_manager.py:2133`](src/agents/memory_manager.py:2133)

### 9.2 最少需要补的上游结构

如果保留现有 Reporter 机制，最少要补：

- `section_brief`
- `chapter_evidence_bundle`
- `entity_profile`
- `comparison_slots`
- `lead_candidates`

这五类对象足以显著改善：

- lead 起笔。
- 章节重心。
- 段落过渡。
- 横向比较的一致性。
- 冲突与限制披露位置。

### 9.3 可以参考 ms-agent/deep_research/v2 的迁移方向

如果参考业界更成熟的 deep research 流程，值得迁移的不是“再加一个写手 prompt”，而是这几类机制：

- 先形成 delivery plan，再做检索补齐。
- 研究过程中维护 section/table/slot 的 completion state。
- 把对象级 profile 和章节级 brief 当成一等产物。
- 在 report-ready 之前做 article/report readiness 审核，而不是只看 evidence density。

## 10. 模块级改动清单

### 10.1 `src/prompts/memory_manager_prompts.py`

建议修改：

- `init_research`
  - 从“compact coarse queries”改成“输出 task archetype + delivery contract + 分阶段 query portfolio”。
- `assess_query`
  - gap taxonomy 扩展为覆盖型、结构型、写作素材型。
  - 明确要求判断“是否足以支撑 section/table/entity profile/lead candidate”。
- `evaluate_portfolio`
  - 输入不再只看 query summaries，而要看 readiness summaries。
- `assess_convergence`
  - 从“fatal conflict 分类”扩展为“fatal conflict + delivery readiness blockers”。
- `plan_followup_query`
  - 支持 slot completion query，而不是只写原子补洞 query。

### 10.2 `src/agents/memory_manager.py`

建议修改：

- `init_research()`
  - 增加 archetype 识别和 delivery contract 落地。
  - `_create_objectives()` 改为写入 `Objective`，不再写
    `Analysis(objective)`。
  - 改 initial query selection，避免最小覆盖直接吞掉横向 discovery。
- `evaluate_research_portfolio()`
  - 读取 `Objective` 与 `Gap`，不再以 `analysis_type` 区分
    objective/gap。
  - 去掉 `blocked_best_effort` 直接计入 readiness 的逻辑。
  - 引入 structure/slot/lead/table 等 readiness 信号。
  - utility 改为 archetype-aware。
- `expand_gaps()`
  - 改为写入和读取 `Gap`，不再写 `Analysis(gap)`。
  - 支持 coverage_hole / roster_hole / table_cell_missing 等 gap 的 query 规划。
- `assess_convergence()`
  - must objective 读取 `Objective`。
  - 拆成 evidence convergence 与 delivery readiness gate。
  - 只有 must objective satisfied，或 blocked 但被更高层 readiness gate 豁免时，才允许 stop。
- `export_report_context()`
  - 输出 section briefs、entity profiles、timeline、comparison slots、lead candidates、readiness 状态。

这是本轮改造的核心文件。

### 10.3 `src/agents/searcher.py`

建议修改：

- 保持 Searcher 不负责全局规划，但允许它在受控 contract 下执行“同一主题簇的小规模受控多检索”。
- 抽取结构中加入对 entity、timeline、table cell、profile fields 的显式抽取。
- submit 前增加“素材对象归档”步骤，而不仅是 statement/evidence/conflict。

### 10.4 `src/prompts/web_searcher.md`

建议修改：

- 从“禁止拆 query”改成“禁止脱离上游 contract 自由扩题，但允许在当前 phase 下对 roster、slot、entity 做受控子检索”。
- 增加 primary source 优先、时间边界检查、禁源约束回避。
- 对 structured report 和 WLC，分别强调“章节素材补齐”和“实体文章素材补齐”。

### 10.5 `src/prompts/reporter.md`

建议修改：

- 让 Reporter 显式消费新增素材对象，而不是只消费 query/evidence。
- 按 archetype 区分写作模式：
  - research_report
  - comparative_report
  - wikipedia_article
- 要求先消化 lead candidates、section briefs 和 entity/timeline bundles，再生成 outline。

### 10.6 `src/tools/convergence.py`

建议修改：

- 读取 `Objective`，不再从 `Analysis(objective)` 读取 must objectives。
- `structurally_converged()` 不再把 `blocked_best_effort` 当作天然通过状态。
- 增加 delivery readiness metrics 的 deterministic 部分。
- novelty 指标保留，但不再单独驱动 must objective 放行。

### 10.7 `src/tools/report_tools.py`

建议修改：

- chapter bundle 中直接支持 section_brief、entity_profile、timeline_slice、comparison_slot、lead_candidates。
- 对 final report validation 增加结构覆盖检查接口，为 Bench-II 和 WLC 提供可观察指标。

### 10.8 `src/tools/research_state.py`

建议修改：

- `get_status()` 内部改为直接读取 `Gap`、`Objective`。
- 在 `get_status()` 里暴露 archetype、delivery readiness、table completion、lead readiness 等摘要状态。
- 为后续 run.log 和 benchmark 评估提供更清晰的运行态可观测性。

### 10.9 测试文件

建议新增或扩展：

- `tests/test_tree_state_machine.py`
  - 覆盖 blocked_best_effort 不再直接放行 must objective。
- `tests/test_convergence.py`
  - 增加 archetype-specific gate。
- `tests/test_report_delivery.py`
  - 验证 chapter bundle 已包含新增素材对象。
- 新增 `tests/test_task_archetype_contract.py`
  - 验证分类和 contract shape。
- 新增 `tests/test_slot_completion.py`
  - 验证 roster/table/section slot 补齐逻辑。
- 新增 `tests/test_wlc_readiness.py`
  - 验证 article readiness gate。

## 11. 优先级与实施顺序

### P0

- 将 `Analysis(objective)`、`Analysis(gap)` 拆为 `Objective`、`Gap`。
- 重写 convergence 语义，禁止 must objective 仅凭 `blocked_best_effort` 通过。
- 引入 task archetype 和 delivery contract。
- 重写 initial query planning，使其按阶段输出 horizontal discovery query portfolio。
- 扩展 gap taxonomy，纳入 roster/table/section/lead 类缺口。

这批改动最可能首先提升：

- 收敛正确性。
- Bench-II rubric 完成度。
- 横向 coverage。

### P1

- 引入 `section_brief`、`entity_profile`、`comparison_slot`、`lead_candidate`、`readiness_checkpoint`。
- 扩展 `export_report_context()` 和 chapter bundle。
- 让 Reporter 真实消费这些中间产物。

这批改动最可能首先提升：

- WLC 写作质量。
- 成稿连贯性。
- 章节平衡与 lead 质量。

### P2

- 视验证结果决定是否把部分 `Analysis` 子类型升级为正式 NodeType。
- 在 Searcher 层增加受控多检索策略。
- 引入更细的 forbidden source / time boundary 自动检查。
- 引入更系统的 benchmark instrumentation。

这批改动更偏增强和产品化。

## 12. 建议的实施路径

建议按四步走。

### Step 1

先完成 `Objective` / `Gap` 拆分，并同步修正 contract、gap taxonomy、
convergence 的读取与写入路径。

目标是先修掉三个最危险的根因：

- `Analysis` 语义混杂
- must objective 被 `blocked_best_effort` 误放行
- 大 query 天然占优且 gap 调度不透明

### Step 2

保留 `Insight` 在 `Analysis` 中，同时新增 `Analysis` 形态的写作中间素材对象，
并改 `export_report_context()`。

目标是让 Reporter 能吃到真正可写的材料。

### Step 3

按 archetype 调整 Reporter prompt 和 chapter bundle。

目标是把 `research_report`、`comparative_matrix`、`entity_article` 三类交付拉开。

### Step 4

基于 benchmark 结果再决定是否上升 schema。

到这一阶段再决定是否继续把 `Insight` 从 `Analysis` 中拆出，以及是否要把
`section_brief`、`entity_profile`、`readiness_checkpoint` 等进一步升级为
正式节点类型。

这样风险最低，也最容易回归验证。

## 13. 验证方案

### 13.1 小规模回归测试

建议先做四类脚本级回归：

1. 一个 open research 题
2. 一个 Bench-II 强结构题
3. 一个 comparative matrix 题
4. 一个 WLC entity article 题

每类只挑 1 到 3 个样本，先观察运行态信号。

### 13.2 `run4` 类案例复测

建议用当前“具身智能技术路线与代表公司”任务做定点复测，重点观察：

- initial queries 是否从 1 条大 query 变成阶段化 portfolio。
- 是否显式生成路线 roster、公司 roster、公司画像槽位。
- `company_profiles` 在 coverage 未到线时是否仍会被错误标成 `blocked_best_effort` 通过。
- `deferred_low_value` 的 gap 是否明显减少，尤其是 taxonomy、产品进度、商业化、团队画像类 gap。

### 13.3 benchmark 抽样评估

建议对三类 benchmark 分别抽样：

- deep_research_bench：10 个短开放题
- Bench-II：10 个强结构题
- WLC：10 个 entity article

关注四组指标：

- 搜索覆盖质量
- 结构完整度
- 成稿质量
- 收敛正确性

### 13.4 观察指标建议

搜索覆盖质量：

- roster completeness
- taxonomy completeness
- primary source ratio
- time-bounded evidence ratio

结构完整度：

- section readiness score
- table cell completion ratio
- lead support score
- entity profile completion ratio

成稿质量：

- lead 是否独立成立
- 章节是否平衡
- 段落是否以主题而非来源组织
- WLC 是否更像百科文章而非资料摘要

收敛正确性：

- must objective 未达标时是否仍被 stop
- readiness blockers 是否被正确暴露
- blocked_best_effort 是否只作为限制披露，而不是直接通行证

## 14. 推荐的确认顺序

在真正实施前，建议用户先确认以下三个 shape。

1. 是否接受引入 `task_archetype + delivery_contract` 作为新的运行时 contract。
2. 是否接受第一阶段先把 `Analysis(objective)`、`Analysis(gap)` 拆为
   `Objective`、`Gap`，同时让 `Insight` 暂时留在 `Analysis`。
3. 是否接受第一阶段仍用 `Analysis` 子类型承载新中间产物，而不是继续扩大
   正式 NodeType。
4. 是否接受将 `blocked_best_effort` 从“可通过状态”降级为“限制披露状态”，并引入新的 delivery readiness gate。

如果这四点确认，后续实现可以在较小范围内分批推进，不必一次性重做整套系统。

## 15. 最终判断

这次改造最应该优先解决的，不是“把 query 变小”这件孤立的小事，而是把系统的优化目标从“图里是否已经有足够多可追溯事实”转成“是否已经形成对目标 archetype 可交付的写作素材与结构覆盖”。

只要这个目标函数不变，哪怕继续补 prompt、补 source filtering、补 conflict handling，也仍然会不断重现同一种问题：分数看似够了，成稿却还不像成稿。

相反，如果把 archetype、slot completeness、写作中间产物和 readiness gate 建起来，即使 Searcher 和 Reporter 本身不大改，系统表现也会明显更稳定，尤其是在 Bench-II 和 WLC 上。
