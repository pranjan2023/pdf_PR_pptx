from src.models import SlideContent, LayoutSpec
from src.utils import log

def plan_layout(slides: list[SlideContent]) -> list[SlideContent]:
    """
    S10: Deterministic Layout Planner.
    Converts visual hints into exact X, Y, W, H coordinates (in inches).
    Standard slide is 10 x 7.5 inches.
    """
    log("layout", "S10 — calculating slide layouts")
    
    for slide in slides:
        hint = getattr(slide, "visual_hint", "text-only")
        
        if hint == "text-only":
            # Full width text box
            slide.layout = LayoutSpec(
                text_left=0.5, text_top=1.5, text_width=9.0, text_height=5.0,
                has_visual=False
            )
        else:
            # Split screen: Text on left, Visual on right
            slide.layout = LayoutSpec(
                text_left=0.5, text_top=1.5, text_width=4.0, text_height=5.0,
                has_visual=True,
                visual_left=5.0, visual_top=1.5, visual_width=4.5, visual_height=5.0
            )
            
    return slides