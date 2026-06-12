from src.models import PresentationRequest, EvidencePack, PresentationStrategy
from src.utils import call_llm, parse_json, log


_SYSTEM = """You are an expert presentation strategist.
Given a topic, audience, objective, and available evidence, define:
1. The single core message the audience should leave with
2. How to adapt tone and depth for this specific audience
3. An ordered list of recommended sections that can be supported by the evidence

Return ONLY valid JSON. No markdown fences, no explanation."""

_PROMPT = """Request:
  Topic    : {topic}
  Audience : {audience}
  Objective: {objective}
  Slides   : {slide_count}

Available evidence ({n_chunks} chunks):
{evidence_summary}

Return JSON in exactly this format:
{{
  "core_message": "one sentence — what should the audience remember after this presentation",
  "audience_adaptation": "one sentence — how tone/depth/vocabulary should be adjusted",
  "recommended_sections": ["Section 1 title", "Section 2 title", ...]
}}

Rules:
- recommended_sections must have between {min_sections} and {max_sections} items
- Each section title should map to actual content in the evidence above
- Do not invent sections that have no evidence support
- Order sections as they would appear in the presentation"""


def _build_evidence_summary(evidence: EvidencePack, max_chunks: int = 15) -> str:
    """
    Build a structured evidence summary for the strategy prompt.
    Groups by type so the LLM understands what's available.
    """
    lines = []

    if evidence.sections:
        lines.append("SECTIONS:")
        for c in evidence.sections[:max_chunks]:
            preview = c.text[:200].replace("\n", " ").strip()
            lines.append(f"  [{c.section}] {preview}")

    if evidence.tables:
        lines.append("TABLES:")
        for c in evidence.tables[:3]:
            preview = c.text[:150].replace("\n", " ").strip()
            lines.append(f"  [{c.section}] {preview}")

    if evidence.figures:
        lines.append("FIGURES:")
        for c in evidence.figures[:3]:
            lines.append(f"  [{c.section}] {c.text[:100].strip()}")

    return "\n".join(lines) if lines else "No evidence available."


def generate_strategy(
    request: PresentationRequest,
    evidence: EvidencePack,
    max_retries: int = 2,
) -> PresentationStrategy:
    """S4 — Generate narrative presentation strategy from request + evidence."""

    all_chunks = evidence.sections + evidence.concepts + evidence.tables + evidence.figures
    evidence_summary = _build_evidence_summary(evidence)

    # slide_count drives how many sections to recommend
    min_sections = max(3, request.slide_count // 3)
    max_sections = request.slide_count - 1   # leave room for title + conclusion

    prompt = _PROMPT.format(
        topic=request.topic,
        audience=request.audience,
        objective=request.objective,
        slide_count=request.slide_count,
        n_chunks=len(all_chunks),
        evidence_summary=evidence_summary,
        min_sections=min_sections,
        max_sections=max_sections,
    )

    for attempt in range(1, max_retries + 1):
        log("strategy", f"Generating strategy (attempt {attempt}/{max_retries})")
        raw = call_llm(_SYSTEM, prompt)
        parsed = parse_json(raw)

        if parsed and "core_message" in parsed and "recommended_sections" in parsed:
            try:
                strategy = PresentationStrategy(**parsed)
                log("strategy", f"Core message: {strategy.core_message}")
                log("strategy", f"Sections: {strategy.recommended_sections}")
                return strategy
            except Exception as e:
                log("strategy", f"Pydantic validation failed: {e}")

        log("strategy", f"Attempt {attempt}: invalid response, retrying...")

    # Fallback
    log("strategy", "WARNING: using fallback strategy")
    return PresentationStrategy(
        core_message=f"Understanding {request.topic}",
        audience_adaptation=f"Content tailored for {request.audience} audience",
        recommended_sections=[
            "Introduction",
            "Core Concepts",
            "Key Findings",
            "Applications",
            "Conclusion",
        ],
    )


def grade_strategy(strategy: PresentationStrategy) -> tuple[str, str]:
    """
    S4c — Deterministic strategy critic.
    Checks structural validity without an LLM call.
    """
    if not strategy.core_message.strip():
        return "retry", "core_message is empty"

    if len(strategy.core_message.split()) < 5:
        return "retry", "core_message is too short — less than 5 words"

    if len(strategy.recommended_sections) < 3:
        return "retry", (
            f"only {len(strategy.recommended_sections)} sections recommended "
            f"— need at least 3"
        )

    # Check for duplicate section titles
    titles = [s.strip().lower() for s in strategy.recommended_sections]
    if len(titles) != len(set(titles)):
        return "retry", "duplicate section titles in recommended_sections"

    # Check for empty section titles
    empty = [s for s in strategy.recommended_sections if not s.strip()]
    if empty:
        return "retry", f"{len(empty)} empty section titles"

    return "good", ""