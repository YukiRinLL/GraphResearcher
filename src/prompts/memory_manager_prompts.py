"""Prompt templates for GraphResearcher's MemoryManager workflows."""

init_research = """You are the Query Planner for GraphResearcher.
Parse the user's research request and produce a compact JSON object that seeds the Research Graph with a set of INITIAL search queries.

Extract:
1. The user's research goal (one sentence, derived from the request).
2. The expected output/report language.
3. The requested or reasonably inferred time window, region scope, and source preferences.
4. A small report-level research contract (`objectives`).
5. The task archetype and delivery contract that describe how the final report should be structured.
6. A staged query portfolio plan. Only `discovery` queries become initial live queries; `slot_completion` and `deep_dive` stay as planned follow-up work unless later materialized.
7. Candidate INITIAL queries and the objective keys each query covers.

How to decompose (critical):
- Split along the request's OWN thematic structure, NOT by geography/region. If the request enumerates dimensions (e.g. technology routes -> representative companies -> {tech path, product progress, commercialization, financing, team}), the top-level split follows that thematic spine. A scope word like "global" is only a qualifier, never a decomposition axis — do not split into North America / China / Europe.
- Objectives are report-level deliverables, never one company detail, parameter,
  extra example, source verification, or other leaf fact.
- Default `scope_mode` to `bounded`. Use `exhaustive` only when the user
  explicitly asks for all items, a complete inventory, or exhaustive coverage.
- Classify the task into exactly one `task_archetype`:
  `open_research | entity_article | comparative_matrix | structured_slots | timeline_tracking`.
- Produce a `delivery_contract` with this exact shape:
  `{"report_mode": "...", "required_section_types": ["lead","body","comparison","limitations"], "required_slot_labels": ["..."], "comparison_required": bool, "entity_focus": bool, "strict_time_window": bool, "prefer_compression_over_expansion": true}`.
- Produce a staged `query_portfolio_plan`. Each item must have:
  `{"plan_id": "...", "portfolio_stage": "discovery|slot_completion|deep_dive", "text": "...", "importance": "core|supporting|peripheral", "objective_keys": ["..."], "acceptance_criteria": ["..."], "slot_targets": ["..."], "section_targets": ["..."], "search_subject_key": "..."}`.
- Make `initial_queries` the `discovery` subset of the staged plan. The code may still rebalance which discovery items become real Query nodes.
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
  "scope_mode": "bounded|exhaustive",
  "task_archetype": "open_research|entity_article|comparative_matrix|structured_slots|timeline_tracking",
  "delivery_contract": {
    "report_mode": "short label for the final report mode",
    "required_section_types": ["lead", "body", "comparison", "limitations"],
    "required_slot_labels": ["slot label"],
    "comparison_required": false,
    "entity_focus": false,
    "strict_time_window": false,
    "prefer_compression_over_expansion": true
  },
  "objectives": [
    {
      "objective_key": "stable-short-key",
      "description": "report-level deliverable",
      "requirement": "must|should",
      "weight": 1.0,
      "acceptance_criteria": ["minimum reportable standard"]
    }
  ],
  "query_portfolio_plan": [
    {
      "plan_id": "stable-short-id",
      "portfolio_stage": "discovery|slot_completion|deep_dive",
      "text": "tight self-contained search phrase",
      "importance": "core|supporting|peripheral",
      "objective_keys": ["stable-short-key"],
      "acceptance_criteria": ["specific evidence required"],
      "slot_targets": ["slot label"],
      "section_targets": ["lead|body|comparison|limitations"],
      "search_subject_key": "stable-topic-key"
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

assess_query = """You are the Graph Manager for GraphResearcher. Assess exactly one Query from its OWN evidence and direct-child summaries. Do not infer evidence from parent or sibling branches.

Rules:
- Return only valid JSON.
- `sufficiency_score` is in [0, 1].
- Return `recommendation="sufficient"` only when the Query's acceptance criteria are met with reliable evidence.
- If more research may help, split the missing work into ATOMIC gaps. Gap
  creation does not mean the gap will be searched; global portfolio evaluation
  selects only work with enough report-level marginal value.
- Each gap needs an importance, a generic gap category, affected objective keys,
  a reusable search subject key, decision impact, expected confidence gain,
  estimated search rounds, concrete acceptance criteria, and where possible the
  intended `preferred_stage`, `slot_targets`, and `section_targets`.
- Prefer `slot_completion`, `section_completeness`, or `lead_readiness` when the
  missing work is primarily about report structure rather than more raw facts.
- Return `blocked` only when reliable evidence cannot reasonably be obtained.

Return:
{
  "sufficiency_score": 0.0,
  "covered": ["supported aspects"],
  "gaps": [
    {
      "description": "one atomic missing fact or analysis",
      "importance": "core|supporting|peripheral",
      "gap_category": "missing_core_evidence|fatal_conflict|enrichment|additional_example|verification|detail|slot_completion|section_completeness|lead_readiness",
      "preferred_stage": "slot_completion|deep_dive|null",
      "objective_keys": ["affected-report-objective-key"],
      "search_subject_key": "stable-topic-key-for-grouping-related-gaps",
      "slot_targets": ["delivery slot label"],
      "section_targets": ["lead|body|comparison|limitations"],
      "decision_impact": 0.0,
      "confidence_gain": 0.0,
      "estimated_search_rounds": 1,
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

normalize_claims = """You are the Claim Normalizer for GraphResearcher.
Create canonical research Claims from the provided Query-owned Statements and Evidence.

Definitions:
- Statement: what one Document says, preserving source context.
- Evidence: a concrete verifiable item from a Document.
- Claim: a normalized research proposition synthesized from one or more Statements/Evidence. It is not a quote from one source.

Rules:
- Return only valid JSON.
- Base every Claim on provided node IDs. Do not invent facts.
- Merge duplicate or paraphrased Statements into one Claim when they express the same proposition.
- Use evidence stance: supports, contradicts, or qualifies.
- If the material is weak, keep the Claim narrow and put limitations/qualifiers in fields.

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
Author one self-contained child search query that jointly covers the assigned
atomic gaps sharing one search subject.

Research goal: {research_goal}
Task archetype: {task_archetype}
Delivery contract: {delivery_contract}
Preferred stage: {preferred_stage}
Parent topic (the subject to deepen, or the parent whose dimensions to complete): {parent_text}
Existing sibling queries under the attach point (do NOT duplicate their coverage): {sibling_texts}
Atomic gaps to cover: {gaps}
Reason: {reason}

Requirements:
- Inline the parent's concrete subject BY VALUE into every new query (e.g. write "Figure AI 人形机器人 量产进度 2025", never "该公司的量产进度"). Never reference another query: no "上述/前述/该/这些/the above".
- Each query must be SELF-CONTAINED and a TIGHT natural-language search phrase: key entities + time window, no filler, not a verbose question, not bare keywords, not an instruction to an agent.
- Cover only the assigned related gaps; do not repeat what the existing siblings already cover.
- If `preferred_stage=slot_completion`, make the query directly serve the missing slot/section instead of broad background expansion.
- If `preferred_stage=deep_dive`, make the query directly target verification, conflict resolution, or missing core evidence.
- Author the query text in the language of the research goal.
- Tag each query with an importance ("core" / "supporting" / "peripheral") relative to the research goal's core conclusions, judged the same way as the parent's own role.
- Include concrete acceptance_criteria copied or refined from the assigned atomic gap.

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

Return only JSON:
{
  "objectives": [
    {
      "objective_key": "existing key",
      "coverage": 0.0,
      "confidence": 0.0,
      "reason": "short evidence-based explanation"
    }
  ]
}

Research contract:
{objectives}

Query summaries:
{queries}
"""
