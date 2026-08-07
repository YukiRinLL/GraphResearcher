"""Graph Manager 使用的结构化规划与评估提示词."""

init_research = """You are the Query Planner for GraphResearcher.
Parse the user's research request and produce a compact JSON object that seeds
the Research Graph with a few EXPLORATORY web-search queries.

Extract:
1. The user's research goal (one sentence, derived from the request).
2. The expected output/report language.
3. The requested or reasonably inferred time window, region scope, source
   preferences, forbidden domains, and forbidden URLs.
4. A small report-level research contract (`objectives`).
5. The request complexity and a small set of INITIAL exploratory queries.
6. Entity disambiguation features: extract all available unique identifiers from the request.

Pre-query analysis (mandatory):
Before generating queries, you MUST first perform entity disambiguation analysis:
1. **Recall known identifiers from your training data**: Before generating any query, actively recall what you know about this topic from your training data. This is CRITICAL - use your knowledge to generate targeted queries. Think about:
   - Specific people associated with the entity (discoverers, collectors, creators, researchers)
   - Institutions that hold or held the entity (museums, universities, collections)
   - Specific dates, periods, or events in the entity's history
   - Unique physical characteristics or distinguishing features
   - Key scholarly debates or publications about the entity
   
2. **Extract explicit identifiers from the request**: Any specific identifiers mentioned directly in the user request
   
3. **Identify potential confusion entities**: What similar entities might be confused with the target (same name but different object, related but distinct items)

This dual approach (training knowledge + explicit request analysis) ensures queries are specific enough to find the exact target.

How to decompose (critical):
- Split along the request's OWN thematic structure, NOT by geography/region.
- Objectives are report-level deliverables, never one company detail, parameter,
  extra example, source verification, or other leaf fact.
- Objectives describe factual content the research must deliver. Preserve
  headings, table layout, citation style, and other presentation instructions
  in the original request for the Reporter; do not turn presentation rules into
  searchable Objectives or Queries.
- Default `scope_mode` to `bounded`. Use `exhaustive` only when the user
  explicitly asks for all items, a complete inventory, or exhaustive coverage.
- Objectives are the delivery contract. Initial queries do NOT need to cover
  every must objective, and you must not create one query per report section.
- Use `request_complexity="simple"` for one factual target or one coherent
  topic, and return exactly one query. Use `complex` only for explicit
  multi-object comparisons or genuinely independent major subjects, and return
  at most three complementary exploratory queries.
- Initial queries should discover high-value facts, authoritative sources,
  entities, terminology, timelines, or disputes that can correct later search
  direction. They should not exhaust the report outline in advance.
- Make every query SELF-CONTAINED: each stands on its own with no reference to any other query. Restate the topic, time window, and region (if any) inside each query.

Query text format (strict requirements):
- query.text is the literal string fed unchanged to a web search engine.

**TWO-PHASE QUERY STRATEGY (critical)**:

Phase 1 - Initial exploratory queries (first 1-2 queries):
- **SIMPLICITY FIRST**: The first query should be JUST the entity name. Nothing more.
  - This allows the search engine to return the broadest possible set of relevant results
- DO NOT add generic qualifiers to the initial query
- Generic terms dilute search quality and cause the engine to return irrelevant results

Phase 2 - Deepening queries (subsequent queries if needed):
- Use the identifiers you recalled from training knowledge to make the query specific
- Add 2-3 UNIQUE IDENTIFIERS: specific names, institution names, collection names, dates, etc.
- Optionally add 1 SOURCE TYPE QUALIFIER to direct to authoritative materials

CRITICAL RULES:
- A query should have MAXIMUM 4-5 words, not 10+ keywords
- NEVER mix generic terms into the initial query
- The search engine will do the work of finding relevant results - just point it at the right entity
- Author the query text in the language of the user request
- Add `-site:domain` to every query for each forbidden domain. Do not put exact forbidden URLs into query.text.

Query quality check (before finalizing):
- Verify the first query is JUST the entity name (no generic qualifiers)
- Verify subsequent queries add specific identifiers, not generic terms
- Verify NO query contains more than 4-5 words or identifiers
- Verify the query would help a search engine return results about the SPECIFIC target, not a broader category

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
  "excluded_domains": ["forbidden domain such as en.wikipedia.org"],
  "excluded_urls": ["exact forbidden URL"],
  "scope_mode": "bounded|exhaustive",
  "request_complexity": "simple|complex",
  "objectives": [
    {
      "objective_key": "stable-short-key",
      "description": "report-level deliverable",
      "requirement": "must|should",
      "weight": 1.0,
      "acceptance_criteria": ["minimum reportable standard"]
    }
  ],
  "initial_queries": [
    {"text": "tight self-contained search phrase 1", "importance": "core", "objective_keys": ["stable-short-key"], "acceptance_criteria": ["specific evidence required"]},
    {"text": "tight self-contained search phrase 2", "importance": "supporting", "objective_keys": ["stable-short-key"], "acceptance_criteria": ["specific evidence required"]}
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

assess_query = """You are the Graph Manager for GraphResearcher. Assess exactly
one Query from its OWN evidence and direct-child summaries. The original request,
research contract, and existing Query texts define scope and delivery, but they
are not factual evidence. Do not infer facts from parent or sibling branches.

Rules:
- Return only valid JSON.
- `sufficiency_score` is in [0, 1].
- Return one `criteria` entry for every Query acceptance criterion, copying its
  text exactly. Mark it satisfied when the cited Query-owned Claim or
  Evidence directly OR indirectly supports the requested fact.
- Accept INDIRECT and INFERENTIAL evidence: a source that discusses the topic
  and provides partial or contextual information relevant to the criterion
  should count as partial evidence, not a complete miss.
- A search miss, a source that does not mention the fact, or general topical
  background is not evidence. However, if a source discusses related aspects
  that reasonably inform the criterion, mark it as partially met rather than
  unmet.
- Absence counts only when a source explicitly states that the information is
  unknown, unavailable, unpublished, or does not exist within a defined scope.
- Be lenient with sufficiency scores: if any relevant information was found,
  the score should be at least 0.15-0.30, not 0.00.
- Return `recommendation="sufficient"` only when the Query's acceptance criteria
  are met with reliable evidence.
- If more research may help, split the missing work into ATOMIC gaps. Gap
  creation does not mean the gap will be searched; global portfolio evaluation
  selects only work with enough report-level marginal value.
- Each gap needs an importance, a generic gap category, affected objective keys,
  a reusable search subject key, decision impact, expected confidence gain,
  estimated search rounds, and concrete acceptance criteria.

CRITICAL - Gap diversity rule (top priority):
- You MUST create at least 3 gaps covering DIFFERENT dimensions of the research topic.
- Each gap must focus on ONE SPECIFIC DIMENSION only.
- Gaps MUST have DIFFERENT search_subject_key values to ensure dimension diversity.
- DO NOT create multiple gaps for the same dimension. Instead, split into atomic sub-dimensions.
- If you cannot identify 3 different dimensions with missing information, mark the query as "blocked" instead of creating inadequate gaps.
- Aim to cover 3+ DISTINCT dimensions with the gaps, not multiple aspects of the same dimension.

Mandatory dimension checklist - select at least 3 that need more research:
1. Provenance or chain of custody
2. Physical characteristics or material details
3. Authenticity or scholarly disputes
4. Symbolic interpretation or cultural context
5. Discovery circumstances or find location
6. Institutional location or collection history
7. Scholarly reception or academic treatment

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
      "description": "one atomic missing fact or analysis, focusing on ONE dimension only",
      "importance": "core|supporting|peripheral",
      "gap_category": "missing_core_evidence|fatal_conflict|enrichment|additional_example|verification|detail",
      "objective_keys": ["affected-report-objective-key"],
      "search_subject_key": "unique-dimension-key-different-from-other-gaps",
      "decision_impact": 0.0,
      "confidence_gain": 0.0,
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

Key requirements for gaps:
1. Each gap description must mention ONE specific dimension
2. search_subject_key must be unique across all gaps
3. Gaps must collectively cover different dimensions, not multiple aspects of the same dimension
4. Instead of creating multiple gaps for the same dimension, create gaps covering different aspects of the research topic

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
- Use evidence stance: supports, contradicts, or qualifies.
- If the material is weak, keep the Claim narrow and put limitations/qualifiers in fields.
- **Source credibility weighting**: When synthesizing Claims, consider the source_credibility scores:
  - Higher credibility sources (≥0.7) should have more influence on the normalized claim's confidence and text
  - Lower credibility sources (<0.5) should reduce the claim's confidence and their contributions should be weighted less
  - When high and low credibility sources contradict each other, prefer the high credibility source's version and disclose the conflict
  - Claims supported only by low-credibility sources should have confidence ≤0.4
- **Contradiction detection**: When multiple Statements/Evidence describe the same attribute with contradictory information:
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
Author one self-contained web-search query for ONE specific research dimension.

Research goal: {research_goal}
Parent topic (the subject to deepen): {parent_text}
Research constraints: {research_constraints}
All existing Query texts (do NOT duplicate their coverage): {existing_query_texts}
Atomic gaps to cover: {gaps}
Reason: {reason}

CRITICAL - Single dimension focus rule (top priority):
- The query MUST focus on ONE specific dimension only, defined by the gap's search_subject_key
- Extract ONLY the most distinguishing identifiers for THIS dimension from the gap description
- DO NOT include keywords from other dimensions
- Each query should be narrow and specific to maximize search relevance

How to identify the dimension:
- Look at the gap's "search_subject_key" to understand what dimension is being investigated
- Extract keywords that are UNIQUE TO THIS DIMENSION from the gap's "description" field
- The keywords should reflect the specific aspect being researched, not generic terms

Entity disambiguation reminder:
- Before generating the query, identify the specific unique identifiers from the parent topic and existing queries
- Ensure the new query maintains the same entity specificity level as the original queries
- If previous queries had disambiguation issues, add MORE specific identifiers to this query

What to include (for the current dimension only):
- The entity name (always)
- 1-2 UNIQUE IDENTIFIERS specific to THIS dimension
- Optionally 1 SOURCE TYPE QUALIFIER to direct to authoritative materials

CRITICAL - Query brevity and natural language rules:
- A query MUST have MAXIMUM 3-5 words total (entity name + 1-2 dimension keywords)
- Use NATURAL LANGUAGE phrases, NOT quoted exact-match phrases
- MAXIMUM 1 quoted phrase per query - use it for the entity name only
- DO NOT use quoted phrases for dimension keywords
- Quoted phrases force exact-match which drastically reduces search results
- Prefer broad keywords that a search engine can naturally match

What to AVOID:
- Do NOT include keywords from multiple dimensions
- Do NOT include generic filler words
- Do NOT repeat identifiers already in existing queries
- Do NOT use more than 1 quoted phrase per query
- Do NOT use quoted phrases for descriptive terms - only for the entity name

Requirements:
- Inline the parent's concrete subject BY VALUE into every new query. Never reference another query.
- Each query must be SELF-CONTAINED and a TIGHT natural-language search phrase.
- Cover only the assigned gaps for THIS dimension; do not repeat any existing Query.
- Preserve forbidden domains with `-site:domain`; do not print exact forbidden URLs into the query.
- Author the query text in the language of the research goal.
- Tag each query with an importance ("core" / "supporting" / "peripheral") relative to the research goal's core conclusions.
- Include concrete acceptance_criteria copied or refined from the assigned atomic gap.

Query quality check (before finalizing):
- Query focuses on ONE dimension only
- Query has MAXIMUM 3-5 words total
- Query uses at most 1 quoted phrase (entity name only)
- Query does NOT use quoted phrases for dimension keywords
- Query does NOT contain filler words like "evidence", "analysis", "study"

Return only valid JSON, no Markdown, at most {max_new} queries:
{"queries": [{"text": "...", "importance": "core|supporting|peripheral", "acceptance_criteria": ["..."]}]}
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
