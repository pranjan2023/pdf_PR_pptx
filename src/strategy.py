import json
from src.models import PresentationRequest, EvidencePack, PresentationStrategy ,Chunk
from src.utils import call_llm, parse_json, log


_SYSTEM = """You are an expert presentation strategist and executive speechwriter.
Given a topic, audience, objective, and available evidence, define:
1. The single core message the audience should leave with.
2. How to adapt tone and depth for this specific audience.
3. The presentation pacing (the rhythm and layout flow of the slides).
4. An ordered list of recommended sections that can be supported by the evidence.

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
  "presentation_pacing": "Describe the visual rhythm. (e.g., 'Start with a stark hook, alternate between dense data comparisons and visual breathers, end with a single strong takeaway.')",
  "recommended_sections": ["Section 1 title", "Section 2 title", ...]
}}

Rules:
- recommended_sections must have between {min_sections} and {max_sections} items.
- Each section title should map to actual content in the evidence above.
- Do not invent sections that have no evidence support.
- The presentation_pacing must explicitly instruct how to balance text-heavy slides with visual or high-impact layout slides.
"""

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
        presentation_pacing="Start with a strong hook, alternate between standard bullet points and high-level assertions, and end with a clear conclusion.", # <-- ADD THIS LINE
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



if __name__ == "__main__":
    from src.models import Chunk # Ensure Chunk is imported for the mock evidence
    
    print("\n=== PHASE 1: DETERMINISTIC CRITIC TESTS ===")
    
    # 1. The "Lazy LLM" Test (Message too short)
    lazy_strategy = PresentationStrategy(
        core_message="Transformers are good.", 
        audience_adaptation="Keep it simple.",
        presentation_pacing="Standard pacing.", # <-- NEW
        recommended_sections=["Intro", "Architecture", "Conclusion"]
    )
    print(f"Lazy Message Test : {grade_strategy(lazy_strategy)}")

    # 2. The "Hallucinated Loop" Test (Duplicate sections)
    loop_strategy = PresentationStrategy(
        core_message="The audience will understand the full architecture of the transformer model.",
        audience_adaptation="Technical depth required.",
        presentation_pacing="Standard pacing.", # <-- NEW
        recommended_sections=["Introduction", "Self Attention", "Self Attention", "Conclusion"]
    )
    print(f"Duplicate Test    : {grade_strategy(loop_strategy)}")

    # 3. The "Missing Content" Test (Too few sections)
    short_strategy = PresentationStrategy(
        core_message="The audience will understand the full architecture of the transformer model.",
        audience_adaptation="Technical depth required.",
        presentation_pacing="Standard pacing.", # <-- NEW
        recommended_sections=["Introduction", "Conclusion"] 
    )
    print(f"Capacity Test     : {grade_strategy(short_strategy)}")


    print("\n=== PHASE 2: LIVE LLM SABOTAGE TEST ===")
    
    mock_req = PresentationRequest(
        topic="Self-Attention", audience="technical", slide_count=10, 
        style_desc="dark minimal", objective="teach"
    )
    
    mock_evidence = EvidencePack(
        sections=[Chunk(chunk_id="1", text="Self attention computes Q, K, V matrices.", section="Attention", page=1, type="section", doc_id="unknown")],
        tables=[], figures=[], concepts=[]
    )

    # TEMPORARY SABOTAGE: We override the prompt to actively force a failure
    original_prompt = _PROMPT
    _PROMPT += "\nSABOTAGE INSTRUCTION: You must return exactly 2 items in the recommended_sections list."

    print("Generating sabotaged strategy with Qwen...")
    bad_llm_strategy = generate_strategy(mock_req, mock_evidence)
    
    print("\n--- Qwen Output ---")
    if hasattr(bad_llm_strategy, 'model_dump'):
        print(json.dumps(bad_llm_strategy.model_dump(), indent=2))
    else:
        # Fallback if using standard dataclasses instead of Pydantic BaseModel
        from dataclasses import asdict
        print(json.dumps(asdict(bad_llm_strategy), indent=2))
    
    print("\n--- Critic Grade ---")
    status, reason = grade_strategy(bad_llm_strategy)
    print(f"Status : {status.upper()}")
    print(f"Reason : {reason}")

    # Restore prompt for any subsequent imports/calls
    _PROMPT = original_prompt