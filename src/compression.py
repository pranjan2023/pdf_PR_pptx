from src.models import SlideContent
from src.utils import call_llm, parse_json, log

def compress_content(slides: list[SlideContent]) -> list[SlideContent]:
    """
    S7: Compression.
    Trims verbose bullets into concise, punchy presentation points.
    """
    log("compression", f"S7 — compressing {len(slides)} slides")
    
    system_prompt = (
        "You are an expert editor for executive presentations. "
        "Compress the provided bullet points into extremely concise, impactful statements. "
        "Remove filler words. Keep bullets under 10 words each. "
        "Return ONLY valid JSON matching this schema: {'bullets': ['str', 'str']}"
    )
    
    for slide in slides:
        # Skip if no bullets to compress
        if not slide.bullets:
            continue
            
        user_prompt = f"Title: {slide.title}\nBullets: {str(slide.bullets)}"
        
        response_text = call_llm(system_prompt, user_prompt)
        compressed = parse_json(response_text)
        
        if compressed and "bullets" in compressed:
            slide.bullets = compressed["bullets"]
            
    return slides