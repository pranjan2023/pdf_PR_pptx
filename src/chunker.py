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

    Produces three chunk types:
      - "section"  : body text split into overlapping windows
      - "table"    : one chunk per table (not split further)
      - "figure"   : one chunk per figure caption
    
    Each chunk carries its section heading as a prefix for retrieval context.
    """
    splitter = _make_splitter(chunk_size, overlap)
    chunks   = []

    for section in doctree.sections:
        heading = section.heading.strip()
        page    = section.page_range[0]

        # ── Body text → "section" chunks ─────────────────────────────
        body = section.text.strip()
        # Skip the preamble/title section — it's author metadata not content
        if section.heading == doctree.title or section.heading == "Preamble":
            continue        

        if body:
            # Prefix each chunk with its section heading for retrieval context
            prefixed = f"[{heading}]\n{body}"
            raw_chunks = splitter.split_text(prefixed)

            for raw in raw_chunks:
                # Validate token length — BGE-M3 limit is 8192 tokens
                # Rough heuristic: 1 token ≈ 4 chars → 8192 * 4 = 32768 chars
                if len(raw) > 32768:
                    print(f"[chunker] WARNING: chunk exceeds token limit, truncating")
                    raw = raw[:32768]

                chunks.append(Chunk(
                    chunk_id=str(uuid.uuid4()),
                    text=raw.strip(),
                    section=heading,
                    page=page,
                    type="section",
                ))

        # ── Tables → "table" chunks ───────────────────────────────────
        for table_str in section.tables:
            if not table_str.strip():
                continue
            # Tables are not split — keep as one chunk with heading context
            text = f"[{heading}]\n{table_str}"
            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                text=text[:32768],
                section=heading,
                page=page,
                type="table",
            ))

        # ── Figures → "figure" chunks ─────────────────────────────────
        for figure_str in section.figures:
            if not figure_str.strip():
                continue
            text = f"[{heading}]\n{figure_str}"
            chunks.append(Chunk(
                chunk_id=str(uuid.uuid4()),
                text=text,
                section=heading,
                page=page,
                type="figure",
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

    print(f"\nTotal chunks : {len(chunks)}")
    print(f"By type      : {by_type}")
    if chunks:
        avg = sum(len(c.text) for c in chunks) // len(chunks)
        print(f"Avg length   : {avg} chars")

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
        table_chunk = next(c for c in chunks if c.type == "table")
        print(f"\nFirst table chunk (section: {table_chunk.section}):")
        print(table_chunk.text[:300])

    if any(c.type == "figure" for c in chunks):
        fig_chunk = next(c for c in chunks if c.type == "figure")
        print(f"\nFirst figure chunk (section: {fig_chunk.section}):")
        print(fig_chunk.text[:200])