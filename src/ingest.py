import sys
import pymupdf
from pathlib import Path
from collections import Counter
import re


_HEADING_NUMBER_RE = re.compile(
    r'^(\d+\.?$'              # "3" or "3."
    r'|\d+\.\d+\.?\s'        # "3.2 " or "3.2. "
    r'|\d+\.\d+\.\d+\.?\s'   # "3.2.1 "
    r'|Abstract|References|Conclusion|Introduction'
    r'|Acknowledgements?|Appendix|Bibliography)',
    re.IGNORECASE
)

def get_body_font_size(doc: pymupdf.Document) -> float:
    """Body font = most frequent font size across the whole document."""
    sizes = []
    for page in doc:
        for b in page.get_text("dict")["blocks"]:
            if "lines" not in b:
                continue
            for l in b["lines"]:
                for s in l["spans"]:
                    if s["size"] > 6:
                        sizes.append(round(s["size"], 1))
    if not sizes:
        return 11.0
    return Counter(sizes).most_common(1)[0][0]


def is_heading(text: str, max_font: float, body_font: float, is_bold: bool = False) -> bool:
    text = text.strip()
    words = text.split()

    if not text or len(words) > 12:
        return False
    if not any(c.isalpha() for c in text):
        return False
    if text.lower().startswith("figure") or text.lower().startswith("table"):
        return False
    if _HEADING_NUMBER_RE.match(text):
        return True
    if text.endswith("."):
        return False
    if text.replace(".", "").replace(" ", "").isdigit():
        return False
    
    ratio = max_font / body_font if body_font > 0 else 1.0
    if ratio >= 1.3:
        return True
    if ratio >= 1.15 and is_bold:
        return True

    return False


def extract_page_tables(page: pymupdf.Page, page_num: int) -> list[str]:
    """Extract tables as markdown strings."""
    tables = []
    try:
        for tab in page.find_tables().tables:
            md = tab.to_markdown()
            if md.strip():
                tables.append(f"[Table, page {page_num}]\n{md}")
    except Exception:
        pass
    return tables


def extract_page_figures(page: pymupdf.Page, page_num: int) -> list[str]:
    """Detect image blocks and extract nearby caption text."""
    figures = []
    blocks = page.get_text("dict")["blocks"]

    for i, block in enumerate(blocks):
        if block["type"] != 1:
            continue
        img_bottom = block["bbox"][3]
        caption = ""
        for other in blocks:
            if other["type"] != 0:
                continue
            if 0 <= other["bbox"][1] - img_bottom <= 40:
                cap = " ".join(
                    s["text"]
                    for l in other["lines"]
                    for s in l["spans"]
                ).strip()
                if cap:
                    caption = cap
                    break
        entry = f"[Figure, page {page_num}]"
        if caption:
            entry += f" Caption: {caption}"
        figures.append(entry)

    return figures


def ingest_pdf(pdf_path: str):
    try:
        from src.models import DocSection, DocTree
    except ImportError:
        from models import DocSection, DocTree

    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected .pdf, got: {path.suffix}")

    doc = pymupdf.open(str(path))

    # Stage 1 — document-wide body font detection
    body_font = get_body_font_size(doc)
    print(f"[ingest] Body font: {body_font}pt")

    # Stage 2 — pre-extract tables and figures per page
    page_tables  = {}
    page_figures = {}
    for page_num, page in enumerate(doc):
        pn = page_num + 1
        page_tables[pn]  = extract_page_tables(page, pn)
        page_figures[pn] = extract_page_figures(page, pn)

    # Stage 3 — walk blocks, split on headings
    sections = []
    current_heading  = None
    current_text     = []
    current_start_pg = 1
    current_end_pg   = 1

    for page_num, page in enumerate(doc):
        pn = page_num + 1
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if "lines" not in block:
                continue

            block_text = ""
            max_font   = 0.0
            has_bold   = False
            for line in block["lines"]:
                for span in line["spans"]:
                    block_text += span["text"] + " "
                    if span["size"] > max_font:
                        max_font = span["size"]
                    if span["flags"] & 2**4:
                        has_bold = True

            block_text = block_text.strip()
            if not block_text:
                continue

            if is_heading(block_text, max_font, body_font,is_bold=has_bold):
                # Close current section
                if current_heading is not None:
                    body = " ".join(current_text).strip()

                    # Attach tables + figures from pages this section spans
                    tbls = []
                    figs = []
                    for p in range(current_start_pg, current_end_pg + 1):
                        tbls.extend(page_tables.get(p, []))
                        figs.extend(page_figures.get(p, []))

                    sections.append(DocSection(
                        heading=current_heading,
                        text=body,
                        tables=tbls,
                        figures=figs,
                        page_range=(current_start_pg, current_end_pg),
                    ))

                # Start new section
                current_heading  = block_text
                current_text     = []
                current_start_pg = pn
                current_end_pg   = pn

            else:
                if current_heading is None:
                    current_heading  = "Preamble"
                    current_start_pg = pn
                    current_end_pg   = pn
                current_text.append(block_text)
                current_end_pg = pn

    # Flush last section
    if current_heading is not None:
        body = " ".join(current_text).strip()
        tbls = []
        figs = []
        for p in range(current_start_pg, current_end_pg + 1):
            tbls.extend(page_tables.get(p, []))
            figs.extend(page_figures.get(p, []))
        sections.append(DocSection(
            heading=current_heading,
            text=body,
            tables=tbls,
            figures=figs,
            page_range=(current_start_pg, current_end_pg),
        ))

    # Validation gate
    if not sections:
        print("[WARNING] No sections found, falling back to page-level")
        for page_num, page in enumerate(doc):
            text = page.get_text().strip()
            if text:
                sections.append(DocSection(
                    heading=f"Page {page_num + 1}",
                    text=text,
                    tables=[], figures=[],
                    page_range=(page_num + 1, page_num + 1),
                ))

    # Title
    title = doc.metadata.get("title", "").strip() or (
        sections[0].heading if sections else path.stem
    )

    word_count = sum(len(s.text.split()) for s in sections)
    doc.close()

    print(f"[ingest] {len(sections)} sections, {word_count} words")
    return DocTree(
        title=title,
        sections=sections,
        format="semantic",
        word_count=word_count,
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.ingest <path_to_pdf>")
        sys.exit(1)

    tree = ingest_pdf(sys.argv[1])

    print(f"\n--- Document Structure: {tree.title} ---")
    print(f"Sections : {len(tree.sections)}")
    print(f"Words    : {tree.word_count}")
    print(f"\nHierarchy:")
    for i, s in enumerate(tree.sections):
        tbls = f"  [{len(s.tables)}T]" if s.tables else ""
        figs = f"  [{len(s.figures)}F]" if s.figures else ""
        print(f"  {i+1:02d} | pp.{s.page_range[0]}-{s.page_range[1]} | "
              f"{s.heading[:50]:<50} | {len(s.text):>5} chars{tbls}{figs}")

    print(f"\nFirst section body preview:")
    print(tree.sections[1].text[:400] if len(tree.sections) > 1 else tree.sections[0].text[:400])