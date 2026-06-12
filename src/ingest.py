import sys
import pymupdf
from pathlib import Path
from collections import Counter
import re


_HEADING_NUMBER_RE = re.compile(
    r'^(\d+\.?$'
    r'|\d+\.\d+\.?\s'
    r'|\d+\.\d+\.\d+\.?\s'
    r'|Abstract|References|Conclusion|Introduction'
    r'|Acknowledgements?|Appendix|Bibliography)',
    re.IGNORECASE
)


def get_body_font_size(doc: pymupdf.Document) -> float:
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


def _find_caption(blocks: list, img_bbox: tuple) -> str:
    """Find caption text in the block immediately below an image bbox."""
    img_bottom = img_bbox[3]
    for block in blocks:
        if block["type"] != 0:
            continue
        if 0 <= block["bbox"][1] - img_bottom <= 50:
            cap = " ".join(
                s["text"]
                for l in block["lines"]
                for s in l["spans"]
            ).strip()
            if cap:
                return cap
    return ""


def extract_page_tables(page: pymupdf.Page, page_num: int, section: str = "") -> tuple[list[str], list]:
    """
    Extract tables as both markdown strings (backward compat)
    and structured TableData objects.
    Returns (list[str], list[TableData])
    """
    try:
        from src.models import TableData
    except ImportError:
        from models import TableData

    markdown_list = []
    table_data_list = []

    try:
        for tab in page.find_tables().tables:
            md = tab.to_markdown()
            if not md.strip():
                continue
            markdown_list.append(f"[Table, page {page_num}]\n{md}")
            table_data_list.append(TableData(
                markdown=md,
                page=page_num,
                section=section,
            ))
    except Exception:
        pass

    return markdown_list, table_data_list


def extract_page_figures(
    page: pymupdf.Page,
    doc: pymupdf.Document,
    page_num: int,
    section: str = "",
    figures_dir: Path | None = None,
) -> tuple[list[str], list]:
    """
    Extract figures as both caption strings (backward compat)
    and FigureImage objects with actual image bytes saved to disk.
    Returns (list[str], list[FigureImage])
    """
    try:
        from src.models import FigureImage
    except ImportError:
        from models import FigureImage

    blocks      = page.get_text("dict")["blocks"]
    caption_list  = []
    figure_image_list = []

    # Map xref → bbox for caption lookup
    image_blocks = {b["number"]: b for b in blocks if b["type"] == 1}

    for img_idx, img in enumerate(page.get_images(full=True)):
        xref = img[0]

        # Find caption — use image block bbox if available
        img_block = image_blocks.get(xref)
        img_bbox  = img_block["bbox"] if img_block else (0, 0, 0, 0)
        caption   = _find_caption(blocks, img_bbox)

        # Caption string (backward compat)
        entry = f"[Figure, page {page_num}]"
        if caption:
            entry += f" Caption: {caption}"
        caption_list.append(entry)

        # Extract image bytes and save to disk
        img_path = None
        if figures_dir is not None:
            try:
                base_image   = doc.extract_image(xref)
                image_bytes  = base_image["image"]
                ext          = base_image["ext"]
                img_filename = f"fig_p{page_num}_{img_idx}.{ext}"
                img_file     = figures_dir / img_filename
                img_file.write_bytes(image_bytes)
                img_path = str(img_file)
            except Exception as e:
                print(f"[ingest] Image extraction failed p{page_num}/{img_idx}: {e}")

        figure_image_list.append(FigureImage(
            path=img_path,
            caption=caption,
            page=page_num,
            section=section,
        ))

    return caption_list, figure_image_list


def ingest_pdf(pdf_path: str, doc_id: str | None = None):
    """
    Parse a PDF into a semantic DocTree.
    Sections follow document headings, not page breaks.
    Tables extracted as markdown + TableData.
    Figures extracted as captions + FigureImage (with image bytes saved to disk).
    """
    try:
        from src.models import DocSection, DocTree
    except ImportError:
        from models import DocSection, DocTree

    path   = Path(pdf_path)
    doc_id = doc_id or path.stem

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected .pdf, got: {path.suffix}")

    # Create figures output directory
    figures_dir = Path(f"./data/figures/{doc_id}")
    figures_dir.mkdir(parents=True, exist_ok=True)

    doc       = pymupdf.open(str(path))
    body_font = get_body_font_size(doc)
    print(f"[ingest] Body font: {body_font}pt")

    # Pre-extract tables and figures per page
    page_tables       = {}   # pn → list[str]
    page_table_data   = {}   # pn → list[TableData]
    page_figures      = {}   # pn → list[str]
    page_figure_images = {}  # pn → list[FigureImage]

    for page_num, page in enumerate(doc):
        pn = page_num + 1
        md_list, td_list = extract_page_tables(page, pn)
        cap_list, fi_list = extract_page_figures(page, doc, pn, figures_dir=figures_dir)

        page_tables[pn]        = md_list
        page_table_data[pn]    = td_list
        page_figures[pn]       = cap_list
        page_figure_images[pn] = fi_list

    # Walk blocks, split on headings
    sections         = []
    current_heading  = None
    current_text     = []
    current_start_pg = 1
    current_end_pg   = 1

    for page_num, page in enumerate(doc):
        pn     = page_num + 1
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

            if is_heading(block_text, max_font, body_font, is_bold=has_bold):
                if current_heading is not None:
                    body = " ".join(current_text).strip()
                    tbls, tds, figs, fis = [], [], [], []
                    for p in range(current_start_pg, current_end_pg + 1):
                        tbls.extend(page_tables.get(p, []))
                        tds.extend(page_table_data.get(p, []))
                        figs.extend(page_figures.get(p, []))
                        fis.extend(page_figure_images.get(p, []))

                    # Update section name on TableData and FigureImage
                    for td in tds:
                        td.section = current_heading
                    for fi in fis:
                        fi.section = current_heading

                    sections.append(DocSection(
                        heading=current_heading,
                        text=body,
                        tables=tbls,
                        table_data=tds,
                        figures=figs,
                        figure_images=fis,
                        page_range=(current_start_pg, current_end_pg),
                    ))

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
        tbls, tds, figs, fis = [], [], [], []
        for p in range(current_start_pg, current_end_pg + 1):
            tbls.extend(page_tables.get(p, []))
            tds.extend(page_table_data.get(p, []))
            figs.extend(page_figures.get(p, []))
            fis.extend(page_figure_images.get(p, []))
        for td in tds:
            td.section = current_heading
        for fi in fis:
            fi.section = current_heading
        sections.append(DocSection(
            heading=current_heading,
            text=body,
            tables=tbls,
            table_data=tds,
            figures=figs,
            figure_images=fis,
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
                    tables=[], table_data=[],
                    figures=[], figure_images=[],
                    page_range=(page_num + 1, page_num + 1),
                ))

    title = doc.metadata.get("title", "").strip() or (
        sections[0].heading if sections else path.stem
    )
    word_count = sum(len(s.text.split()) for s in sections)
    doc.close()

    print(f"[ingest] {len(sections)} sections, {word_count} words")

    # Summary of extracted assets
    total_tables  = sum(len(s.table_data) for s in sections)
    total_figures = sum(len(s.figure_images) for s in sections)
    saved_images  = sum(1 for s in sections for fi in s.figure_images if fi.path)
    print(f"[ingest] {total_tables} tables, {total_figures} figures ({saved_images} images saved to {figures_dir})")

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
        tbls = f"  [{len(s.table_data)}T]" if s.table_data else ""
        figs = f"  [{len(s.figure_images)}F]" if s.figure_images else ""
        saved = sum(1 for fi in s.figure_images if fi.path)
        img_saved = f"  ({saved} saved)" if saved else ""
        print(f"  {i+1:02d} | pp.{s.page_range[0]}-{s.page_range[1]} | "
              f"{s.heading[:50]:<50} | {len(s.text):>5} chars{tbls}{figs}{img_saved}")

    # Show first figure with saved path
    for s in tree.sections:
        for fi in s.figure_images:
            if fi.path:
                print(f"\nFirst saved figure:")
                print(f"  Section : {fi.section}")
                print(f"  Caption : {fi.caption}")
                print(f"  Path    : {fi.path}")
                break
        else:
            continue
        break

    # Show first table
    for s in tree.sections:
        if s.table_data:
            print(f"\nFirst table (section: {s.heading}):")
            print(s.table_data[0].markdown[:300])
            break