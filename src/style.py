import sys
from src.models import StyleConfig
from src.utils import call_llm, parse_json, log, CONFIG

_SYSTEM = """You are a Senior UI/UX Designer creating presentation themes.
Based on the user's descriptive prompt, generate a cohesive, highly readable color palette and typography rules.
Respond ONLY in valid JSON matching the requested schema."""

_PROMPT = """Create a visual theme based on this vibe: "{style_desc}"

Rules for the JSON Output:
1. "template_name": A 1-3 word name for this theme.
2. "bg_color": Hex code for the background.
3. "text_color": Hex code for the primary text. MUST have extremely high contrast with bg_color!
4. "accent_color": Hex code for charts, highlights, and big numbers.
5. "title_font" / "body_font": Choose ONLY from standard safe fonts (Helvetica, Arial, Calibri, Garamond, Trebuchet MS, Georgia).
6. "max_bullets": Integer between 2 and 6. If the vibe is 'minimal', choose a lower number.
7. "bullet_max_words": Integer between 6 and 18.

Return EXACTLY this JSON structure:
{{
  "template_name": "...",
  "bg_color": "#...",
  "text_color": "#...",
  "accent_color": "#...",
  "title_font": "...",
  "body_font": "...",
  "max_bullets": 4,
  "bullet_max_words": 12
}}"""

def _get_luminance(hex_color: str) -> float:
    """Calculates relative luminance to check visual contrast."""
    hex_color = hex_color.lstrip('#')
    try:
        rgb = tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return 0.5 # Fallback
    
    a = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722

def _check_contrast(bg_hex: str, text_hex: str) -> bool:
    """Checks if the contrast ratio meets basic readability standards."""
    lum1 = _get_luminance(bg_hex)
    lum2 = _get_luminance(text_hex)
    brightest = max(lum1, lum2)
    darkest = min(lum1, lum2)
    ratio = (brightest + 0.05) / (darkest + 0.05)
    return ratio >= 3.0  # 3.0 is minimum for large text

def resolve_style(style_desc: str, max_retries: int = 2) -> StyleConfig:
    """Generates a dynamic theme using an LLM, enforced by contrast rules."""
    
    # Fast fallback for empty/generic prompts
    if not style_desc or style_desc.lower() in ["default", "standard"]:
        log("style", "Using safe default theme.")
        return StyleConfig(
            template_name="Default Clean", bg_color="#FFFFFF", text_color="#222222", 
            accent_color="#0066CC", title_font="Helvetica", body_font="Helvetica", 
            max_bullets=4, bullet_max_words=12
        )

    prompt = _PROMPT.format(style_desc=style_desc)
    
    for attempt in range(1, max_retries + 1):
        log("style", f"Generating dynamic theme for '{style_desc}' (attempt {attempt})")
        raw = call_llm(_SYSTEM, prompt)
        parsed = parse_json(raw)
        
        if parsed:
            try:
                config = StyleConfig(**parsed)
                
                # DETERMINISTIC RULE: Enforce Contrast Readability
                if not _check_contrast(config.bg_color, config.text_color):
                    log("style", "Warning: Generated colors fail contrast check. Inverting text color.")
                    # Force white text for dark backgrounds, or black for light backgrounds
                    bg_lum = _get_luminance(config.bg_color)
                    config.text_color = "#FFFFFF" if bg_lum < 0.5 else "#111111"

                log("style", f"Successfully built theme: {config.template_name}")
                return config
            except Exception as e:
                log("style", f"Pydantic validation failed: {e}")

    log("style", "Max retries hit. Falling back to default.")
    return StyleConfig(
        template_name="Fallback Minimal", bg_color="#F8F9FA", text_color="#212529",
        accent_color="#0D6EFD", title_font="Arial", body_font="Arial",
        max_bullets=4, bullet_max_words=12
    )

if __name__ == "__main__":
    test_prompts = [
        "Cyberpunk 2077 neon hacker",
        "Vintage 1970s warm sepia",
        "Aggressive corporate banking firm"
    ]
    
    for tp in test_prompts:
        print(f"\n--- Testing Vibe: {tp} ---")
        config = resolve_style(tp)
        print(f"Template Name : {config.template_name}")
        print(f"Background    : {config.bg_color}")
        print(f"Text Color    : {config.text_color}")
        print(f"Accent Color  : {config.accent_color}")
        print(f"Density Rules : Max {config.max_bullets} bullets, {config.bullet_max_words} words per bullet")