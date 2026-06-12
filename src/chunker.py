import uuid
from src.models import DocTree, Chunk
from langchain_text_splitters import RecursiveCharacterTextSplitter


def _make_splitter(chunk_size: int, overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " "],
    )


def chunk_doctree(
    doctree: DocTree,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[Chunk]:
    """
    Chunk a semantic DocTree into typed Chunk objects.

    Produces four chunk types:
      - "section" : body text split into overlapping windows
      - "table"   : one chunk per TableData (markdown, no split)
      - "figure"  : one chunk per FigureImage (caption + image_path)
      - "concept" : reserved for future named entity extraction

    Each chunk carries its section heading as a prefix for retrieval context.
    image_path is populated for figure and table chunks that have saved images.
    """
    splitter = _make_splitter(chunk_size, overlap)
    chunks   = []

    for section in doctree.sections:
        heading = section.heading.strip()
        page    = section.page_range[0]

        # Skip preamble/title — author metadata, not content
        if section.heading == doctree.title or section.heading == "Preamble":
            continue

        # ── Body text → "section" chunks ─────────────────────────────
        body = section.text.strip()
        if body:
            prefixed   = f"[{heading}]\n{body}"
            raw_chunks = splitter.split_text(prefixed)

            for raw in raw_chunks:
                if len(raw) > 32768:
                    print(f"[chunker] WARNING: chunk exceeds token limit, truncating")
                    raw = raw[:32768]
                chunks.append(Chunk(
                    chunk_id=str(uuid.uuid4()),
                    text=raw.strip(),
                    section=heading,
                    page=page,
                    type="section",
                    image_path=None,
                ))

        # ── Tables → "table" chunks (from TableData) ──────────────────
        for td in section.table_data:
            if not td.markdown.strip():
                continue
            text = f"[{heading}]\n[Table, page {td.page}]\n{td.markdown}"
            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                text=text[:32768],
                section=heading,
                page=td.page,
                type="table",
                image_path=td.image_path,   # None for now, set in Phase 3+
            ))

        # ── Figures → "figure" chunks (from FigureImage) ──────────────
        for fi in section.figure_images:
            # Build rich text: caption + image availability signal
            caption_text = fi.caption.strip() if fi.caption else "No caption available"
            has_image    = fi.path is not None

            text = f"[{heading}]\n[Figure, page {fi.page}]\nCaption: {caption_text}"
            if has_image:
                text += f"\n[IMAGE_PATH: {fi.path}]"

            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                text=text,
                section=heading,
                page=fi.page,
                type="figure",
                image_path=fi.path,         # actual path on disk or None
            ))

    return chunks


if __name__ == "__main__":
    import sys
    from src.ingest import ingest_pdf

    if len(sys.argv) < 2:
        print("Usage: python -m src.chunker <path_to_pdf>")
        sys.exit(1)

    doctree = ingest_pdf(sys.argv[1])
    chunks  = chunk_doctree(doctree)

    # Summary
    by_type = {}
    for c in chunks:
        by_type[c.type] = by_type.get(c.type, 0) + 1

    print(f"\nTotal chunks  : {len(chunks)}")
    print(f"By type       : {by_type}")
    if chunks:
        avg = sum(len(c.text) for c in chunks) // len(chunks)
        print(f"Avg length    : {avg} chars")

    # Image path coverage
    with_images = [c for c in chunks if c.image_path]
    print(f"With image_path: {len(with_images)} chunks")

    print(f"\nChunk breakdown by section:")
    seen = set()
    for c in chunks:
        if c.section not in seen:
            section_chunks = [x for x in chunks if x.section == c.section]
            types = {}
            for sc in section_chunks:
                types[sc.type] = types.get(sc.type, 0) + 1
            print(f"  {c.section[:50]:<50} → {types}")
            seen.add(c.section)

    print(f"\nFirst section chunk:")
    print(chunks[0].text[:300])

    if any(c.type == "table" for c in chunks):
        tc = next(c for c in chunks if c.type == "table")
        print(f"\nFirst table chunk (section: {tc.section}, page: {tc.page}):")
        print(tc.text[:300])

    if any(c.type == "figure" for c in chunks):
        fc = next(c for c in chunks if c.type == "figure")
        print(f"\nFirst figure chunk (section: {fc.section}, page: {fc.page}):")
        print(f"  image_path: {fc.image_path}")
        print(f"  text: {fc.text[:200]}")