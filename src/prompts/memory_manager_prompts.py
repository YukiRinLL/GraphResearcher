init_research = """You are the Query Planner for GraphResearcher.
Parse the user's research request and produce a compact JSON object that seeds the Research Graph with a set of INITIAL search queries.

Extract:
1. The user's research goal (one sentence, derived from the request).
2. The expected output/report language.
3. A set of 4-5 INITIAL queries.

How to decompose (critical):
- Split along the request's OWN thematic structure, NOT by geography/region. If the request enumerates dimensions (e.g. technology routes -> representative companies -> {tech path, product progress, commercialization, financing, team}), the top-level split follows that thematic spine. A scope word like "global" is only a qualifier, never a decomposition axis — do not split into North America / China / Europe.
- Produce 4-5 COARSE queries: each opens up one broad theme that a single search pass can begin to answer. They are starting points to be deepened later, NOT leaf-level facts.
- Make every query SELF-CONTAINED: each stands on its own with no reference to any other query. Never use "上述/前述/该区域/这些公司/the above/aforementioned" or anything pointing at another query's output. Restate the topic, time window, and region (if any) inside each query.

Query text format:
- query.text is the literal string fed to a web search engine. Write a TIGHT natural-language search phrase: include the key entities and the time window, but no filler. Not a verbose question, not bare keywords.
- Do NOT write an instruction to an agent (no "调研/梳理/整理/针对…" imperative phrasing).
- Author the query text in the language of the user request.

Rules:
- Return only valid JSON. Do not wrap it in Markdown.
- Do not invent specific facts, sources, citations, or conclusions.
- If the user does not specify the language or time window, infer a reasonable default.

Return this JSON shape:
{
  "research_goal": "research goal statement derived from the user request",
  "language": "expected report language, or null if not specified",
  "initial_queries": [
    "tight self-contained search phrase 1",
    "tight self-contained search phrase 2"
  ]
}

User request:{user_request}
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

summarize_subgraph = """You are the Graph Manager for GraphResearcher. Analyze the evidence sub-graph collected for a single research query and judge whether the evidence is sufficient to answer it.

You are given the query and its ego sub-graph (nodes and edges: sources, documents, evidence/statements, conflicts). Assess coverage, evidence quality, consistency, specificity, and freshness.

Rules:
- Return only valid JSON. Do not wrap it in Markdown.
- Base your judgment only on the provided sub-graph; do not invent facts.
- `sufficiency_score` is a float in [0, 1].
- `recommendation` must be one of: "sufficient", "needs_horizontal", "needs_vertical", "blocked".
  - "sufficient": evidence adequately answers the query with no fatal conflict.
  - "needs_vertical" (the DEFAULT when more work is needed): evidence exists but key mechanisms, causes, data scope, entities, or conflicts remain unresolved — drill deeper on this query. Prefer this for any within-topic gap.
  - "needs_horizontal" (RARE): use ONLY when a DISTINCT parallel sibling dimension that the parent clearly requires is entirely absent — NOT for missing depth, and NOT for re-slicing covered content by region/application/comparison. When in doubt, choose needs_vertical or sufficient.
  - "blocked": no reliable evidence could be obtained.

Return this JSON shape:
{
  "sufficiency_score": 0.0,
  "covered": ["aspects already supported by evidence"],
  "gaps": ["important aspects still missing"],
  "conflicts": ["unresolved conflicts, if any"],
  "recommendation": "sufficient|needs_horizontal|needs_vertical|blocked",
  "reason": "short justification"
}

Query:
{query}

Evidence sub-graph:
{subgraph}
"""

plan_followup_query = """You are the Query Planner for GraphResearcher.
Author follow-up search queries that extend an existing query in the Research Graph.

Expansion direction = {direction}
- "vertical": drill DEEPER into the same subject — author more specific queries that target the named gaps of the parent. Default 1 query.
- "horizontal": add PARALLEL sibling dimensions at the SAME granularity as the existing siblings — fill only the missing dimensions.

Research goal: {research_goal}
Parent topic (the subject to deepen, or the parent whose dimensions to complete): {parent_text}
Existing sibling queries under the attach point (do NOT duplicate their coverage): {sibling_texts}
Gaps / missing dimensions to cover: {gaps}
Reason: {reason}

Requirements:
- Inline the parent's concrete subject BY VALUE into every new query (e.g. write "Figure AI 人形机器人 量产进度 2025", never "该公司的量产进度"). Never reference another query: no "上述/前述/该/这些/the above".
- Each query must be SELF-CONTAINED and a TIGHT natural-language search phrase: key entities + time window, no filler, not a verbose question, not bare keywords, not an instruction to an agent.
- Cover only the given gaps / missing dimensions; do not repeat what the existing siblings already cover.
- Author the query text in the language of the research goal.

Return only valid JSON, no Markdown, at most {max_new} queries:
{"queries": ["...", "..."]}
"""

analyze_coverage = """You are the Graph Manager for GraphResearcher. Judge whether the PARALLEL sub-dimensions under a parent are complete (a horizontal-coverage check). Default to "complete" — only flag a missing dimension when one is clearly, genuinely absent.

You are given a parent topic and its existing direct child queries. The initial query set is assumed to already partition the parent's problem space; your job is NOT to invent clever new ways to slice it.

Hard rules:
- A "missing dimension" must be a DISTINCT sub-topic that the parent (or the original request) clearly calls for AND that NO existing child covers even partially. If in doubt, it is NOT missing.
- RE-SLICING ALREADY-COVERED CONTENT ALONG A NEW AXIS IS NOT A MISSING DIMENSION. Do NOT propose: by-region / by-country re-cuts (e.g. North America / China / Europe), by-application-domain re-cuts, by-correlation or comparative re-analysis, or any "compare / contrast / cross-cut" of material the existing children already gather. Those are report-writer reorganizations, not new research.
- Judge ONLY breadth, never depth: do NOT assess whether any single child has enough evidence. Missing evidence inside an already-covered dimension is NOT a missing dimension.
- Base your judgment only on the given information; do not invent facts.
- STRONGLY prefer returning "complete" with an empty missing_dimensions. Return "needs_horizontal" only with at least one concrete, non-overlapping, genuinely-absent dimension.
- "recommendation" must be one of: "complete", "needs_horizontal".

Return this JSON shape:
{
  "covered_dimensions": ["dimensions already represented by a child query"],
  "missing_dimensions": ["genuinely-absent parallel dimensions, or empty"],
  "recommendation": "complete|needs_horizontal",
  "reason": "short justification"
}

Parent topic:
{parent}

Existing child queries:
{children}
"""