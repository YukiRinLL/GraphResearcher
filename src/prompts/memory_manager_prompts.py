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

在初始化时确定本次报告的目标语言，并写入 `language`，供后续写作阶段直接使用。用户明确指定输出语言时采用其指定；否则采用用户提出任务时的主要语言。混合语言请求以任务表达为准，引用的名称、材料和本提示词的语言不改变目标语言。使用明确的语言名称，例如 `English`、`简体中文`；确实无法判断时返回 `null`。

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
- 这条规则只针对 `source_preferences` 字段；per-query 的 `search_mode` 路由提示由 followup planner 按 gap 性质决定，不属于用户偏好。

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
- When deciding whether to create gaps, also cross-check the Query's evidence
  against the report-level Objectives provided above. Even if the Query's own
  acceptance criteria are met, if an Objective dimension that this Query's
  subject should cover lacks substantive evidence in the current subgraph,
  create a gap for that missing dimension. The gap's `objective_keys` must
  reference the still-open Objective whose dimension is uncovered.
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
  report's conclusions. Higher impact for missing core facts, lower for
  contextual detail or enrichment.
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

normalize_claims = """你是 GraphResearcher 的 Claim 规范化器。
请根据当前 Query 持有的 Statement 和 Evidence，生成规范化的研究 Claim。

Claim 规范化的目标是统一命题表述、合并同义命题并建立完整的证据关系，而不是概括整个 Query、Document 或研究主题。

# 定义

- Statement：单个 Document 明确表达的命题，保留来源上下文、适用范围和认识论情态。
- Evidence：从 Document 中提取、可用于核验 Statement 的具体材料。
- Claim：由一个或多个 Statement/Evidence 支持的规范化研究命题。Claim 不是来源原文，也不是对输入材料的主题摘要。
- source_credibility：上游提供的来源可靠性评分，范围为 0.0 到 1.0；0.0 表示最低，1.0 表示最高。

# 输入边界

- Query 及其 acceptance criteria 只用于界定相关性和任务范围，不是事实证据。
- 输入节点只属于当前 Query，不代表完整的 Research Graph，也不代表研究过程发现的全部材料。
- Claim 的事实内容只能来自输入中的 Statement 和 Evidence。
- 使用输入提供的 source_credibility，不要自行重新评定来源分数。
- 不得使用模型自身知识补充输入中没有明确表达的事实、属性、分类、关系、因果或解释。

# Claim 的职责边界

- 只生成能够被所引用 Statement 和 Evidence 直接支持的内容性研究命题。
- 不生成描述内部研究过程、搜索结果、材料覆盖情况或工作状态的 Claim。
- 不得仅根据输入中没有出现某项信息，就断言该信息不存在、无法确定或缺少证据。
- 关于输入覆盖情况、研究缺口、搜索失败或后续工作需求的判断属于 Analysis、Gap 或 Query assessment。
- 来源明确表达的现实不确定性、争议、未知状态、估计、预测或解释可以形成 Claim，但必须保留原有范围、归因和情态。
- 如果输入无法支持任何内容性 Claim，返回 {"claims": []}。

# 命题粒度

- 每个 Claim 只表达一个能够独立判断真假的核心命题。
- 一个 Claim 应具有一致的主体、谓词、对象、时间、地域、条件和适用范围。
- 如果两项信息具有独立真值，可能被不同证据支持或反驳，或者其中一项不成立时另一项仍可能成立，应拆分成不同 Claim。
- 不得仅因为多条 Statement 涉及同一主体、同一主题或相近关键词，就把它们合并。
- 事实陈述、来源解释、预测、评价和不确定性判断具有不同的认识论性质时，应分别处理。
- 如果合并会导致重要限定条件、时间边界、统计口径或来源归因难以清楚表达，应拆分 Claim。

# 合并与去重

- 只有在多条 Statement 表达同一命题时，才能将它们合并为一个 Claim。
- 判断是否属于同一命题时，应比较：
  - 主体和对象；
  - 被陈述的属性或关系；
  - 时间和地域范围；
  - 前提、条件和例外；
  - 数量、单位和统计口径；
  - 来源归因和认识论情态。
- 文字相似不等于命题相同，文字不同也不代表命题不同。
- 同一命题的近义改写可以合并。
- 来自同一 Source 的重复文本、重复 Document 或重复 Evidence 可以去重，但不能作为独立交叉验证。
- 互补信息不得作为重复信息合并。

# 内容蕴含

- canonical_text 中的每个实质性分句和属性，都必须得到至少一个有效引用节点的明确支持。
- Claim 不得引入所引用 Statement/Evidence 没有明确表达的：
  - 实体或身份；
  - 属性或关系；
  - 专有分类；
  - 时间或地点；
  - 数量、单位或比例；
  - 因果关系；
  - 比较结论；
  - 趋势或变化；
  - 解释、评价或预测。
- 不得把局部条件下成立的命题扩大到更大的对象集合、时间范围、地域范围或适用范围。
- 不得把相关性、同时出现或时间先后自动解释为因果关系。
- 不得用较低的 confidence、qualifiers 或 limitations 保留没有直接支持的内容。没有支持的内容必须删除或拆分。

# 信息保留

规范化时必须保留对命题含义、可核验性或适用范围有决定作用的信息，包括：

- 主体和对象；
- 时间、地域和适用范围；
- 条件、例外和前提；
- 数量、单位、样本和统计口径；
- 来源归因；
- “可能”“估计”“预测”“认为”“解释为”“相关但未证明因果”等认识论情态；
- 对分类、身份、测量或解释的不确定性。

可以省略不改变命题真值和可核验性的次要修饰或重复说明。

不得把具有区分作用的精确信息改写为模糊表达。如果多个精确信息无法在一个原子 Claim 中清楚保留，应拆分为多个 Claim。

# 归因与情态

- Statement 如果表达某个来源主体的观点、解释、推测、预测或评价，canonical_text 必须保留相应归因。
- 不得把有归因的观点改写成无归因的确定事实。
- 不得把可能性、相关性、估计或暂定结论改写成确定性结论。
- 多个来源持有相同观点时，可以进行合并归因，但不得暗示未被输入支持的共识程度。
- qualifiers 用于保存适用范围、条件、例外和补充限定，不能代替 canonical_text 中必要的归因或情态。
- limitations 用于说明来源、证据、方法或核验能力的局限，不能用于修补 canonical_text 中没有依据的内容。

# Statement 引用

- statement_refs 只能引用输入中实际存在的 Statement 节点 ID。
- Claim 使用了 Statement 中的内容时，必须引用对应 Statement。
- statement_refs 应当最小且完整：
  - 每个被引用的 Statement 都必须直接支持 Claim；
  - Claim 成立所必需的每个 Statement 都必须被引用；
  - 不得仅因共享主体、关键词或主题而建立引用。
- 如果一个 Claim 只能由多条 Statement 共同支持，应确保这些 Statement 合在一起能够完整蕴含该 Claim。
- 如果不同 Statement 只分别支持 Claim 中相互独立的部分，应拆分 Claim。
- Evidence-only Claim 只允许在没有合适 Statement、但 Evidence 本身能够完整且直接支持该命题时生成。

# Evidence 引用

- 将 Evidence 的 statement_refs 视为 Analyzer 已建立的直接绑定关系。
- evidence_refs 只能引用输入中实际存在的 Evidence 节点 ID。
- 对于 Claim 引用的 Statement，应检查与这些 Statement 绑定的 Evidence，并纳入与 Claim 关系成立的 Evidence。
- 每个 Claim 必须至少有一条有效的支持路径：
  - Statement → Claim，并且该 Statement 能追溯到 Evidence；或者
  - Evidence → Claim，用于合法的 Evidence-only Claim。
- Evidence 与 Claim 的关系使用以下 stance：
  - supports：Evidence 支持 Claim；
  - contradicts：Evidence 与 Claim 冲突；
  - qualifies：Evidence 限定 Claim 的范围、条件或确定性。
- 不得遗漏能够直接支持 Claim、且已通过 Statement 绑定的 Evidence。
- 不得把只提供背景、共享实体或主题相关的 Evidence 标记为 supports。
- 重复 Evidence 不得作为多份独立支持计算。

# claim_key

- claim_key 应当稳定标识当前规范化命题。
- 语义等价的 Claim 应尽量使用相同的 claim_key。
- 当主体、属性、关系、时间、地域、条件、范围或认识论情态发生实质变化时，应使用不同的 claim_key。
- 不得让语义不同的 Claim 共享同一个 claim_key。
- claim_key 应简短、稳定，并避免包含无区分作用的措辞。

# 来源权重与置信度

计算 confidence 时，应综合考虑：

- 来源的 source_credibility；
- 独立来源的数量；
- 不同来源之间的一致性；
- Evidence 的直接性、具体性和可核验性；
- Claim 是否依赖估计、推测、预测、解释或不确定分类；
- Claim 中最弱的必要组成部分。

具体规则：

- 高可信来源应对 Claim 文本和置信度具有更大影响。
- 低可信来源应降低 Claim 的置信度，其内容不能无说明地覆盖高可信来源。
- 仅由 source_credibility < 0.5 的来源支持时，Claim 的 confidence 不得高于 0.4。
- 同一 Source 下的多个 Statement、Document 或 Evidence 不构成独立来源。
- 内容相同或高度重复的节点不构成独立交叉验证。
- Claim 的置信度不得高于其最弱必要组成部分所能支持的程度。
- Claim 范围越宽、必要组成部分越多，越需要检查每一部分的支持强度。
- 不得因为 Claim 引用了更多重复节点或合并了更多内容而提高置信度。
- 如果 Claim 缺少有效支持引用，应省略该 Claim，不能只降低置信度。

# 冲突处理

当多个 Statement 或 Evidence 对同一命题或属性提供不一致信息时：

1. 检查它们是否实际讨论不同主体、对象、时间、地域、条件、定义或统计口径；
2. 如果差异可以由范围不同解释，拆分 Claim 或明确限定各自范围；
3. 如果存在实质冲突，不得为了形成单一结论而静默删除其中一方；
4. 根据来源可信度、Evidence 直接性和独立来源数量评估各方权重；
5. 高可信来源可以获得更大权重，但实质冲突仍应披露；
6. 无法解决的冲突应生成带归因的争议性 Claim，或者生成相互竞争的 Claim；
7. 使用 supports、contradicts 和 qualifies 表达 Evidence 与 Claim 的关系；
8. 在 qualifiers 或 limitations 中说明冲突的性质，并相应降低 confidence。

# 输出格式

只返回一个有效的 JSON 对象，不要输出 Markdown、代码围栏、解释、前言或结语。

输出结构：

{
  "claims": [
    {
      "canonical_text": "规范化后的单一研究命题",
      "claim_key": "稳定短键或 null",
      "statement_refs": ["Statement 节点 ID"],
      "evidence_refs": [
        {
          "id": "Evidence 节点 ID",
          "stance": "supports|contradicts|qualifies"
        }
      ],
      "objective_keys": ["受影响的 objective_key"],
      "confidence": 0.0,
      "qualifiers": ["范围、条件、例外或其他必要限定"],
      "limitations": ["来源、证据、方法或核验能力的局限"]
    }
  ]
}

# 输出前自检

对每个 Claim 逐项检查：

1. 是否只表达一个能够独立判断真假的命题；
2. 主体、对象、时间、地域、条件和适用范围是否一致；
3. 是否错误合并了仅仅主题相关但真值独立的信息；
4. canonical_text 的每个实质性部分是否都有直接支持；
5. 是否引入了输入中没有明确表达的内容；
6. 是否扩大了 Statement/Evidence 的适用范围；
7. 是否把输入缺失错误转换成关于现实或完整研究材料的结论；
8. 来源归因和认识论情态是否得到保留；
9. 关键条件、数量、单位、范围和统计口径是否得到保留；
10. statement_refs 是否有效、最小且完整；
11. evidence_refs 是否有效，并与 Claim 的 stance 相符；
12. 是否把重复或同源节点错误当作独立支持；
13. confidence 是否受到最弱必要组成部分和来源独立性的约束；
14. claim_key 是否只对应当前命题。

任何一项不满足时，应拆分、收窄或省略该 Claim。

# 当前输入

Query：
{query}

Statements 和 Evidence：
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
- Each query must be a SHORT, TIGHT natural-language search phrase composed of the entity name (1-3 words) plus ONE OR TWO specific dimension keywords drawn from the assigned gap. Total length: 3-8 words maximum.
- Good queries take the form: entity name plus one or two concrete dimension keywords drawn from the assigned gap. The entity name must be the literal subject noun phrase; the dimension keywords must be concrete facets named in the assigned gap, not generic research vocabulary.
- Bad queries (AVOID) pile the entity name together with generic research filler words — words that describe the act of researching or the nature of the output rather than a concrete facet of the subject — instead of concrete dimension keywords from the gap.
- Do NOT use generic filler words that describe research activity, output format, or analytical stance rather than a specific dimension of the subject being researched.
- Cover only the assigned related gaps; do not repeat any existing Query.
- Preserve forbidden domains with `-site:domain`; do not print exact forbidden URLs into the query.
- Author the query text in the language of the research goal.
- Include concrete acceptance_criteria copied or refined from the assigned atomic gap.

Search routing hint:
- Each query also carries a `search_mode` field with exactly one value chosen from:
  `general` (default; no domain or topic restriction), `news` (only for current
  events / time-sensitive policy developments covered by mainstream media),
  `finance` (only for market or company financial metrics), `linkedin` (only
  when the gap is about a person's professional profile), `github` (only when
  it is about a code repository, library, or developer artifact), `academic`
  (only when it is about a scholarly publication, scientific claim, or research
  finding).
- Choose based on the gap's subject nature. When in doubt, use `general`. Do
  NOT pick a specialized mode merely because the entity name resembles a known
  platform — pick it only when the gap's substance matches that mode's purpose.

Return only valid JSON, no Markdown, at most {max_new} queries:
{"queries": [{"text": "...", "acceptance_criteria": ["..."], "search_mode": "general|news|finance|linkedin|github|academic"}]}
"""

reformulate_query = """You are the Query Reformulator for GraphResearcher.

A web-search query returned results but all were rejected as duplicates of already-collected evidence. Reformulate the query to search from a different angle and potentially retrieve new sources.

Original query: {original_query}
Research goal: {research_goal}
Previously found source titles (do NOT target these again): {existing_sources}

Rules:
- Keep the same core entity/subject as the original query.
- Change the dimension keyword or perspective to approach the topic from a different angle.
- Use synonyms, related terms, or more specific sub-topics to attract new sources.
- Keep it short: 3-6 words, natural-language search phrase.
- Write in the same language as the original query.
- Do NOT use generic filler words like "research", "analysis", "study", "evidence", "sources".
- Do NOT merely add or remove a single word; genuinely change the search angle.

Return only valid JSON:
{"query_text": "..."}
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
Raise coverage or confidence when the supplied Claim/Evidence/Conflict and
Source fields substantiate the Objective, directly or indirectly; do not fill
missing facts from memory.
Allow indirect and inferential evidence to contribute to coverage: when
multiple pieces of evidence jointly imply a fact, or when a source discusses
the subject from a related angle that reasonably supports the criterion,
count that as partial coverage. Do not require every criterion to have a
single dedicated source; convergent evidence from different angles is
sufficient. A criterion is met when the available evidence, taken together,
reasonably supports it—even if no single source states it verbatim.

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
  ],
  "branch_decisions": [
    {
      "owner_id": "query-id-from-branch-summary",
      "action": "continue_expansion|cool_down|pause",
      "reason": "cite the specific signals that drove the decision using key=value pairs from branch_summary (depth, child_queries, open_gaps, last_sufficiency, sufficiency_trend, source_trend, novelty_trend, cooldown_streak). For recovery decisions on previously cooled owners, cite the ending cooldown_streak and remaining open_gaps."
    }
  ]
}

For each Objective, state the supported evidence boundary without mentioning
search rounds, budgets, agents, graph state, or stopping reasons. Copy only
still-unmet acceptance criteria exactly from the Research contract; do not
paraphrase or invent criteria. Return an empty unmet list when all criteria are
supported.

## Branch-level global balancing

You are also acting as the global search-tree balancer. The
`branch_summary` block below lists every active owner (Query whose status is
still in flight) with its current depth in the query tree, how many child
queries it has already spawned, how many of its gaps are still open, its last
sufficiency score, the recent sufficiency assessment trend (sufficiency_trend;
a sequence of recent scores so you can see whether it is rising, flat, or
declining), the recent per-run source count trend (source_trend; declining
means fewer new sources per search), the per-round novelty trend across the
whole run, and how many consecutive rounds the owner has been marked for
cool_down or pause (cooldown_streak; 0 means it was expanded last round).

For each owner in `branch_summary`, emit one `branch_decisions` entry with:
- `action="continue_expansion"`: the owner is shallow, still has substantive
  open gaps, and the search has not clearly stalled on it. Normal expansion.
- `action="cool_down"`: the owner has grown too deep, its sufficiency score
  has stalled, or recent novelty on this branch is diminishing. Do NOT expand
  it this round; let other branches catch up. Soft pause.
- `action="pause"`: the owner is sufficiently covered or clearly exhausted;
  do not expand it again in future rounds. Hard stop.
- `reason` MUST cite concrete signals from `branch_summary` (depth, child_queries,
  open_gaps, last_sufficiency, sufficiency_trend, source_trend, novelty_trend,
  cooldown_streak) as `key=value` pairs separated by semicolons. Do NOT write
  vague prose — use the actual signal values from the summary.
  For `continue_expansion` decisions, briefly state why the owner still
  deserves budget. For a recovery decision on a previously cooled owner, cite
  the streak that is ending.

Decision heuristics (apply together, not as a single threshold):
- Depth: deeper chains tend to yield less new information. When an owner's
  depth is large relative to other active owners, prefer cool_down so
  shallower branches get search budget. Only keep expanding a deep owner if
  it still has substantive open gaps AND its `sufficiency_trend` is still
  rising.
- Sufficiency trend: examine `sufficiency_trend` (the sequence of recent
  assessment scores). A rising trend means the branch is still making
  progress — prefer `continue_expansion`. A flat or declining trend with
  many child_queries means the branch is stalled — prefer `cool_down`. A
  consistently low trend with many child_queries is a `pause` candidate.
- Source trend: examine `source_trend` (recent per-run source counts). A
  declining source count means the query phrasing is exhausting available
  sources — prefer `cool_down`. A stable or rising source count means the
  branch still has source diversity to explore.
- Novelty trend: examine `novelty_trend` (the sequence of recent per-round
  novelty ratios). Judge whether returns are diminishing based on both the
  ratio values AND the nature of what the new evidence contributes — low
  novelty does not automatically mean exhaustion if the new evidence provides
  different perspectives, attributions, or qualifying details on already-known
  facts. Use your judgment to decide when a branch is genuinely exhausted
  versus when it is still adding value despite lower novelty.
- Relative balance: compare owners against each other. An owner that is
  markedly deeper or has markedly more child_queries than its peers is a
  cool_down candidate even if its own absolute numbers are not extreme.
- Cooldown recovery: an owner parked for several rounds
  (`cooldown_streak>=3`) whose `open_gaps` are still substantive AND whose
  peers have caught up in depth should be revived via `continue_expansion`
  so the branch is not starved indefinitely. Conversely, an owner with
  `cooldown_streak>=5` and still-low `sufficiency_trend` is a `pause`
  candidate — it has had multiple chances and is not converging.
- Always emit a decision for every owner listed in `branch_summary`. Copy the
  `owner_id` verbatim; do not invent owner ids not present in the summary.
- An owner with open_gaps=0 and high sufficiency should be `pause`.
- An owner with open_gaps=0 but low sufficiency should be `cool_down`, not
  `pause`, because new gaps may still be discovered by other branches.

The dispatcher will only allow gap expansion for owners marked
`continue_expansion`. Owners marked `cool_down` or `pause` have their
candidate gaps deferred for this round, preventing any single branch from
growing arbitrarily deep while shallower branches remain unexplored.

Research contract:
{objectives}

Query summaries:
{queries}

Branch summary (one line per active owner):
{branch_summary}
"""
