import re
from src.models import PresentationRequest


def compile_query(raw: str) -> PresentationRequest:
    """
    Extract structured fields from a natural language query.
    Fills defaults for anything not found.
    """
    raw_lower = raw.lower()

    # --- slide count ---
    slide_count = 10
    match = re.search(r'(\d+)\s*slide', raw_lower)
    if match:
        slide_count = int(match.group(1))

    # --- audience ---
    audience = "technical"
    if any(w in raw_lower for w in ["executive", "ceo", "board", "investor"]):
        audience = "executive"
    elif any(w in raw_lower for w in ["beginner", "student", "intro", "101"]):
        audience = "beginner"
    elif any(w in raw_lower for w in ["technical", "engineer", "developer", "researcher"]):
        audience = "technical"

    # --- objective ---
    objective = "inform"
    if any(w in raw_lower for w in ["pitch", "sell", "convince", "invest"]):
        objective = "pitch"
    elif any(w in raw_lower for w in ["teach", "tutorial", "explain", "learn"]):
        objective = "teach"
    elif any(w in raw_lower for w in ["summarize", "summary", "overview"]):
        objective = "summarize"

    # --- style ---
    style_desc = "clean minimal"
    if any(w in raw_lower for w in ["dark"]):
        style_desc = "dark minimal"
    elif any(w in raw_lower for w in ["colorful", "vibrant", "creative"]):
        style_desc = "colorful creative"
    elif any(w in raw_lower for w in ["corporate", "formal", "professional"]):
        style_desc = "corporate formal"

# --- topic: strip constraint words, keep the core subject ---
    topic = raw
    for pattern in [
        r'\d+\s*slides?',
        r'\b(for\s+)?(executives?|beginners?|students?|engineers?|researchers?)\b',
        r'\b(dark|minimal|colorful|corporate|formal|vibrant|creative)\s*(theme)?\b',
        r'\b(create|make|generate|build)\s+(a\s+)?(presentation|deck|slides?)\b',
        r'\b(presentation|deck)\b',
        r'\bwith\s+(dark|light|minimal|colorful|corporate)\s*(theme)?\b',
    ]:
        topic = re.sub(pattern, '', topic, flags=re.IGNORECASE).strip()
    topic = re.sub(r'\s+', ' ', topic).strip() or raw
    req = PresentationRequest(
        topic=topic,
        audience=audience,
        slide_count=slide_count,
        style_desc=style_desc,
        objective=objective,
    )

    print(f"[query_compiler] Parsed request:")
    print(f"  topic      : {req.topic}")
    print(f"  audience   : {req.audience}")
    print(f"  slide_count: {req.slide_count}")
    print(f"  style_desc : {req.style_desc}")
    print(f"  objective  : {req.objective}")

    return req


if __name__ == "__main__":
    tests = [
        "make a 10 slide technical presentation on the transformer architecture",
        "create a 5 slide executive summary of the attention mechanism",
        "build a beginner tutorial on self-attention with dark theme",
    ]
    for t in tests:
        print(f"\nInput: {t}")
        compile_query(t)
