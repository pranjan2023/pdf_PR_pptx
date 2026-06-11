from src.models import StyleConfig

STYLE_MAP = {
    "dark minimal": StyleConfig(
        template_name="dark_minimal",
        bg_color="#1a1a1a",
        title_font="Helvetica",
        body_font="Helvetica",
        accent_color="#4A90D9",
        max_bullets=3,
        bullet_max_words=12,
    ),
    "corporate formal": StyleConfig(
        template_name="corporate",
        bg_color="#ffffff",
        title_font="Calibri",
        body_font="Calibri",
        accent_color="#003087",
        max_bullets=5,
        bullet_max_words=15,
    ),
    "colorful creative": StyleConfig(
        template_name="vibrant",
        bg_color="#f5f5f5",
        title_font="Arial",
        body_font="Arial",
        accent_color="#E84393",
        max_bullets=4,
        bullet_max_words=12,
    ),
    "clean minimal": StyleConfig(
        template_name="default",
        bg_color="#ffffff",
        title_font="Arial",
        body_font="Arial",
        accent_color="#2E86AB",
        max_bullets=4,
        bullet_max_words=15,
    ),
}

DEFAULT_STYLE = STYLE_MAP["clean minimal"]


def resolve_style(style_desc: str) -> StyleConfig:
    style_desc = style_desc.lower().strip()
    # Exact match first
    if style_desc in STYLE_MAP:
        print(f"[style] Exact match '{style_desc}'")
        return STYLE_MAP[style_desc]
    # Then partial
    for key, config in STYLE_MAP.items():
        if all(word in style_desc for word in key.split()):
            print(f"[style] Resolved '{style_desc}' → '{key}'")
            return config
    print(f"[style] No match for '{style_desc}', using default")
    return DEFAULT_STYLE
