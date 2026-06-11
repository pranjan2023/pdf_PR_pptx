from src.models import SlideContent
from src.utils import call_llm, parse_json, log

def plan_visuals(slides: list[SlideContent]) -> list[SlideContent]:
    """
    S8: Analyzes slide content and assigns a layout hint (text, diagram, table, chart).
    """
    log("visual", "S8 — assigning visual hints to slides")
    
    system_prompt = (
        "You are an expert presentation designer. Determine the best visual format "
        "for the provided slide content. "
        "Choose EXACTLY ONE of these tags: ['text-only', 'diagram', 'table', 'chart'].\n"
        "Return ONLY valid JSON matching this schema: {'hint': 'str'}"
    )
    
    for slide in slides:
        user_prompt = (
            f"Title: {slide.title}\n"
            f"Bullets: {slide.bullets}\n"
            f"Takeaway: {slide.takeaway}"
        )
        
        response_text = call_llm(system_prompt, user_prompt)
        hint_dict = parse_json(response_text)
        
        # Validate and assign the hint, fallback to text-only if confused
        valid_hints = ['text-only', 'diagram', 'table', 'chart']
        if hint_dict and "hint" in hint_dict and hint_dict["hint"] in valid_hints:
            slide.visual_hint = hint_dict["hint"]
        else:
            slide.visual_hint = "text-only"
            
        # 👇 NEW: Log the decision so we can see it in the terminal!
        log("visual", f"Slide {slide.slide_id} tagged as: '{slide.visual_hint}'")
            
    return slides