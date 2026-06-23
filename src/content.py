import sys
import re
from src.models import SlidePlan, EvidencePack, SlideContent, PresentationStrategy
from src.utils import call_llm, parse_json, log, CONFIG

_SYSTEM = """You are an expert presentation copywriter.
Generate structured slide content grounded in the provided evidence.
Adapt your JSON output schema to perfectly match the requested layout type.
Respond ONLY in valid JSON. No markdown fences, no preamble."""

_PROMPT = """Generate content for slide {slide_id} of {total_slides}.

Overall presentation core message: {core_message}

Slide purpose : {purpose}
Layout Type   : {layout_type}
Audience      : {audience}

Previously covered (do not repeat these):
{previous_context}

Evidence for this slide:
{slide_evidence}

Return JSON strictly matching this layout structure:
{expected_json}

Rules:
- Layout MUST match the structure provided above.
- Maximum 15 words per bullet/item. No paragraphs on the slide.
- visual_hint must be one of: chart, diagram, table, text-only, image.
- Ground content in evidence — do not invent facts.
- If evidence contains [IMAGE AVAILABLE: ...], set visual_hint to "image" and mention it in speaker_notes.
"""

# Dynamic schemas depending on what the Planner requested
_LAYOUT_SCHEMAS = {
    "Title": """{
  "title": "Main Presentation Title (max 8 words)",
  "bullets": ["Subtitle or Presenter Name"],
  "speaker_notes": "Opening remarks..."
}""",
    "Big-Message": """{
  "title": "Contextual Title",
  "big_message": "One massive, impactful statement or quote (max 15 words)",
  "takeaway": "Key message",
  "speaker_notes": "Detailed explanation..."
}""",
    "Two-Column": """{
  "title": "Comparison/Contrast Title",
  "left_column": ["Point A1", "Point A2"],
  "right_column": ["Point B1", "Point B2"],
  "takeaway": "Key message",
  "speaker_notes": "Explanation of the comparison..."
}""",
    "Assertion-Data": """{
  "title": "Core Assertion (e.g., 'Performance Increased by 50%')",
  "big_message": "Primary Metric or Stat",
  "bullets": ["Supporting detail 1", "Supporting detail 2"],
  "takeaway": "Key message",
  "speaker_notes": "Data analysis...",
  "visual_hint": "chart"
}""",
    "Standard-Bullets": """{
  "title": "Concise slide title",
  "bullets": ["Point 1", "Point 2", "Point 3"],
  "takeaway": "Key message",
  "speaker_notes": "Detailed remarks..."
}"""
}

def _build_previous_context(results: list[SlideContent], window: int = 4) -> str:
    if not results:
        return "None — this is the first slide."
    lines = []
    for s in results[-window:]:
        lines.append(f"  Slide {s.slide_id} '{s.title}': {s.takeaway}")
    return "\n".join(lines)

def _get_slide_evidence(slide, all_chunks: dict) -> str:
    texts = []
    for eid in slide.evidence_ids:
        if eid not in all_chunks:
            continue
        chunk = all_chunks[eid]
        if chunk.image_path:
            texts.append(f"[IMAGE AVAILABLE: {chunk.image_path}]\n{chunk.text}")
        else:
            texts.append(chunk.text)
    return "\n\n".join(texts) if texts else "No specific evidence assigned."

def _clean_citations(text_list: list[str]) -> list[str]:
    """Strips citation artifacts like [1], [ 2 ], [3, 4] from strings."""
    clean = [re.sub(r'\[\s*\d+(?:\s*,\s*\d+)*\s*\]', '', b).strip() for b in text_list]
    return [b for b in clean if b]

def generate_content(
    plan: SlidePlan,
    evidence: EvidencePack,
    audience: str = "technical",
    strategy: PresentationStrategy | None = None,
) -> list[SlideContent]:
    
    max_retries = CONFIG["agent"]["max_content_retries"]
    all_chunks = {c.chunk_id[:8]: c for c in (evidence.sections + evidence.concepts + evidence.tables + evidence.figures)}
    core_message = strategy.core_message if strategy else "Present the topic clearly."
    results: list[SlideContent] = []

    for slide in plan.slides:
        slide_evidence = _get_slide_evidence(slide, all_chunks)
        previous_context = _build_previous_context(results)
        
        # Fallback to standard if layout is unrecognized
        expected_json = _LAYOUT_SCHEMAS.get(getattr(slide, "layout_type", "Standard-Bullets"), _LAYOUT_SCHEMAS["Standard-Bullets"])

        prompt = _PROMPT.format(
            slide_id=slide.slide_id,
            total_slides=plan.total,
            core_message=core_message,
            purpose=slide.purpose,
            layout_type=getattr(slide, "layout_type", "Standard-Bullets"),
            audience=audience,
            previous_context=previous_context,
            slide_evidence=slide_evidence,
            expected_json=expected_json
        )

        for attempt in range(1, max_retries + 1):
            raw = call_llm(_SYSTEM, prompt)
            parsed = parse_json(raw)

            if parsed:
                try:
                    # Clean citations across all possible list fields
                    if "bullets" in parsed: parsed["bullets"] = _clean_citations(parsed["bullets"])
                    if "left_column" in parsed: parsed["left_column"] = _clean_citations(parsed["left_column"])
                    if "right_column" in parsed: parsed["right_column"] = _clean_citations(parsed["right_column"])
                    
                    # Ensure slide_id and layout_type are injected properly
                    parsed["slide_id"] = slide.slide_id
                    parsed["layout_type"] = getattr(slide, "layout_type", "Standard-Bullets")
                    parsed["original_intent"] = slide.purpose

                    content_obj = SlideContent(**parsed)
                    results.append(content_obj)
                    log("content", f"Slide {slide.slide_id} [{content_obj.layout_type}] ✓ '{content_obj.title}'")
                    break
                except Exception as e:
                    log("content", f"Slide {slide.slide_id} Pydantic failed: {e}. Retry {attempt}")
            else:
                log("content", f"Slide {slide.slide_id} invalid JSON, retry {attempt}")
            
            if attempt == max_retries:
                results.append(SlideContent(
                    slide_id=slide.slide_id,
                    title=f"Slide {slide.slide_id} Failed",
                    layout_type="Standard-Bullets",
                    bullets=["Content generation failed"],
                    original_intent=slide.purpose
                ))

    return results

if __name__ == "__main__":
    from src.query_compiler import compile_query
    from src.retrieval import retrieve
    from src.strategy import generate_strategy
    from src.planner import generate_slide_plan

    raw_query = sys.argv[1] if len(sys.argv) > 1 else "make a 5 slide presentation comparing RAG to standard models"
    doc_id = sys.argv[2] if len(sys.argv) > 2 else "Rag"

    request  = compile_query(raw_query)
    evidence = retrieve(request.topic, top_k=15, doc_id=doc_id)
    strategy = generate_strategy(request, evidence)
    plan     = generate_slide_plan(request, evidence, strategy=strategy)

    log("content", f"Generating content for {plan.total} slides...")
    slides = generate_content(plan, evidence, audience=request.audience, strategy=strategy)

    print(f"\n{'='*50}")
    print(f"DYNAMIC SLIDE CONTENT — {len(slides)} slides")
    print(f"{'='*50}")
    
    for s in slides:
        print(f"\nSlide {s.slide_id} [{s.layout_type}]: {s.title}")
        
        if s.layout_type == "Two-Column":
            print("  [LEFT COLUMN]")
            for b in s.left_column: print(f"    • {b}")
            print("  [RIGHT COLUMN]")
            for b in s.right_column: print(f"    • {b}")
            
        elif s.layout_type in ["Big-Message", "Assertion-Data"]:
            print(f"  ★ BIG MESSAGE: {s.big_message}")
            if s.bullets:
                print("  [SUPPORTING DATA]")
                for b in s.bullets: print(f"    • {b}")
                
        else: # Standard and Title
            for b in s.bullets:
                print(f"  • {b}")
                
        print(f"  ↳ {s.takeaway}")