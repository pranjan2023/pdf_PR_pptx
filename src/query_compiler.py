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
  "style_desc": "dark minimal" | "corporate formal" | "colorful creative" | "clean minimal",
  "objective": "inform" | "teach" | "pitch" | "summarize"
}}

Rules:
- topic: extract only the subject. "make a presentation on transformers" → "transformers"
- audience: infer from context. "for engineers" → technical, "for investors" → executive
- slide_count: extract number if mentioned, else 10
- style_desc: infer from keywords. "dark", "minimal" → "dark minimal". Default: "clean minimal"
- objective: infer from explicit words only. 
  "tutorial", "teach", "learn", "explain" → teach
  "summary", "summarize", "overview" → summarize  
  "pitch", "sell", "convince", "investor" → pitch
  "presentation", "slides" with no other signal → inform (default)
  When in doubt, use "inform"
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
                if style_desc not in ("dark minimal", "corporate formal",
                                      "colorful creative", "clean minimal"):
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
    ]
    for t in tests:
        print(f"\nInput: {t}")
        req = compile_query(t)
        print()