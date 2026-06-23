import json
from src.models import PresentationRequest
from src.utils import call_llm, parse_json, log


_SYSTEM = """You extract structured presentation requirements from natural language requests.
Return ONLY valid JSON. No markdown fences, no explanation, no preamble."""

_PROMPT = """Extract presentation requirements from this request:

"{raw}"

Return JSON in exactly this format:
{{
  "topic": "the core subject matter only — no action words like make/create/build",
  "audience": "technical" | "executive" | "beginner",
  "slide_count": <integer, default 10>,
  "style_desc": "<free text describing the visual style>",
  "objective": "inform" | "teach" | "pitch" | "summarize"
}}

Extraction Rules:
- topic: Extract only the subject (e.g., "make a deck on transformers" → "transformers").
- objective: Infer the goal. ("tutorial/explain" → teach, "summary" → summarize, "pitch/investor" → pitch, otherwise inform).
- slide_count: If explicitly stated, use that number. If not stated, infer based on objective (executive summary → 3-5, pitch deck → 10-12, deep tutorial → 15-20).
- audience: If not stated, deduce from topic/objective (e.g., "code review" → technical, "sales" → executive, "intro to" → beginner).
- style_desc: 
  * If the user mentions a visual style / vibe / theme (e.g., "dark theme", "neon", "corporate", "minimal", "vintage"), output that **exact phrase**.
  * If not mentioned, suggest a suitable style based on audience and topic (e.g., "dark minimal" for technical, "corporate formal" for executive, "colorful creative" for beginners).
  * Do NOT restrict to a fixed list.
"""


def compile_query(raw: str) -> PresentationRequest:
    """
    Use LLM to extract structured PresentationRequest from raw query.
    Falls back to safe defaults if LLM returns invalid JSON.
    """
    prompt = _PROMPT.format(raw=raw)

    for attempt in range(1, 3):
        try:
            raw_response = call_llm(_SYSTEM, prompt)
            parsed = parse_json(raw_response)

            if parsed and "topic" in parsed:
                # Validate and clamp values
                topic       = str(parsed.get("topic", raw)).strip() or raw
                audience    = parsed.get("audience", "technical")
                slide_count = int(parsed.get("slide_count", 10))
                style_desc  = parsed.get("style_desc", "clean minimal")
                objective   = parsed.get("objective", "inform")

                # Guard against out-of-range slide counts
                slide_count = max(3, min(slide_count, 30))

                # Guard against hallucinated enum values
                if audience not in ("technical", "executive", "beginner"):
                    audience = "technical"
                if objective not in ("inform", "teach", "pitch", "summarize"):
                    objective = "inform"
                if not style_desc or not isinstance(style_desc, str):
                    style_desc = "clean minimal"


                req = PresentationRequest(
                    topic=topic,
                    audience=audience,
                    slide_count=slide_count,
                    style_desc=style_desc,
                    objective=objective,
                )

                log("query_compiler", f"Parsed request:")
                log("query_compiler", f"  topic      : {req.topic}")
                log("query_compiler", f"  audience   : {req.audience}")
                log("query_compiler", f"  slide_count: {req.slide_count}")
                log("query_compiler", f"  style_desc : {req.style_desc}")
                log("query_compiler", f"  objective  : {req.objective}")
                return req

            log("query_compiler", f"Attempt {attempt}: invalid JSON, retrying...")

        except Exception as e:
            log("query_compiler", f"Attempt {attempt}: LLM error — {e}")

    # Fallback — safe defaults if LLM fails both attempts
    log("query_compiler", "WARNING: LLM failed, using raw query as topic with defaults")
    return PresentationRequest(
        topic=raw,
        audience="technical",
        slide_count=10,
        style_desc="clean minimal",
        objective="inform",
    )


if __name__ == "__main__":
    tests = [
        "make a 10 slide technical presentation on the transformer architecture",
        "create a 5 slide executive summary of the attention mechanism",
        "build a beginner tutorial on self-attention with dark theme",
        "pitch deck for investors on our new NLP product, 8 slides",
        "summarize the training section in 4 slides corporate style",
        "Multiple ways to design memory systems for deep learning,colorful creative",
    ]
    for t in tests:
        print(f"\nInput: {t}")
        req = compile_query(t)
        print()