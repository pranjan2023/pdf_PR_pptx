from pydantic import BaseModel
from typing import TypedDict, Any



class FigureImage(BaseModel):
    path: str | None = None    # None until Phase 3
    caption: str
    page: int
    section: str

class DocSection(BaseModel):
    heading: str
    text: str
    tables: list[str]
    figures: list[str]
    figure_images: list[FigureImage] = []   # Phase 3
    page_range: tuple[int, int]

class DocTree(BaseModel):
    title: str
    sections: list[DocSection]
    format: str
    word_count: int

class Chunk(BaseModel):
    chunk_id: str
    text: str
    section: str
    page: int
    type: str

class EvidencePack(BaseModel):
    concepts: list[Chunk]
    tables: list[Chunk]
    figures: list[Chunk]
    sections: list[Chunk]

class PresentationRequest(BaseModel):
    topic: str
    audience: str = "technical"
    slide_count: int = 10
    style_desc: str = "clean minimal"
    scope: str | None = None
    objective: str = "inform"

class SlideIntent(BaseModel):
    slide_id: int
    purpose: str
    evidence_ids: list[str]

class SlidePlan(BaseModel):
    slides: list[SlideIntent]
    total: int

class LayoutSpec(BaseModel):
    text_left: float
    text_top: float
    text_width: float
    text_height: float
    has_visual: bool = False
    visual_left: float | None = None
    visual_top: float | None = None
    visual_width: float | None = None
    visual_height: float | None = None

class SlideContent(BaseModel):
    slide_id: int
    title: str
    bullets: list[str]
    takeaway: str
    speaker_notes: str
    visual_hint: str = "text-only"
    layout: LayoutSpec | None = None

class StyleConfig(BaseModel):
    template_name: str
    bg_color: str
    title_font: str
    body_font: str
    accent_color: str
    max_bullets: int
    bullet_max_words: int

class VisualSpec(BaseModel):
    slide_id: int
    type: str                    # "chart" | "diagram" | "table" | "text-only"
    data_ref: str | None = None
    caption: str | None = None

class AgentState(TypedDict):
    # inputs
    raw_query:         str
    doc_id:            str
    # compiled
    request:           Any   # PresentationRequest
    # retrieval
    evidence:          Any   # EvidencePack
    # ── NEW: S4 Strategy State ──
    strategy:          str | None
    strategy_grade:    str   # "good" | "retry"
    strategy_reason:   str
    strategy_attempts: int
    # ── UPDATED: S5 Planning State ──
    plan:              Any   # SlidePlan
    plan_grade:        str   # "good" | "retry"
    plan_reason:       str
    plan_attempts:     int   # Renamed from 'attempts' to prevent collision
    # generation
    slides:            Any   # list[SlideContent]
    # style + output
    style:             Any   # StyleConfig
    output_path:       str

class PresentationStrategy(BaseModel):
    core_message: str
    audience_adaptation: str
    recommended_sections: list[str]