import sys
from src.models import SlidePlan, EvidencePack, SlideContent, PresentationStrategy
from src.utils import call_llm, parse_json, log, CONFIG


_SYSTEM = """You are a presentation content writer.
Generate structured slide content grounded in the provided evidence.
Write for the specified audience.
Respond ONLY in valid JSON. No markdown fences, no preamble."""

_PROMPT = """Generate content for slide {slide_id} of {total_slides}.

Overall presentation core message: {core_message}

Slide purpose : {purpose}
Audience      : {audience}

Previously covered (do not repeat these):
{previous_context}

Evidence for this slide:
{slide_evidence}

Return JSON in exactly this format:
{{
  "slide_id": {slide_id},
  "title": "concise slide title (max 8 words)",
  "bullets": [
    "bullet point 1 (max 15 words)",
    "bullet point 2 (max 15 words)",
    "bullet point 3 (max 15 words)"
  ],
  "takeaway": "one sentence key message of this slide",
  "speaker_notes": "2-3 sentences expanding on the slide for the presenter",
  "visual_hint": "text-only"
}}

Rules:
- Maximum 4 bullets per slide
- Each bullet maximum 15 words
- Title slide (slide 1) gets 1 bullet maximum — just the subtitle
- visual_hint must be one of: chart, diagram, table, text-only
- Bullets must be grounded in the evidence — do not invent facts
- Do not repeat content already covered in previous slides
- Each bullet must be a complete thought, not a sentence fragment
- Remove any citation artifacts like [1], [2], [31] from bullets"""


def _build_previous_context(results: list[SlideContent]) -> str:
    """Build a compact summary of slides already generated."""
    if not results:
        return "None — this is the first slide."
    lines = []
    for s in results:
        lines.append(f"  Slide {s.slide_id} '{s.title}': {s.takeaway}")
    return "\n".join(lines)


def _get_slide_evidence(slide, all_chunks: dict) -> str:
    """Gather evidence text for a slide from its evidence_ids."""
    texts = [
        all_chunks[eid].text
        for eid in slide.evidence_ids
        if eid in all_chunks
    ]
    return "\n\n".join(texts) if texts else (
        "No specific evidence assigned — write a coherent transition or summary slide."
    )


def generate_content(
    plan: SlidePlan,
    evidence: EvidencePack,
    audience: str = "technical",
    strategy: PresentationStrategy | None = None,
) -> list[SlideContent]:
    """
    S6 — Generate structured content for each slide.
    One LLM call per slide, with strategy coherence and dedup context.
    """
    max_retries = CONFIG["agent"]["max_content_retries"]

    all_chunks = {
        c.chunk_id[:8]: c
        for c in (evidence.sections + evidence.concepts + evidence.tables + evidence.figures)
    }

    core_message = (
        strategy.core_message if strategy
        else "Present the topic clearly and concisely."
    )

    results: list[SlideContent] = []

    for slide in plan.slides:
        slide_evidence    = _get_slide_evidence(slide, all_chunks)
        previous_context  = _build_previous_context(results)

        prompt = _PROMPT.format(
            slide_id=slide.slide_id,
            total_slides=plan.total,
            core_message=core_message,
            purpose=slide.purpose,
            audience=audience,
            previous_context=previous_context,
            slide_evidence=slide_evidence,
        )

        for attempt in range(1, max_retries + 1):
            raw    = call_llm(_SYSTEM, prompt)
            parsed = parse_json(raw)

            if parsed and "title" in parsed and "bullets" in parsed:
                # Strip citation artifacts from bullets
                import re
                clean_bullets = [
                    re.sub(r'\[\d+\]', '', b).strip()
                    for b in parsed["bullets"][:4]
                ]
                clean_bullets = [b for b in clean_bullets if b]  # remove empty

                results.append(SlideContent(
                    slide_id=parsed.get("slide_id", slide.slide_id),
                    title=parsed["title"],
                    bullets=clean_bullets,
                    takeaway=parsed.get("takeaway", ""),
                    speaker_notes=parsed.get("speaker_notes", ""),
                    visual_hint=parsed.get("visual_hint", "text-only"),
                ))
                log("content", f"Slide {slide.slide_id} ✓  '{parsed['title']}'")
                break

            else:
                log("content", f"Slide {slide.slide_id} invalid JSON, retry {attempt}")
                if attempt == max_retries:
                    results.append(SlideContent(
                        slide_id=slide.slide_id,
                        title=f"Slide {slide.slide_id}",
                        bullets=["Content generation failed — check evidence"],
                        takeaway="",
                        speaker_notes="",
                        visual_hint="text-only",
                    ))

    return results


if __name__ == "__main__":
    from src.query_compiler import compile_query
    from src.retrieval import retrieve
    from src.strategy import generate_strategy
    from src.planner import generate_slide_plan

    raw_query = (
        sys.argv[1] if len(sys.argv) > 1
        else "make a 10 slide technical presentation on the transformer architecture"
    )
    doc_id = sys.argv[2] if len(sys.argv) > 2 else "Attention_is_all_you_Need"

    request  = compile_query(raw_query)
    evidence = retrieve(request.topic, top_k=15, doc_id=doc_id)
    strategy = generate_strategy(request, evidence)
    plan     = generate_slide_plan(request, evidence, strategy=strategy)

    log("content", f"Generating content for {plan.total} slides...")
    slides = generate_content(plan, evidence, audience=request.audience, strategy=strategy)

    print(f"\n{'='*50}")
    print(f"SLIDE CONTENT — {len(slides)} slides")
    print(f"{'='*50}")
    for s in slides:
        print(f"\nSlide {s.slide_id}: {s.title}")
        for b in s.bullets:
            print(f"  • {b}")
        print(f"  ↳ {s.takeaway}")