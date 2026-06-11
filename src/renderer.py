import sys
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from src.models import SlideContent, StyleConfig


def hex_to_rgb(hex_color: str) -> RGBColor:
    h = hex_color.lstrip("#")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _add_slide(prs: Presentation, content: SlideContent, style: StyleConfig) -> None:
    layout = prs.slide_layouts[6]  # blank layout
    slide  = prs.slides.add_slide(layout)

    W = prs.slide_width
    H = prs.slide_height

    # Background
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = hex_to_rgb(style.bg_color)

    is_dark = style.bg_color.lower() in ("#1a1a1a", "#000000", "#111111")
    text_color = hex_to_rgb("#ffffff") if is_dark else hex_to_rgb("#1a1a1a")

    # Title bar accent
    from pptx.util import Emu
    accent = slide.shapes.add_shape(
        1,  # rectangle
        Inches(0), Inches(0),
        W, Inches(0.08),
    )

    # Title
    title_box = slide.shapes.add_textbox(
        Inches(0.4), Inches(0.3),
        Inches(9.0), Inches(1.4),
    )
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = content.title
    p.font.name = style.title_font
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = hex_to_rgb(style.accent_color)

    # Divider line
    from pptx.util import Pt as PtU
    line = slide.shapes.add_shape(
        1,
        Inches(0.4), Inches(1.35),
        Inches(9.0), Inches(0.02),
    )

    # ─── NEW: DYNAMIC LAYOUT APPLICATION ─────────────────────────────────
    
    # 1. Coordinate assignment (with fallback if layout is somehow missing)
    if content.layout:
        t_left   = Inches(content.layout.text_left)
        t_top    = Inches(content.layout.text_top)
        t_width  = Inches(content.layout.text_width)
        t_height = Inches(content.layout.text_height)
    else:
        t_left, t_top, t_width, t_height = Inches(0.5), Inches(1.9), Inches(8.8), Inches(4.2)

    # 2. Add Bullets Textbox
    bullets = content.bullets[:style.max_bullets]
    body_box = slide.shapes.add_textbox(t_left, t_top, t_width, t_height)
    tf = body_box.text_frame
    tf.word_wrap = True

    for i, bullet in enumerate(bullets):
        # Trim to max words
        words = bullet.split()
        if len(words) > style.bullet_max_words:
            bullet = " ".join(words[:style.bullet_max_words]) + "…"

        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = f"  {bullet}"
        p.font.name = style.body_font
        p.font.size = Pt(22)
        p.font.color.rgb = text_color
        p.space_before = Pt(14)

    # 3. Add Visual Placeholder (if flagged by S8/S10)
    if content.layout and content.layout.has_visual:
        v_left   = Inches(content.layout.visual_left)
        v_top    = Inches(content.layout.visual_top)
        v_width  = Inches(content.layout.visual_width)
        v_height = Inches(content.layout.visual_height)
        
        ph_box = slide.shapes.add_shape(
            1, # MSO_SHAPE.RECTANGLE
            v_left, v_top, v_width, v_height
        )
        
        # Style the placeholder appropriately for dark/light mode
        ph_box.fill.solid()
        ph_bg = "#222222" if is_dark else "#F0F0F0"
        ph_text_color = "#888888" if is_dark else "#777777"
        
        ph_box.fill.fore_color.rgb = hex_to_rgb(ph_bg)
        ph_box.line.color.rgb = hex_to_rgb(ph_text_color)
        
        # Add descriptive text to the placeholder
        tf_ph = ph_box.text_frame
        tf_ph.word_wrap = True
        p_ph = tf_ph.paragraphs[0]
        p_ph.text = f"[ Placeholder for {content.visual_hint.upper()} ]"
        p_ph.alignment = PP_ALIGN.CENTER
        p_ph.font.color.rgb = hex_to_rgb(ph_text_color)

    # ──────────────────────────────────────────────────────────────────────

    # Takeaway bar at bottom
    if content.takeaway:
        bar = slide.shapes.add_shape(
            1,
            Inches(0), Inches(6.6),
            W, Inches(0.9),
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = hex_to_rgb(style.accent_color)
        bar.line.fill.background()

        ta_box = slide.shapes.add_textbox(
            Inches(0.3), Inches(6.65),
            Inches(9.3), Inches(0.8),
        )
        tf = ta_box.text_frame
        p = tf.paragraphs[0]
        p.text = f"Key takeaway: {content.takeaway}"
        p.font.name = style.body_font
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = hex_to_rgb("#ffffff")

    # Speaker notes
    if content.speaker_notes:
        notes_slide = slide.notes_slide
        notes_slide.notes_text_frame.text = content.speaker_notes


def render_pptx(
    slides: list[SlideContent],
    style: StyleConfig,
    output_path: str = "./outputs/presentation.pptx",
) -> str:
    prs = Presentation()
    prs.slide_width  = Inches(10)
    prs.slide_height = Inches(7.5)

    for content in slides:
        _add_slide(prs, content, style)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(output_path)

    # Verify
    check = Presentation(output_path)
    assert len(check.slides) == len(slides), \
        f"Expected {len(slides)} slides, got {len(check.slides)}"

    import os
    size = os.path.getsize(output_path)
    assert size > 0, "Output file is empty"

    print(f"[renderer] Saved {len(slides)} slides → {output_path} ({size:,} bytes)")
    return output_path


if __name__ == "__main__":
    sys.path.insert(0, "src")
    from query_compiler import compile_query
    from retrieval import retrieve
    from planner import generate_slide_plan
    from content import generate_content
    from visual import plan_visuals
    from layout import plan_layout
    from style import resolve_style

    raw_query = (
        sys.argv[1] if len(sys.argv) > 1
        else "make a 10 slide technical presentation on the transformer architecture"
    )
    doc_id = sys.argv[2] if len(sys.argv) > 2 else "Attention_is_all_you_Need"

    request    = compile_query(raw_query)
    evidence   = retrieve(request.topic, top_k=15, doc_id=doc_id)
    plan       = generate_slide_plan(request, evidence)
    slides     = generate_content(plan, evidence, audience=request.audience)
    
    # Run the new nodes so standalone tests don't fail!
    slides     = plan_visuals(slides)
    slides     = plan_layout(slides)
    
    style      = resolve_style(request.style_desc)

    output     = render_pptx(slides, style)
    print(f"\n✅ Done — open {output} in Keynote or PowerPoint")