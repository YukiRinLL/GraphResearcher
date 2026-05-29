"""Reporter agent: graph-grounded long-form report generation."""

import json
import logging

from langchain.chat_models import init_chat_model

logger = logging.getLogger(__name__)

# ── Prompts ────────────────────────────────────────────────────────────────────

_OUTLINE_PROMPT = """You are a professional research writer tasked with creating an evidence-bound report outline.

Research Goal: {research_goal}
Language: {language}

Research Graph Context:
{context_json}

Create a structured report outline where every section is explicitly grounded in the evidence from the research graph.

Rules:
- Return only valid JSON. Do not wrap it in Markdown.
- Each section must bind to at least one query ID and list relevant evidence IDs.
- Order sections logically (introduction → core findings → discussion → conclusion).
- Prefer 4-8 sections. Merge thin sections; split overloaded ones.
- Note any unresolved conflicts that must be disclosed in the relevant section.

Return this JSON shape:
{{
  "title": "<report title>",
  "sections": [
    {{
      "heading": "<section heading>",
      "query_ids": ["<query node ID>", ...],
      "evidence_ids": ["<evidence node ID>", ...],
      "key_points": ["<key point to cover>", ...],
      "conflict_ids": ["<conflict node ID if any>", ...]
    }}
  ]
}}
"""

_SECTION_PROMPT = """You are a professional research writer. Write the following report section in a scholarly style.

Report Title: {report_title}
Section Heading: {heading}
Language: {language}

Key Points to Cover:
{key_points}

Relevant Evidence (use these as the factual basis — do not introduce facts not present here):
{evidence_json}

Relevant Sources (for inline citation — use numbered references [1], [2], etc.):
{sources_json}

Conflicts to Disclose (if any):
{conflicts_json}

Writing Guidelines:
- Write in a professional, analytical tone appropriate for a research report.
- Every factual claim must be backed by the evidence provided above.
- Use inline numbered citations [N] when citing specific evidence or sources.
- Disclose conflicts and uncertainties honestly rather than hiding them.
- Aim for 200-400 words per section unless the evidence warrants more.
- Do NOT wrap output in any JSON or code blocks — write plain prose.
"""

_COMPILE_PROMPT = """You are compiling a final research report from pre-written sections.

Report Title: {report_title}
Language: {language}

Sections (in order):
{sections_text}

All Sources (for the reference list):
{all_sources_json}

Instructions:
1. Output the full report as Markdown.
2. Start with a one-paragraph executive summary after the title.
3. Include all sections with their headings (##).
4. Ensure inline citation numbers [N] in sections map consistently to the ## References section at the end.
5. The ## References (中文报告用 ## 参考文献) section must list every source as:
   [N] Title. Publisher/Author. Date. URL
   If no sources are available, write "No external sources were collected in this research run."
6. Maintain scholarly tone throughout. Do not add information not present in the sections.
"""


class Reporter:
    """Reporter agent that generates a citation-bound research report from graph context.

    Uses a 3-stage pipeline:
      1. Generate a structured outline (JSON) bound to query/evidence IDs.
      2. Write each section as prose (with inline citations).
      3. Compile sections into a final Markdown report with a References section.
    """

    def __init__(self, config: dict):  # noqa: D107
        self.config = config
        self.model = init_chat_model(
            config.get("model_name", "gpt-4o-mini"),
            temperature=config.get("temperature", 0.5),
            max_tokens=config.get("max_tokens", 8192),
            max_retries=config.get("max_retries", 3),
        )

    async def run(self, graph_context: dict) -> str:
        """Generate a full research report from the exported graph context.

        Args:
            graph_context: Output of MemoryManager.export_report_context().

        Returns:
            Full Markdown report string.
        """
        research_goal = graph_context.get("research_goal", "Research Report")
        language = graph_context.get("language", "auto")
        sources: list[dict] = graph_context.get("sources", [])
        evidence: list[dict] = graph_context.get("evidence", [])
        conflicts: list[dict] = graph_context.get("conflicts", [])

        if not graph_context.get("queries") and not evidence:
            return f"# {research_goal}\n\nNo research data was collected. Please run the research pipeline first."

        # Build source index for citation numbers
        source_index: dict[str, int] = {}
        for i, src in enumerate(sources, start=1):
            src_id = src.get("id", "")
            if src_id:
                source_index[src_id] = i

        logger.info("Reporter: generating outline for '%s'", research_goal)

        # Stage 1: Generate outline
        outline = await self._generate_outline(graph_context, research_goal, language)
        if not outline or not outline.get("sections"):
            logger.warning("Reporter: outline generation failed or produced no sections; writing fallback report")
            return self._fallback_report(research_goal, evidence, sources)

        report_title = outline.get("title", research_goal)
        sections_data = outline.get("sections", [])

        # Stage 2: Write each section
        logger.info("Reporter: writing %d sections", len(sections_data))
        written_sections: list[tuple[str, str]] = []
        for sec in sections_data:
            heading = sec.get("heading", "")
            key_points = sec.get("key_points", [])
            evidence_ids = set(sec.get("evidence_ids", []))
            conflict_ids = set(sec.get("conflict_ids", []))

            sec_evidence = [ev for ev in evidence if ev.get("id") in evidence_ids]
            sec_conflicts = [c for c in conflicts if c.get("id") in conflict_ids]
            # Include all sources if we can't narrow them down
            sec_sources = sources

            prose = await self._write_section(
                report_title=report_title,
                heading=heading,
                key_points=key_points,
                evidence=sec_evidence,
                sources=sec_sources,
                conflicts=sec_conflicts,
                language=language,
            )
            written_sections.append((heading, prose))

        # Stage 3: Compile final report
        logger.info("Reporter: compiling final report")
        final_report = await self._compile_report(
            report_title=report_title,
            sections=written_sections,
            sources=sources,
            language=language,
        )

        return final_report

    async def _generate_outline(
        self, graph_context: dict, research_goal: str, language: str
    ) -> dict:
        context_json = json.dumps(
            {
                "queries": [
                    {
                        "id": q.get("id"),
                        "text": q.get("text"),
                        "status": q.get("status"),
                        "evidence_count": len(q.get("evidence", [])),
                    }
                    for q in graph_context.get("queries", [])
                ],
                "evidence_count": len(graph_context.get("evidence", [])),
                "conflict_count": len(graph_context.get("conflicts", [])),
                "source_count": len(graph_context.get("sources", [])),
            },
            ensure_ascii=False,
            indent=2,
        )

        prompt = _OUTLINE_PROMPT.format(
            research_goal=research_goal,
            language=language,
            context_json=context_json,
        )

        response = await self.model.ainvoke(prompt)
        content = getattr(response, "content", str(response)).strip()

        try:
            if content.startswith("```"):
                lines = content.splitlines()
                content = "\n".join(ln for ln in lines if not ln.startswith("```")).strip()
            return json.loads(content)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Reporter outline JSON parse failed: %s", exc)
            return {}

    async def _write_section(
        self,
        report_title: str,
        heading: str,
        key_points: list[str],
        evidence: list[dict],
        sources: list[dict],
        conflicts: list[dict],
        language: str,
    ) -> str:
        prompt = _SECTION_PROMPT.format(
            report_title=report_title,
            heading=heading,
            language=language,
            key_points="\n".join(f"- {p}" for p in key_points) or "(no key points specified)",
            evidence_json=json.dumps(evidence[:20], ensure_ascii=False, indent=2),
            sources_json=json.dumps(
                [{"index": i + 1, **s} for i, s in enumerate(sources[:30])],
                ensure_ascii=False,
                indent=2,
            ),
            conflicts_json=json.dumps(conflicts, ensure_ascii=False, indent=2) or "[]",
        )

        response = await self.model.ainvoke(prompt)
        return getattr(response, "content", str(response))

    async def _compile_report(
        self,
        report_title: str,
        sections: list[tuple[str, str]],
        sources: list[dict],
        language: str,
    ) -> str:
        sections_text = "\n\n".join(
            f"### {heading}\n\n{prose}" for heading, prose in sections
        )

        prompt = _COMPILE_PROMPT.format(
            report_title=report_title,
            language=language,
            sections_text=sections_text,
            all_sources_json=json.dumps(
                [{"index": i + 1, **s} for i, s in enumerate(sources)],
                ensure_ascii=False,
                indent=2,
            ),
        )

        response = await self.model.ainvoke(prompt)
        return getattr(response, "content", str(response))

    def _fallback_report(
        self, research_goal: str, evidence: list[dict], sources: list[dict]
    ) -> str:
        """Minimal fallback when outline generation fails."""
        lines = [f"# {research_goal}\n"]
        if evidence:
            lines.append("## Collected Evidence\n")
            for ev in evidence[:20]:
                lines.append(f"- {ev.get('claim', '')}")
        if sources:
            lines.append("\n## References\n")
            for i, src in enumerate(sources, 1):
                title = src.get("title") or src.get("url", "")
                url = src.get("url", "")
                lines.append(f"[{i}] [{title}]({url})")
        return "\n".join(lines)
