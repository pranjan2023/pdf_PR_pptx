import sys
from src.models import SlideContent, LayoutSpec, BoundingBox
from src.utils import log

def plan_layout(slides: list[SlideContent]) -> list[SlideContent]:
    """
    S10: Deterministic Layout Planner.
    Converts polymorphic layout types and visual hints into exact X, Y, W, H coordinates (in inches).
    Standard slide is 10 x 7.5 inches.
    """
    log("layout", f"S10 — calculating slide layouts for {len(slides)} slides")
    
    # Universal Title Box for most slides
    standard_title = BoundingBox(left=0.5, top=0.5, width=9.0, height=1.0)
    
    for slide in slides:
        hint = getattr(slide, "visual_hint", "text-only")
        l_type = getattr(slide, "layout_type", "Standard-Bullets")
        has_vis = hint in ["chart", "image"]

        # Base spec starts with a title and assumes no visual
        spec = LayoutSpec(has_visual=has_vis, title_box=standard_title)
        
        # --- 1. TITLE SLIDE ---
        if l_type == "Title":
            spec.title_box = BoundingBox(left=1.0, top=2.5, width=8.0, height=1.5)
            spec.body_box = BoundingBox(left=1.0, top=4.0, width=8.0, height=1.0) # Used for subtitle
            
        # --- 2. TWO COLUMN LAYOUT ---
        elif l_type == "Two-Column":
            if has_vis:
                # If there's a visual, the right column becomes the visual box
                spec.left_box = BoundingBox(left=0.5, top=1.8, width=4.25, height=5.0)
                spec.visual_box = BoundingBox(left=5.25, top=1.8, width=4.25, height=5.0)
            else:
                # Standard two text columns
                spec.left_box = BoundingBox(left=0.5, top=1.8, width=4.25, height=5.0)
                spec.right_box = BoundingBox(left=5.25, top=1.8, width=4.25, height=5.0)
                
        # --- 3. ASSERTION / DATA LAYOUT ---
        elif l_type == "Assertion-Data":
            if has_vis:
                # Squish text to the left, visual on the right
                spec.big_message_box = BoundingBox(left=0.5, top=1.8, width=4.25, height=2.0)
                spec.body_box = BoundingBox(left=0.5, top=4.0, width=4.25, height=3.0)
                spec.visual_box = BoundingBox(left=5.25, top=1.8, width=4.25, height=5.0)
            else:
                # Text spans full width
                spec.big_message_box = BoundingBox(left=0.5, top=1.8, width=9.0, height=2.0)
                spec.body_box = BoundingBox(left=0.5, top=4.0, width=9.0, height=3.0)
                
        # --- 4. BIG MESSAGE LAYOUT ---
        elif l_type == "Big-Message":
            # Remove title box, dead center the big message
            spec.title_box = None 
            spec.big_message_box = BoundingBox(left=1.0, top=2.5, width=8.0, height=2.5)
            
        # --- 5. STANDARD BULLETS ---
        else: 
            if has_vis:
                spec.body_box = BoundingBox(left=0.5, top=1.8, width=4.25, height=5.0)
                spec.visual_box = BoundingBox(left=5.25, top=1.8, width=4.25, height=5.0)
            else:
                spec.body_box = BoundingBox(left=0.5, top=1.8, width=9.0, height=5.0)

        # Attach the calculated layout to the slide object
        slide.layout = spec

    return slides