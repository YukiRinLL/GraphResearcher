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
- Extract UNIQUE IDENTIFIERS from the request: specific person names, institution names, collection names, catalog numbers, archaeological site names, specific measurements, dates, or other distinguishing features
- Extract TARGET ENTITY type: what category of entity is being researched (artifact, person, organization, event, etc.)
- Extract POTENTIAL CONFUSION entities: what similar entities might be confused with the target (e.g., same name but different object, related but distinct items)
- This analysis ensures queries are specific enough to find the exact target and avoid disambiguation failures

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
- MANDATORY: Every query MUST include at least 2-3 UNIQUE IDENTIFIERS: specific person names, institution names, collection names, catalog numbers, archaeological site names, specific measurements, dates, or other distinguishing features that help disambiguate the target from similar entities.
- MANDATORY: Every query MUST include SOURCE TYPE QUALIFIERS to direct searches toward authoritative materials: such as "museum collection", "journal article", "scholarly publication", "official record", "primary source", "academic paper", or "university press".
- MANDATORY: Every query MUST include specific time period or date references when applicable (e.g., specific years, periods, centuries) to help narrow results.
- Write a TIGHT natural-language search phrase with concrete entities and relevant qualifiers such as time window, region, policy version, or factual dimension.
- Do NOT put report sections, table formatting, acceptance standards, or citation instructions into query.text.
- Do NOT write an instruction to an agent. Avoid phrases that command research actions.
- Author the query text in the language of the user request.
- Add `-site:domain` to every query for each forbidden domain. Do not put exact forbidden URLs into query.text.

Query quality check (before finalizing):
- Verify the query does NOT contain overly broad terms without specific qualifiers
- Verify the query includes concrete, searchable identifiers rather than generic topic terms
- Verify the query would help a search engine return results about the SPECIFIC target, not a broader category
- If the query fails any check, revise it to add more specific identifiers

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
- **Contradiction detection**: When multiple Statements/Evidence describe the same attribute (e.g., museum location, weight, dimensions) with contradictory information:
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

Entity disambiguation reminder:
- Before generating the query, identify the specific unique identifiers from the parent topic and existing queries
- Ensure the new query maintains the same entity specificity level as the original queries
- If previous queries had disambiguation issues (e.g., confusing related entities), add MORE specific identifiers to this query

Requirements:
- Inline the parent's concrete subject BY VALUE into every new query. Never reference another query.
- Each query must be SELF-CONTAINED and a TIGHT natural-language search phrase.
- MANDATORY: Include at least 2-3 UNIQUE IDENTIFIERS: specific person names, institution names, collection names, catalog numbers, archaeological site names, specific measurements, dates, or other distinguishing features that disambiguate the target from similar entities.
- MANDATORY: Add SOURCE TYPE QUALIFIERS to direct searches toward authoritative materials: such as "museum collection", "journal article", "scholarly publication", "official record", "primary source", "academic paper", or "university press".
- MANDATORY: Include specific time period or date references when applicable.
- Cover only the assigned related gaps; do not repeat any existing Query.
- Preserve forbidden domains with `-site:domain`; do not print exact forbidden URLs into the query.
- Author the query text in the language of the research goal.
- Tag each query with an importance ("core" / "supporting" / "peripheral") relative to the research goal's core conclusions.
- Include concrete acceptance_criteria copied or refined from the assigned atomic gap.

Query quality check (before finalizing):
- Verify the query does NOT contain overly broad terms without specific qualifiers
- Verify the query includes concrete, searchable identifiers
- Verify the query would help a search engine return results about the SPECIFIC target, not a broader category

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
