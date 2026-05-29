"""LLM prompt strings used by MemoryManager and related agents."""

init_research = """You are the Memory Manager for GraphResearcher.
Your task is to parse the user's research request and produce a compact JSON object for initializing the Research Graph.

Extract:
1. The user's research goal
2. The expected report language
3. A small set of initial research queries with similar granularity

Rules:
- Return only valid JSON. Do not wrap it in Markdown.
- Do not invent specific facts, sources, citations, or conclusions.
- If the user does not specify a field, infer a reasonable default and record the uncertainty in `notes`.
- Initial queries should be suitable for creating Task/Query nodes in the Research Graph.
- Initial queries should be parallel dimensions under the same research goal, not deep follow-up questions.
- Prefer 3 to 6 initial queries. Use fewer only when the request is narrow.
- Each query must be specific enough for a Searcher agent to execute.

Return this JSON shape:
{{
  "research_goal": "research goal statement derived from the user request",
  "language": "Expected language of sources and report, or null if not specified",
  "initial_queries": [
    "The concrete research question to investigate.",
    "query2",
    "query3",
    ...
  ]
}}

User request:{user_request}
"""

extract_content = """Generate a structured analysis of the following content by:
1. Identifying the most salient keywords (focus on nouns, verbs, and key concepts)
2. Extracting key insights or conclusions that can be drawn from the content, atomic and specific enough to be useful for reasoning
3. Creating a concise summary of the entire content

Format the response as a JSON object:
{{
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
}}

Content for analysis:
"""

analyze_sufficiency = """You are evaluating evidence coverage in a research knowledge graph for a specific research query.

Research Query: {query_text}

Current Research Subgraph (JSON):
{subgraph_json}

Assess the evidence quality and coverage. Consider:
1. How many unique, high-quality evidence nodes are present?
2. Are the key aspects of the query addressed by evidence?
3. Are there significant unresolved gaps or conflicting evidence?
4. Is the evidence specific enough (data, mechanisms, examples, citations) rather than vague summaries?

Rules:
- Return only valid JSON. Do not wrap it in Markdown.
- coverage_score of 0.7 or above means evidence is sufficient to write about this query.
- suggest_vertical: true if the query has partial evidence but needs deeper follow-up on mechanism, cause, data, or verification.
- suggest_horizontal: true if the query reveals clearly missing parallel research dimensions that were not in the original plan.

Return this JSON shape:
{{
  "coverage_score": <float 0.0 to 1.0>,
  "sufficient": <true if coverage_score >= 0.7 and no blocking gaps>,
  "gaps": ["<specific evidence gap 1>", "<specific evidence gap 2>"],
  "suggest_horizontal": <true|false>,
  "suggest_vertical": <true|false>,
  "reason": "<one-sentence explanation of the assessment>"
}}
"""

summarize_subgraph = """You are summarizing the current state of a research knowledge graph subgraph.

Research Graph Subgraph (JSON):
{subgraph_json}

Generate a concise, structured research status summary covering:
1. What has been researched and what key findings have been established
2. Key claims and evidence collected (be specific: numbers, names, dates where available)
3. Known conflicts or uncertainties that remain unresolved
4. Remaining evidence gaps and what should be investigated next

Format as a professional research status note. Be specific and factual — do not fabricate details not present in the graph.
Respond in the same language as the research content.
"""
