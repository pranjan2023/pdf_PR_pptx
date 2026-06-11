import uuid
from src.models import DocTree, Chunk
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_doctree(doctree: DocTree, chunk_size: int = 512, overlap: int = 64) -> list[Chunk]:
    """
    Split each DocTree section into overlapping chunks.
    Returns a flat list of Chunk objects ready for embedding.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " "],
    )

    chunks = []

    for section in doctree.sections:
        if not section.text.strip():
            continue

        raw_chunks = splitter.split_text(section.text)

        for raw in raw_chunks:
            chunk = Chunk(
                chunk_id=str(uuid.uuid4()),
                text=raw.strip(),
                section=section.heading,
                page=section.page_range[0],
                type="section",
            )
            chunks.append(chunk)

    return chunks


if __name__ == "__main__":
    import sys
    from ingest import ingest_pdf

    if len(sys.argv) < 2:
        print("Usage: python chunker.py <path_to_pdf>")
        sys.exit(1)

    doctree = ingest_pdf(sys.argv[1])
    chunks = chunk_doctree(doctree)

    print(f"\nTotal chunks : {len(chunks)}")
    print(f"Avg chunk len: {sum(len(c.text) for c in chunks) // len(chunks)} chars")
    print(f"\nFirst chunk (id={chunks[0].chunk_id}):")
    print(chunks[0].text[:300])
    print(f"\nLast chunk (id={chunks[-1].chunk_id}):")
    
