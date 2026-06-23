import sys
from src.models import (
    PresentationRequest, EvidencePack,
    PresentationStrategy, SlideIntent, SlidePlan
)
from src.utils import call_llm, parse_json, log, CONFIG

_SYSTEM = """You are a presentation architect.
Your job is to create a slide plan — NOT slide content.
Each slide has a clear purpose, a specific layout topology, and references which evidence chunks support it.
Respond ONLY in valid JSON. No markdown fences, no preamble, no explanation."""

_PROMPT = """Create a {slide_count}-slide presentation plan.

Topic     : {topic}
Audience  : {audience}
Objective : {objective}

Narrative strategy:
  Core message : {core_message}
  Adaptation   : {audience_adaptation}
  Recommended sections: {recommended_sections}
  Presentation Pacing : {presentation_pacing}

Available evidence chunks:
{evidence_text}

Return a JSON object in exactly this format:
{{
  "slides": [
    {{
      "slide_id": 1,
      "purpose": "one sentence describing what this slide communicates",
      "layout_type": "Title",
      "evidence_ids": []
    }},
    {{
      "slide_id": 2,
      "purpose": "another sentence describing the slide's purpose",
      "layout_type": "Standard-Bullets",
      "evidence_ids": ["chunk_id_1"]
    }}
  ]
}}

Rules:
- Exactly {slide_count} slides
- Follow the Recommended sections and Presentation Pacing to determine the flow.
- Slide 1 is always the title/overview -> layout_type MUST be "Title".
- The layout_type for all other slides MUST be exactly one of: "Big-Message", "Two-Column", "Assertion-Data", or "Standard-Bullets".
- Match the layout_type to the intent: 
  * "Big-Message" for high-level concepts or stark takeaways.
  * "Two-Column" for comparisons (e.g., pros/cons, old vs new).
  * "Assertion-Data" for highly statistical or metric-driven slides.
  * "Standard-Bullets" for standard explanations.
- Each evidence_id must be one of the 8-character chunk IDs listed above.
- Do not generate slide content — only purpose, layout, and evidence mapping.
- Every non-title slide should have at least one evidence_id.
"""

def _build_evidence_text(evidence: EvidencePack) -> str:
    all_chunks = evidence.sections + evidence.concepts + evidence.tables + evidence.figures
    lines = []
    for c in all_chunks:
        preview = c.text[:200].replace("\n", " ").strip()
        lines.append(f"[{c.chunk_id[:8]}] ({c.type}, page {c.page}, {c.section[:40]}) {preview}")
    return "\n".join(lines)

def generate_slide_plan(
    request: PresentationRequest,
    evidence: EvidencePack,
    strategy: PresentationStrategy | None = None,
) -> SlidePlan:
    """
    S5 — LLM generates a SlidePlan from request + evidence + strategy.
    Assigns specific layout topologies based on the presentation pacing.
    """
    max_retries  = CONFIG["agent"]["max_plan_retries"]
    all_chunks   = evidence.sections + evidence.concepts + evidence.tables + evidence.figures
    evidence_text = _build_evidence_text(evidence)
    valid_ids    = {c.chunk_id[:8] for c in all_chunks}

    # Use strategy if provided, else use safe defaults
    core_message        = strategy.core_message if strategy else f"Understanding {request.topic}"
    audience_adaptation = strategy.audience_adaptation if strategy else ""
    presentation_pacing = strategy.presentation_pacing if strategy else "Standard pacing."
    recommended_sections = (
        ", ".join(strategy.recommended_sections) if strategy
        else "Introduction, Core Concepts, Key Findings, Conclusion"
    )

    prompt = _PROMPT.format(
        slide_count=request.slide_count,
        topic=request.topic,
        audience=request.audience,
        objective=request.objective,
        core_message=core_message,
        audience_adaptation=audience_adaptation,
        presentation_pacing=presentation_pacing,
        recommended_sections=recommended_sections,
        evidence_text=evidence_text,
    )

    for attempt in range(1, max_retries + 1):
        log("planner", f"Attempt {attempt}/{max_retries}...")
        raw    = call_llm(_SYSTEM, prompt)
        parsed = parse_json(raw)

        if parsed is None:
            log("planner", f"Invalid JSON on attempt {attempt}, retrying...")
            continue

        slides_data = parsed.get("slides", [])

        if len(slides_data) == 0:
            log("planner", "No slides in response, retrying...")
            continue

        if abs(len(slides_data) - request.slide_count) > 1:
            log("planner", f"Got {len(slides_data)} slides, expected {request.slide_count}, retrying...")
            continue

        # Build typed SlidePlan — filter hallucinated chunk IDs and enforce layout schemas
        slides = []
        valid_layouts = ["Title", "Big-Message", "Two-Column", "Assertion-Data", "Standard-Bullets"]
        
        for s in slides_data:
            clean_ids = [eid for eid in s.get("evidence_ids", []) if eid in valid_ids]
            
            # Enforce layout enum, fallback to standard if hallucinated
            layout = s.get("layout_type", "Standard-Bullets")
            if layout not in valid_layouts:
                layout = "Standard-Bullets"
                
            slides.append(SlideIntent(
                slide_id=s["slide_id"],
                purpose=s["purpose"],
                layout_type=layout,
                evidence_ids=clean_ids,
            ))

        plan = SlidePlan(slides=slides, total=len(slides))
        log("planner", f"Valid plan: {plan.total} slides")
        return plan

    log("planner", "Max retries exceeded, returning empty plan")
    return SlidePlan(slides=[], total=0)

if __name__ == "__main__":
    from src.query_compiler import compile_query
    from src.retrieval import retrieve
    from src.strategy import generate_strategy

    raw_query = (
        sys.argv[1] if len(sys.argv) > 1
        else "make a 7 slide presentation comparing RAG to standard generation models"
    )
    doc_id = sys.argv[2] if len(sys.argv) > 2 else "Rag"

    request  = compile_query(raw_query)
    evidence = retrieve(request.topic, top_k=15, doc_id=doc_id)
    strategy = generate_strategy(request, evidence)
    plan     = generate_slide_plan(request, evidence, strategy=strategy)

    print(f"\n{'='*50}")
    print(f"SLIDE PLAN — {plan.total} slides")
    print(f"{'='*50}")
    for slide in plan.slides:
        print(f"\nSlide {slide.slide_id} [{slide.layout_type}]: {slide.purpose}")
        print(f"  Evidence IDs : {slide.evidence_ids}")