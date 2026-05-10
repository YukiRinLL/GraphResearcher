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

summarize_subgraph = """"""