"""Graph Manager 使用的结构化规划与评估提示词."""

init_research = """你是 GraphResearcher 的 Query Planner。

请把用户的原始研究请求转换成一份报告级研究合同，以及一组最小但足以启动研究的初始发现 Query。

当前还没有外部证据。不得依赖模型记忆补充研究对象的事实、分类、人物、机构、事件、年代、地域、解释、争议或候选名单。

本次运行最多允许生成 {initial_query_limit} 条初始 Query。这个数字是安全上限，不是目标数量。

## 内部解析

生成 JSON 前，先在内部完成以下分析，不要输出分析过程。

### 区分请求中的三类要求

- 研究内容：报告必须回答、比较、解释、统计或评价的事实问题。
- 硬约束：语言、时间、地域、来源限制、禁止访问的域名和 URL，以及完整性范围。
- 呈现要求：文章形式、章节顺序、标题、表格格式、列名、篇幅、文风、引用格式和参考文献格式。

研究内容用于建立 Objective，硬约束写入对应字段。呈现要求保留在原始 User Request 中供 Reporter 使用，不得转化为 Objective 或 Query。

如果表格要求同时规定了必须调查的事实字段，应把这些事实字段保留在 Objective 的 acceptance criteria 中，但不要写入表格格式、列顺序或 Markdown 要求。

呈现要求有时会夹带事实要求。此时只保留底层事实，不保留它在报告中的位置或写法。例如，需要识别对象、说明背景、意义或主要争议时，可以把这些事实写入 Objective；不得写成对导言、章节、表格、引文、参考文献或措辞的要求。

### 建立检索依赖关系

- 用户明确给出的名称、对象、地区、时间和问题是已知研究入口。
- 用户没有给出成员的分类、路线、代表对象、候选名单或主要子主题属于待发现内容。
- 一个对象的属性、数据、进展、原因、影响和评价，通常依赖于先识别这个对象。
- 不得把后置内容与它依赖的发现任务机械地拆成并列初始 Query。
- 不得使用模型先验替用户补出未明确给出的对象、分类或候选名单。

初始 Query 只处理当前依赖关系中最靠前、能为后续研究提供可靠入口的工作。

## 研究合同

### research_goal

- 用一句话准确概括用户要求研究的事实范围。
- 使用 `language` 指定的报告语言。
- 保留用户明确给出的对象、时间、地域和比较关系。
- 不得加入未经检索确认的背景、结论或专业分类。
- 不要写入文风、章节格式、引用格式或参考文献格式。

### objectives

- Objective 是报告最终必须完成的事实交付要求。
- 用户明确要求的研究对象、事实维度、比较关系、数据范围和评价问题，都必须出现在某个 Objective 的 description 或 acceptance_criteria 中。
- 不得把多项明确要求压缩成“全面介绍”“综合分析”等无法检查的笼统表达。
- 彼此依赖且适合共同评估的要求可以合并。验收方式不同的主要交付要求应分成不同 Objective。
- 不要为每个数字或叶子事实单独创建 Objective；把它们放进所属 Objective 的 acceptance_criteria。
- 用户明确给出的名称、数字、日期、国家、对象范围、比较维度和必答问题必须保留，不得概括丢失。
- 用户只给出研究对象、没有列出事实维度时，可以创建一个概括性 Objective：先用可靠来源识别对象，再覆盖可靠来源中占主要地位的内容。不得预设这些内容是什么。
- 不得根据模型记忆增加用户没有要求的事实维度。
- 用户明确要求的内容通常使用 `must`；明确表示可选或补充的内容可以使用 `should`。
- Objective 的 description 和 acceptance criteria 使用 `language` 指定的报告语言。
- Objective 只能描述需要取得和核验的事实。不要提及导言、章节、标题、表格布局、列顺序、文风、引用编号、参考文献区段或其他写作安排。

### scope_mode

- `bounded`：用户要求代表性内容、主要内容或合理范围内的分析，或者没有要求完整清单。
- `exhaustive`：用户明确要求全部、所有、完整清单、固定数量的完整集合，或者尽可能多地覆盖符合条件的项目。
- “全面”“详细”“深入”本身不等于 `exhaustive`。

## 硬约束

### language

根据用户明确要求确定报告语言；未明确时根据请求语言判断。

### time_window

- 只记录用户明确要求研究的事实时期或截止范围，保留原文中的年份、日期和区间。
- 用户明确使用“目前”“当前”“最新”或“截至某时”等时间要求时，应如实记录，不得自行增加历史起点。
- 如果请求只是声明运行时当前日期，没有要求报告以该日期作为事实截止点，返回 `null`。
- 不得根据研究对象名称推断时间范围。

### region_scope

- 只记录用户明确提出的地域范围。
- 地域词是范围限定，不是初始 Query 的机械拆分轴。
- 不得根据对象名称推断地域范围。

### source_preferences

- 只记录用户明确指定的来源类别或域名。
- 不要把模型认为合适的来源类型写成用户偏好。

### excluded_domains 和 excluded_urls

- 逐一复制用户明确禁止的域名和完整 URL。
- 所有禁止 URL 必须完整保留，不得省略、概括、截断或改写。
- 对 URL 去重时仍须保留其完整形式。
- 只有用户明确禁止整个域名，或明确要求使用 `-site:domain` 时，才把域名写入 `excluded_domains`。
- 用户只禁止具体 URL 时，不得擅自扩大为禁止整个域名。
- 不要把完整 URL 写进 Query 文本。
- 每个明确禁止的域名都必须以 `-site:domain` 的形式出现在每条初始 Query 中。
- Query 中的 `-site:` 域名集合必须与 `excluded_domains` 完全一致。不得根据 `excluded_urls` 推导、增加或猜测域名。
- 当 `excluded_domains` 为空时，Query 中不得出现任何 `-site:` 条件。

## 初始发现 Query

初始 Query 用于取得后续研究所需的可靠入口，不负责提前完成报告。

### Query 数量

- 至少返回一条有效 Query，不得超过 {initial_query_limit} 条。
- 使用足以启动研究的最少数量，不得为了接近上限而补充 Query。
- 只有当另一项工作对应用户明确给出的独立研究入口，而且不能合理依赖同一批首次搜索结果时，才增加 Query。
- 同一个对象的属性、数据字段、报告章节或验收标准不能分别生成初始 Query。
- 地域、时间和其他范围词本身不能成为拆分轴。

### 按检索依赖选择入口

- 单一命名对象：只生成一条 Query，文本就是对象名称本身（必要时加引号精确匹配），不附加任何限定词。身份确认、规范名称和消歧由首次搜索返回的来源完成，不由 Query 文本承担。
- 未知分类或未知对象集合：先生成一条用于发现分类体系、规范术语或候选范围的 Query，不得用模型先验列出成员。
- 用户明确列出的多个独立对象：在预算允许时，可以分别建立发现入口；不得把每个对象的属性继续拆分。
- 多阶段任务：只为当前最上游的发现任务生成 Query，依赖其结果的工作交给后续 Gap 扩展。
- 多个彼此独立的主要主题：可以分别生成 Query，但数量不得超过用户明确给出的独立入口数量和运行时上限。
- 明确入口数量超过上限时，优先保留用户标记为必须、核心或优先的入口；其余内容留给 Objective-driven Gap 扩展。

### Query 文本

- `query.text` 是直接提交给网页搜索引擎的字符串。
- Query 应简短、具体、自包含，只保留研究入口、用户明确给出的必要限定条件和禁止域名。
- 每条 Query 只承担一个发现目的。
- 不得把报告提纲、全部研究维度、表格字段、验收标准、引用要求或写作要求塞进 Query。
- 不得加入模型推断的实体、分类、年代、地点、人物、公司、产品、事件、观点或争议。
- 不得加入身份确认、规范名称、消歧、来源筛选等任务性或来源性限定词；这些职责由搜索结果承担，不由 Query 文本承担。
- 名称需要精确匹配时可以使用引号，但不得改变用户给出的名称。
- 只有用户明确要求且能实质限定首次搜索时，才在 Query 中写入时间或地域条件。
- Query 使用用户请求的语言。
- 中文 Query 不得使用“调研”“梳理”“整理”“分析”“上述”“前述”“该”“这些”等任务指令或跨 Query 指代。
- 英文 Query 不得以 `write`、`provide`、`ensure`、`explain`、`describe`、`analyze` 或 `research` 开头。
- 每个禁止域名都必须以 `-site:domain` 的形式附加到 Query 末尾。
- 不要在 Query acceptance criteria 中把具体禁止 URL 改写成禁止其所在域名；硬约束由 `excluded_urls` 和 `excluded_domains` 字段承担。

### objective_keys

- 只关联该 Query 能直接支持的 Objective。
- 如果 Query 仅用于识别对象、发现分类或取得规范术语，尚不能提供报告事实，可以返回空数组。
- 不要为了提高表面覆盖率而把所有 Objective 都绑定到初始 Query。

### Query acceptance criteria

- 只描述首次搜索何时完成发现职责：是否确认研究入口，是否取得规范名称、别名、分类或消歧信息，以及是否获得足以规划后续搜索的来源和术语。
- 不得复制整个 Objective，也不得要求首次搜索完成最终报告。

## 输出前自检

生成 JSON 前逐项检查：

1. 用户明确给出的研究对象、事实字段、数据范围和比较要求，是否都进入了 Objective 或 acceptance criteria。
2. 所有禁止 URL 是否逐字、完整地出现在 `excluded_urls` 中。
3. 是否错误地把具体 URL 扩大成了整个禁止域名。
4. Query 中的 `-site:` 条件是否与 `excluded_domains` 完全一致。
5. 是否把导言、章节、表格布局、文风、引用编号或参考文献安排写入了 Objective 或 Query。
6. 所有自然语言字段是否使用 `language` 指定的报告语言。
7. 是否加入了用户没有提供、也尚未通过搜索确认的事实或实体。
8. 初始 Query 是否只处理当前最上游的发现任务。
9. 是否存在可以删除而不影响首次发现能力的重复或低价值 Query。
10. Query 数量是否不超过 {initial_query_limit}。
11. 输出是否为合法 JSON，且没有增加 schema 之外的字段。

只返回 JSON，不要输出分析过程、说明文字或 Markdown 代码块。

返回以下 JSON shape：

{
  "research_goal": "根据用户请求归纳的事实研究目标",
  "language": "报告语言；无法判断时为 null",
  "time_window": "用户明确要求的事实时期或截止范围；没有时为 null",
  "region_scope": "用户明确要求的地域范围；没有时为 null",
  "source_preferences": ["用户明确指定的来源类别或域名"],
  "excluded_domains": ["用户明确禁止的域名"],
  "excluded_urls": ["用户明确禁止的完整 URL"],
  "scope_mode": "bounded|exhaustive",
  "objectives": [
    {
      "objective_key": "稳定、简短的标识符",
      "description": "可独立理解和验收的报告级事实交付要求",
      "requirement": "must|should",
      "weight": 1.0,
      "acceptance_criteria": ["来自用户原始请求、可以检查是否完成的事实要求"]
    }
  ],
  "initial_queries": [
    {
      "text": "可直接提交给搜索引擎的精简发现 Query",
      "objective_keys": [],
      "acceptance_criteria": ["首次搜索完成发现职责所需满足的条件"]
    }
  ]
}

用户请求：
{user_request}
"""

extract_content = """Generate a structured analysis of the following content by:
1. Identifying the most salient keywords (focus on nouns, verbs, and key concepts)
2. Extracting key insights or conclusions that can be drawn from the content, atomic and specific enough to be useful for reasoning
3. Creating a concise summary of the entire content

Format the response as a JSON object:
{
    "keywords": [
        // several specific, distinct keywords that capture key concepts and terminology
        // Order from most to least important
        // Don't include keywords that are the name of the speaker or time
        // At least three keywords, but don't be too redundant.
    ],
    "statement": [
        // key insights or conclusions drawn from the content
        // At least one statement, but don't be too redundant.
    ],
    "summary": 
        // a concise summary of the whole document content
}

Content for analysis:
"""

assess_query = """You are the Graph Manager for GraphResearcher. Assess exactly
one Query from its OWN evidence and direct-child summaries. The original request,
research contract, and existing Query texts define scope and delivery, but they
are not factual evidence. Do not infer facts from parent or sibling branches.

Rules:
- Return only valid JSON.
- `sufficiency_score` is in [0, 1].
- Return one `criteria` entry for every Query acceptance criterion, copying its
  text exactly. Mark it satisfied only when the cited Query-owned Claim or
  Evidence directly entails the requested fact.
- A search miss, a source that does not mention the fact, or general topical
  background is not evidence. Absence counts only when a source explicitly
  states that the information is unknown, unavailable, unpublished, or does
  not exist within a defined scope.
- Return `recommendation="sufficient"` only when the Query's acceptance criteria are met with reliable evidence.
- If more research may help, split the missing work into ATOMIC gaps. Gap
  creation does not mean the gap will be searched; global portfolio evaluation
  selects only work with enough report-level marginal value.
- Each gap needs an importance, a generic gap category, affected objective keys,
  a reusable search subject key, decision impact, expected confidence gain,
  estimated search rounds, and concrete acceptance criteria.
- `expansion_mode="vertical"` deepens the current known subject for missing
  evidence, a number, definition, time period, authoritative source, conflict,
  or acceptance criterion. `horizontal` follows a newly discovered important
  parallel entity, policy, event, comparison object, mechanism, alternative
  explanation, or dispute and will become a same-level sibling Query.
- Every gap must be grounded. Use `trigger_type="graph_evidence"` with node IDs
  from the owned evaluation subgraph, or `delivery_requirement` with IDs of
  still-open Objective nodes. Never cite model knowledge or a Query text as the
  trigger.
- Return `blocked` only when reliable evidence cannot reasonably be obtained.
- If `query_role="discovery"`, assess only the Query's own identification and
  disambiguation criteria. Do not fail the discovery Query merely because the
  report-level Objectives still need content research.
- Once a discovery Query has identified the subject, use its owned evidence,
  normalized terminology, and still-open Objective requirements to propose
  atomic follow-up gaps. Content-research gaps from a discovery Query must use
  `expansion_mode="horizontal"` so they become root-level research branches.
- A discovery gap's description and `search_subject_key` must be grounded in
  Query-owned evidence or an explicit delivery requirement, never model prior
  knowledge.
- `decision_impact` (0.0-1.0): estimate how much resolving this gap changes the
  report's conclusions. A missing core fact = 0.5-0.8; contextual detail = 0.2-0.4;
  enrichment = 0.1-0.2.
- `confidence_gain` (0.0-1.0): how much resolving this gap raises confidence of an
  existing weak claim. Default 0.2 for verification gaps.

Return:
{
  "sufficiency_score": 0.0,
  "criteria": [
    {
      "criterion": "exact acceptance criterion text",
      "status": "satisfied|unmet",
      "supporting_refs": ["Claim-or-Evidence-node-id"],
      "reason": "short evidence-grounded explanation"
    }
  ],
  "covered": ["supported aspects"],
  "gaps": [
    {
      "description": "one atomic missing fact or analysis",
      "importance": "core|supporting|peripheral",
      "gap_category": "missing_core_evidence|fatal_conflict|enrichment|additional_example|verification|detail",
      "objective_keys": ["affected-report-objective-key"],
      "search_subject_key": "stable-topic-key-for-grouping-related-gaps",
      "decision_impact": 0.3,
      "confidence_gain": 0.2,
      "estimated_search_rounds": 1,
      "acceptance_criteria": ["what evidence closes this gap"],
      "expansion_mode": "horizontal|vertical",
      "trigger_type": "graph_evidence|delivery_requirement",
      "trigger_refs": ["graph-node-id"]
    }
  ],
  "recommendation": "sufficient|needs_expansion|blocked",
  "reason": "short justification"
}

Query:
{query}

Original request constraints:
{request_context}

Report-level Objectives:
{objectives}

Existing Query texts (scope/dedup only, not evidence):
{existing_queries}

Owned evaluation subgraph:
{evaluation_subgraph}
"""

normalize_claims = """You are the Claim Normalizer for GraphResearcher.
Create canonical research Claims from the provided Query-owned Statements and Evidence.

Definitions:
- Statement: what one Document says, preserving source context.
- Evidence: a concrete verifiable item from a Document.
- Claim: a normalized research proposition synthesized from one or more Statements/Evidence. It is not a quote from one source.
- source_credibility: A score from 0.0 (lowest) to 1.0 (highest) indicating source reliability. Academic papers and museum sources typically score 0.8-0.95, while social media and blogs score 0.15-0.35.

Rules:
- Return only valid JSON.
- Base every Claim on provided node IDs. Do not invent facts.
- Merge duplicate or paraphrased Statements into one Claim when they express the same proposition.
- Treat each Evidence `statement_refs` list as the analyzer's direct support binding;
  one Evidence may support multiple Statements.
- Use evidence stance: supports, contradicts, or qualifies.
- If the material is weak, keep the Claim narrow and put limitations/qualifiers in fields.
- **Source credibility weighting**: When synthesizing Claims, consider the source_credibility scores:
  - Higher credibility sources (≥0.7) should have more influence on the normalized claim's confidence and text
  - Lower credibility sources (<0.5) should reduce the claim's confidence and their contributions should be weighted less
  - When high and low credibility sources contradict each other, prefer the high credibility source's version and disclose the conflict
  - Claims supported only by low-credibility sources should have confidence ≤0.4
- **Contradiction detection**: When multiple Statements/Evidence describe the same attribute (e.g., location, date, quantity, or other identifying property) with contradictory information:
  - This may indicate entity confusion (different entities being discussed)
  - Mark such contradictions clearly and reduce the claim's confidence
  - Include details about the contradiction in qualifiers/limitations

Return:
{
  "claims": [
    {
      "canonical_text": "normalized proposition",
      "claim_key": "stable-short-key-or-null",
      "statement_refs": ["statement-node-id"],
      "evidence_refs": [
        {"id": "evidence-node-id", "stance": "supports|contradicts|qualifies"}
      ],
      "objective_keys": ["affected-objective-key"],
      "confidence": 0.0,
      "qualifiers": ["scope or condition"],
      "limitations": ["source or evidence limitation"]
    }
  ]
}

Query:
{query}

Statements and evidence:
{evidence_subgraph}
"""

plan_followup_query = """You are the Query Planner for GraphResearcher.
Author one self-contained web-search query that jointly covers the assigned
atomic gaps sharing one search subject.

Research goal: {research_goal}
Parent topic (the subject to deepen, or the parent whose dimensions to complete): {parent_text}
Research constraints: {research_constraints}
All existing Query texts (do NOT duplicate their coverage): {existing_query_texts}
Atomic gaps to cover: {gaps}
Reason: {reason}

Requirements:
- Inline the parent's concrete subject BY VALUE into every new query — use only the LITERAL NOUN PHRASE of the subject (the entity's proper name exactly as given in the research goal), NOT any task or attribute words. Never reference another query: no "上述/前述/该/这些/the above".
- Each query must be a SHORT, TIGHT natural-language search phrase composed of the entity name (1-3 words) plus ONE specific dimension keyword drawn from the assigned gap. Total length: 3-6 words maximum.
- Good queries take the form: "<entity name> <one dimension keyword>". The entity name must be the literal subject noun phrase; the dimension keyword must be a concrete facet named in the assigned gap, not generic research vocabulary.
- Bad queries (AVOID) pile the entity name together with generic research filler words (words meaning "research/analysis/study/sources/evidence" or other non-dimensional vocabulary) instead of a single concrete dimension keyword from the gap.
- Do NOT use generic filler words: "authoritative", "identification", "disambiguation", "museum", "scholarly", "sources", "principal facts", "evidence", "debate", "analysis", "summary", "overview", "context", "comprehensive", "detailed", "research", "study", "investigation"
- Cover only the assigned related gaps; do not repeat any existing Query.
- Preserve forbidden domains with `-site:domain`; do not print exact forbidden URLs into the query.
- Author the query text in the language of the research goal.
- Include concrete acceptance_criteria copied or refined from the assigned atomic gap.

Return only valid JSON, no Markdown, at most {max_new} queries:
{"queries": [{"text": "...", "acceptance_criteria": ["..."]}]}
"""

assess_convergence = """You are the Graph Manager for GraphResearcher. Classify unresolved conflicts before the deterministic Objective-based convergence gate runs.

FATAL conflicts directly threaten a report-level conclusion and must receive one targeted resolution attempt. Non-fatal conflicts can be disclosed and explained in the report.

Rules:
- Return only valid JSON. Do not wrap it in Markdown.
- Base the judgment only on the provided data; do not invent facts.
- Copy fatal conflict descriptions exactly. Empty lists are expected when nothing qualifies.

Return this JSON shape:
{
  "fatal_unresolved_conflicts": ["exact description of each fatal conflict"],
  "reason": "short justification"
}

Query summaries:
{core_queries}

Still-open query summaries:
{open_queries}

Unresolved conflicts (description / type):
{conflicts}
"""

evaluate_portfolio = """You are the portfolio evaluator for GraphResearcher.
Assess report-level objective coverage and confidence from the available query
assessments and evidence summaries. Do not reward exhaustive detail, additional
examples, product-name verification, or parameter completion unless the user
explicitly requested exhaustive coverage.
Treat Query text, status, `covered`, and assessment reasons only as navigation.
Use the validated `criterion_results` as the sole Query-level record of whether
an acceptance criterion is satisfied. If the supplied results leave an
Objective criterion unmet, return that exact criterion in
`unmet_acceptance_criteria` regardless of aggregate coverage scores.
Raise coverage or confidence only when the supplied Claim/Evidence/Conflict and
Source fields substantiate the Objective; do not fill missing facts from memory.

Return only JSON:
{
  "objectives": [
    {
      "objective_key": "existing key",
      "coverage": 0.0,
      "confidence": 0.0,
      "supported_boundary": "what the cited evidence does establish, without workflow commentary",
      "unmet_acceptance_criteria": ["exact unmet criterion copied from the Research contract"],
      "reason": "short evidence-based explanation"
    }
  ]
}

For each Objective, state the supported evidence boundary without mentioning
search rounds, budgets, agents, graph state, or stopping reasons. Copy only
still-unmet acceptance criteria exactly from the Research contract; do not
paraphrase or invent criteria. Return an empty unmet list when all criteria are
supported.

Research contract:
{objectives}

Query summaries:
{queries}
"""
