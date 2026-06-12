from pydantic import BaseModel
from typing import TypedDict, Any


# ── Document Intelligence Models ──────────────────────────────────────

class FigureImage(BaseModel):
    path: str | None = None    # path to extracted PNG on disk
    caption: str
    page: int
    section: str


class TableData(BaseModel):
    markdown: str              # extracted table as markdown string
    page: int
    section: str
    image_path: str | None = None  # rendered table as image — future


class DocSection(BaseModel):
    heading: str
    text: str
    tables: list[str]              # backward compat — markdown strings
    table_data: list[TableData] = []   # structured table data — new
    figures: list[str]             # captions — backward compat
    figure_images: list[FigureImage] = []  # actual image refs — new
    page_range: tuple[int, int]


class DocTree(BaseModel):
    title: str
    sections: list[DocSection]
    format: str
    word_count: int


# ── Retrieval Models ──────────────────────────────────────────────────

class Chunk(BaseModel):
    chunk_id: str
    text: str
    section: str
    page: int
    type: str
    image_path: str | None = None  # for figure/table image chunks


class EvidencePack(BaseModel):
    concepts: list[Chunk]
    tables: list[Chunk]
    figures: list[Chunk]
    sections: list[Chunk]


# ── Presentation Request Models ───────────────────────────────────────

class PresentationRequest(BaseModel):
    topic: str
    audience: str = "technical"
    slide_count: int = 10
    style_desc: str = "clean minimal"
    scope: str | None = None
    objective: str = "inform"


class PresentationStrategy(BaseModel):
    core_message: str
    audience_adaptation: str
    recommended_sections: list[str]


# ── Slide Planning Models ─────────────────────────────────────────────

class SlideIntent(BaseModel):
    slide_id: int
    purpose: str
    evidence_ids: list[str]


class SlidePlan(BaseModel):
    slides: list[SlideIntent]
    total: int


# ── Slide Content Models ──────────────────────────────────────────────

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
    visual_hint: str = "text-only"  # "text-only" | "image" | "diagram" | "chart" | "table"
    image_path: str | None = None   # path to figure/table image for renderer
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
    type: str                       # "chart" | "diagram" | "table" | "text-only" | "image"
    data_ref: str | None = None
    caption: str | None = None
    image_path: str | None = None   # resolved path for renderer


# ── Agent State ───────────────────────────────────────────────────────

class AgentState(TypedDict):
    # inputs
    raw_query:         str
    doc_id:            str
    # compiled
    request:           Any   # PresentationRequest
    # retrieval
    evidence:          Any   # EvidencePack
    # S4 strategy
    strategy:          Any   # PresentationStrategy | None
    strategy_grade:    str
    strategy_reason:   str
    strategy_attempts: int
    # S5 planning
    plan:              Any   # SlidePlan
    plan_grade:        str
    plan_reason:       str
    plan_attempts:     int
    # generation
    slides:            Any   # list[SlideContent]
    # style + output
    style:             Any   # StyleConfig
    output_path:       str