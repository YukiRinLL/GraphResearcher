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
{
  "research_goal": "research goal statement derived from the user request",
  "language": "Expected language of sources and report, or null if not specified",
  "initial_queries": [
    "The concrete research question to investigate.",
    "query2",
    "query3",
    ...
  ],
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
  - "needs_vertical": some evidence exists but key mechanisms, causes, data scope, or conflicts remain unresolved — drill deeper on this query.
  - "needs_horizontal": this query only covers part of the problem space; parallel sibling dimensions are missing.
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