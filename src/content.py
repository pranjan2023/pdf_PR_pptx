import sys
from src.models import SlidePlan, EvidencePack, SlideContent
from src.utils import call_llm, parse_json, log, CONFIG


def generate_content(plan: SlidePlan,evidence: EvidencePack,audience: str = "technical") -> list[SlideContent]:
    max_retries = CONFIG["agent"]["max_content_retries"]
    """
    S6 — Generate structured content for each slide.
    One LLM call per slide using only its assigned evidence chunks.
    """
    all_chunks = {
        c.chunk_id[:8]: c
        for c in (evidence.sections + evidence.concepts + evidence.tables + evidence.figures)
    }

    system_prompt = """You are a presentation content writer.
Generate structured slide content based on the provided evidence.
Write for the specified audience.
Respond ONLY in valid JSON. No markdown fences, no preamble."""

    results = []

    for slide in plan.slides:
        # Gather evidence text for this slide
        slide_evidence = "\n\n".join(
            all_chunks[eid].text
            for eid in slide.evidence_ids
            if eid in all_chunks
        ) or "No specific evidence — use general knowledge for this slide."

        user_prompt = f"""Generate content for slide {slide.slide_id}.

Purpose  : {slide.purpose}
Audience : {audience}
Evidence :
{slide_evidence}

Return JSON in exactly this format:
{{
  "slide_id": {slide.slide_id},
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
- Title slide (slide 1) gets 1 bullet maximum
- visual_hint must be one of: chart, diagram, table, text-only"""

        for attempt in range(1, max_retries + 1):
            # Replaced _call_llm with call_llm
            raw    = call_llm(system_prompt, user_prompt)
            # Replaced _parse_json with parse_json
            parsed = parse_json(raw)

            if parsed and "title" in parsed and "bullets" in parsed:
                results.append(SlideContent(
                    slide_id=parsed.get("slide_id", slide.slide_id),
                    title=parsed["title"],
                    bullets=parsed["bullets"][:4],   # enforce max 4
                    takeaway=parsed.get("takeaway", ""),
                    speaker_notes=parsed.get("speaker_notes", ""),
                    visual_hint=parsed.get("visual_hint", "text-only"),
                ))
                # Replaced print with log("content", ...)
                log("content", f"Slide {slide.slide_id} ✓  '{parsed['title']}'")
                break
            else:
                # Replaced print with log("content", ...)
                log("content", f"Slide {slide.slide_id} invalid JSON, retry {attempt}")
                if attempt == max_retries:
                    # Fallback placeholder
                    results.append(SlideContent(
                        slide_id=slide.slide_id,
                        title=f"Slide {slide.slide_id}",
                        bullets=["Content generation failed"],
                        takeaway="",
                        speaker_notes="",
                        visual_hint="text-only",
                    ))

    return results


if __name__ == "__main__":
    sys.path.insert(0, "src")
    from query_compiler import compile_query
    from retrieval import retrieve
    from planner import generate_slide_plan

    raw_query = (
        sys.argv[1] if len(sys.argv) > 1
        else "make a 10 slide technical presentation on the transformer architecture"
    )
    doc_id = sys.argv[2] if len(sys.argv) > 2 else "Attention_is_all_you_Need"

    request  = compile_query(raw_query)
    evidence = retrieve(request.topic, top_k=15, doc_id=doc_id)
    plan     = generate_slide_plan(request, evidence)

    # Replaced print with log("content", ...)
    log("content", f"Generating content for {plan.total} slides...\n")
    slides = generate_content(plan, evidence, audience=request.audience)

    print(f"\n{'='*50}")
    print(f"SLIDE CONTENT — {len(slides)} slides")
    print(f"{'='*50}")
    for s in slides:
        print(f"\nSlide {s.slide_id}: {s.title}")
        for b in s.bullets:
            print(f"  • {b}")
        print(f"  ↳ {s.takeaway}")