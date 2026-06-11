from src.models import PresentationRequest, EvidencePack, SlideIntent, SlidePlan
from src.utils import call_llm, parse_json, log, CONFIG
import sys 



def generate_slide_plan(request: PresentationRequest,evidence: EvidencePack) -> SlidePlan:
    max_retries = CONFIG["agent"]["max_plan_retries"]
    """
    S5 — LLM generates a SlidePlan from request + evidence.
    No content yet — only slide purpose and evidence mapping.
    """
    all_chunks = evidence.concepts + evidence.tables + evidence.figures + evidence.sections

    # Build evidence summary for the prompt
    evidence_text = "\n".join(
        f"[{c.chunk_id[:8]}] (page {c.page}) {c.text[:200]}"
        for c in all_chunks
    )

    system_prompt = """You are a presentation architect.
Your job is to create a slide plan — NOT slide content.
Each slide should have a clear purpose and reference which evidence chunks it will use.
Respond ONLY in valid JSON. No markdown fences, no preamble, no explanation."""

    user_prompt = f"""Create a {request.slide_count}-slide presentation plan.

Topic    : {request.topic}
Audience : {request.audience}
Objective: {request.objective}

Available evidence chunks:
{evidence_text}

Return a JSON object in exactly this format:
{{
  "slides": [
    {{
      "slide_id": 1,
      "purpose": "one sentence describing what this slide communicates",
      "evidence_ids": ["chunk_id_1", "chunk_id_2"]
    }}
  ]
}}

Rules:
- Exactly {request.slide_count} slides
- First slide is always the title/overview slide (evidence_ids can be empty)
- Last slide is always a conclusion/summary slide
- Each evidence_id must be one of the 8-character chunk IDs from the list above
- Do not generate any slide content — only purpose and evidence mapping"""

    for attempt in range(1, max_retries + 1):
        # Replaced print behavior with log call
        log("planner", f"Attempt {attempt}/{max_retries}...")
        
        # Replaced _call_llm with call_llm
        raw = call_llm(system_prompt, user_prompt)
        
        # Replaced _parse_json with parse_json
        parsed = parse_json(raw)

        if parsed is None:
            # Replaced print behavior with log call
            log("planner", f"Invalid JSON on attempt {attempt}, retrying...")
            continue

        slides_data = parsed.get("slides", [])

        # Validation gate — S5c
        if len(slides_data) == 0:
            log("planner", "No slides in response, retrying...")
            continue

        # Tolerance of ±1 slide
        if abs(len(slides_data) - request.slide_count) > 1:
            log("planner", f"Got {len(slides_data)} slides, expected {request.slide_count}, retrying...")
            continue

        # Build typed SlidePlan
        slides = []
        valid_ids = {c.chunk_id[:8] for c in all_chunks}
        for s in slides_data:
            # Filter out any hallucinated chunk IDs
            clean_ids = [eid for eid in s.get("evidence_ids", []) if eid in valid_ids]
            slides.append(SlideIntent(
                slide_id=s["slide_id"],
                purpose=s["purpose"],
                evidence_ids=clean_ids,
            ))

        plan = SlidePlan(slides=slides, total=len(slides))
        
        log("planner", f"Valid plan: {plan.total} slides")
        return plan

    # Max retries exceeded — return best partial plan
    # Replaced print behavior with log call
    log("planner", "Max retries exceeded, returning partial plan")
    return SlidePlan(slides=[], total=0)


if __name__ == "__main__":
    sys.path.insert(0, "src")
    from query_compiler import compile_query
    from retrieval import retrieve

    raw_query = (
        sys.argv[1] if len(sys.argv) > 1
        else "make a 10 slide technical presentation on the transformer architecture"
    )
    doc_id = sys.argv[2] if len(sys.argv) > 2 else "Attention_is_all_you_Need"

    log("planner", f"Query : {raw_query}")
    request  = compile_query(raw_query)
    evidence = retrieve(request.topic, top_k=15, doc_id=doc_id)

    all_chunks = evidence.sections + evidence.concepts + evidence.tables + evidence.figures
    log("planner", f"Evidence: {len(all_chunks)} chunks retrieved")

    plan = generate_slide_plan(request, evidence)

    print(f"\n{'='*50}")
    print(f"SLIDE PLAN — {plan.total} slides")
    print(f"{'='*50}")
    for slide in plan.slides:
        print(f"\nSlide {slide.slide_id}: {slide.purpose}")
        print(f"  Evidence: {slide.evidence_ids}")