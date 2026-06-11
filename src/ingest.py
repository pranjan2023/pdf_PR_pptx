import sys
import pymupdf
from pathlib import Path
from src.models import DocSection, DocTree


def extract_title(doc: pymupdf.Document, pdf_path: str) -> str:
    """
    Try to extract title from PDF metadata first.
    Fall back to first non-empty text line on page 1.
    Fall back to filename.
    """
    meta_title = doc.metadata.get("title", "").strip()
    if meta_title:
        return meta_title

    first_page = doc[0]
    blocks = first_page.get_text("blocks")  # list of (x0,y0,x1,y1,text,...)
    for block in blocks:
        line = block[4].strip()
        if line:
            # take first line only, cap at 120 chars
            return line.split("\n")[0][:120]

    return Path(pdf_path).stem  # filename without extension as last resort


def ingest_pdf(pdf_path: str) -> DocTree:
    """
    Parse a PDF into a DocTree.
    One DocSection per page (MVP approach).
    Validates that at least one section was extracted.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.suffix}")

    doc = pymupdf.open(str(path))
    sections = []

    for page_num, page in enumerate(doc):
        text = page.get_text().strip()
        if not text:
            continue  # skip blank / image-only pages
        sections.append(
            DocSection(
                heading=f"Page {page_num + 1}",
                text=text,
                tables=[],
                figures=[],
                page_range=(page_num + 1, page_num + 1),
            )
        )

    # Validation gate — PRD S1
    if not sections:
        print(
            "[WARNING] No text extracted from PDF. "
            "Document may be scanned or image-only. "
            "Falling back to single empty section."
        )
        sections = [
            DocSection(
                heading="Page 1",
                text="[No extractable text — possible scanned PDF]",
                tables=[],
                figures=[],
                page_range=(1, 1),
            )
        ]

    title = extract_title(doc, str(path))
    word_count = sum(len(s.text.split()) for s in sections)

    doctree = DocTree(
        title=title,
        sections=sections,
        format="text-heavy",
        word_count=word_count,
    )

    doc.close()
    return doctree


if __name__ == "__main__":
    # Usage: python ingest.py path/to/file.pdf
    if len(sys.argv) < 2:
        print("Usage: python ingest.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    doctree = ingest_pdf(pdf_path)

    print("\nDOC TREE")
    print(f"Title   : {doctree.title}")
    print(f"Words   : {doctree.word_count}")
    print(f"Sections: {len(doctree.sections)}")
    print(f"\nFirst section preview ({doctree.sections[0].heading}):")
    print(doctree.sections[0].text[:300], "...")
