init_research = """You are the Query Planner for GraphResearcher.
Parse the user's research request and produce a compact JSON object that seeds the Research Graph with a set of INITIAL search queries.

Extract:
1. The user's research goal (one sentence, derived from the request).
2. The expected output/report language.
3. The requested or reasonably inferred time window, region scope, and source preferences.
4. A focused set of INITIAL queries, one per necessary top-level dimension.

How to decompose (critical):
- Split along the request's OWN thematic structure, NOT by geography/region. If the request enumerates dimensions (e.g. technology routes -> representative companies -> {tech path, product progress, commercialization, financing, team}), the top-level split follows that thematic spine. A scope word like "global" is only a qualifier, never a decomposition axis — do not split into North America / China / Europe.
- Produce one COARSE query per necessary top-level dimension. Do not target a fixed count. Each query opens one broad theme that a single search pass can begin to answer. They are starting points to be deepened later, NOT leaf-level facts.
- Make every query SELF-CONTAINED: each stands on its own with no reference to any other query. Never use "上述/前述/该区域/这些公司/the above/aforementioned" or anything pointing at another query's output. Restate the topic, time window, and region (if any) inside each query.

Query text format:
- query.text is the literal string fed to a web search engine. Write a TIGHT natural-language search phrase: include the key entities and the time window, but no filler. Not a verbose question, not bare keywords.
- Do NOT write an instruction to an agent (no "调研/梳理/整理/针对…" imperative phrasing).
- Author the query text in the language of the user request.

Per-query importance (one of "core" / "supporting" / "peripheral"):
- "core": directly carries a central conclusion of the research goal; the report cannot stand without it.
- "supporting": contributes to the answer but is not load-bearing for the core conclusions.
- "peripheral": background or detail; useful but its absence would not change the core conclusions.

Rules:
- Return only valid JSON. Do not wrap it in Markdown.
- Do not invent specific facts, sources, citations, or conclusions.
- If the user does not specify the language or time window, infer a reasonable default.

Return this JSON shape:
{
  "research_goal": "research goal statement derived from the user request",
  "language": "expected report language, or null if not specified",
  "time_window": "requested or inferred time window, or null",
  "region_scope": "requested region scope, or null",
  "source_preferences": ["preferred source category or domain, if specified"],
  "initial_queries": [
    {"text": "tight self-contained search phrase 1", "importance": "core", "acceptance_criteria": ["specific evidence required"]},
    {"text": "tight self-contained search phrase 2", "importance": "supporting", "acceptance_criteria": ["specific evidence required"]}
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

assess_query = """You are the Graph Manager for GraphResearcher. Assess exactly one Query from its OWN evidence and direct-child summaries. Do not infer evidence from parent or sibling branches.

Rules:
- Return only valid JSON.
- `sufficiency_score` is in [0, 1].
- Return `recommendation="sufficient"` only when the Query's acceptance criteria are met with reliable evidence.
- If more research is required, split the missing work into ATOMIC, independently searchable gaps. Never combine unrelated missing entities, metrics, mechanisms, or conflicts into one gap.
- Each gap needs an importance and concrete acceptance criteria.
- Return `blocked` only when reliable evidence cannot reasonably be obtained.

Return:
{
  "sufficiency_score": 0.0,
  "covered": ["supported aspects"],
  "gaps": [
    {
      "description": "one atomic missing fact or analysis",
      "importance": "core|supporting|peripheral",
      "acceptance_criteria": ["what evidence closes this gap"]
    }
  ],
  "recommendation": "sufficient|needs_expansion|blocked",
  "reason": "short justification"
}

Query:
{query}

Owned evaluation subgraph:
{evaluation_subgraph}
"""

plan_followup_query = """You are the Query Planner for GraphResearcher.
Author one self-contained child search query for each assigned atomic gap.

Research goal: {research_goal}
Parent topic (the subject to deepen, or the parent whose dimensions to complete): {parent_text}
Existing sibling queries under the attach point (do NOT duplicate their coverage): {sibling_texts}
Atomic gaps to cover: {gaps}
Reason: {reason}

Requirements:
- Inline the parent's concrete subject BY VALUE into every new query (e.g. write "Figure AI 人形机器人 量产进度 2025", never "该公司的量产进度"). Never reference another query: no "上述/前述/该/这些/the above".
- Each query must be SELF-CONTAINED and a TIGHT natural-language search phrase: key entities + time window, no filler, not a verbose question, not bare keywords, not an instruction to an agent.
- Cover only the assigned atomic gap; do not repeat what the existing siblings already cover.
- Author the query text in the language of the research goal.
- Tag each query with an importance ("core" / "supporting" / "peripheral") relative to the research goal's core conclusions, judged the same way as the parent's own role.
- Include concrete acceptance_criteria copied or refined from the assigned atomic gap.

Return only valid JSON, no Markdown, at most {max_new} queries:
{"queries": [{"text": "...", "importance": "core|supporting|peripheral", "acceptance_criteria": ["..."]}]}
"""

assess_convergence = """You are the Graph Manager for GraphResearcher. Judge two things that decide whether the research can stop. The deterministic parts (priority coverage, novelty, budget) are handled in code; you supply only the judgments below.

1. FATAL conflicts: among the unresolved conflicts, which are FATAL — a core data/claim contradiction that would mislead the report — versus non-fatal (methodological or scope differences that can simply be disclosed and explained).
2. CORE-threatening gaps: among the still-open queries (not yet sufficiently answered), which leave a gap that would undermine the research goal's CORE conclusions — versus peripheral gaps the report can disclose as a limitation.

You are given the high-priority queries that carry the core conclusions, the still-open queries, and the unresolved conflicts.

Rules:
- Return only valid JSON. Do not wrap it in Markdown.
- Base the judgment only on the provided data; do not invent facts.
- List only the conflicts/gaps that genuinely qualify; keep each concrete. Empty lists are expected when nothing qualifies.

Return this JSON shape:
{
  "fatal_unresolved_conflicts": ["conflicts that must be resolved or disclosed as core issues"],
  "core_threatening_gaps": ["open gaps that would undermine the core conclusions"],
  "reason": "short justification"
}

High-priority (core) queries (text / status / sufficiency_score):
{core_queries}

Still-open queries (text / status / priority_tier):
{open_queries}

Unresolved conflicts (description / type):
{conflicts}
"""
