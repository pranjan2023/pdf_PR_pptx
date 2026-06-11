import sys
from pathlib import Path
from pymilvus import MilvusClient
from sentence_transformers import SentenceTransformer
from src.models import Chunk, EvidencePack

COLLECTION = "pdf_chunks"
DB_PATH    = "./data/milvus.db"
MODEL_NAME = "all-MiniLM-L6-v2"
DIM        = 384


def retrieve(query: str, top_k: int = 10, doc_id: str | None = None) -> EvidencePack:
    """
    Embed query, search Milvus, return typed EvidencePack.
    Optionally filter by doc_id to search within a specific document.
    """
    model  = SentenceTransformer(MODEL_NAME)
    q_emb  = model.encode([query], device="mps")[0].tolist()

    client = MilvusClient(DB_PATH)
    client.load_collection(COLLECTION)

    filter_expr = f'doc_id == "{doc_id}"' if doc_id else ""

    results = client.search(
        collection_name=COLLECTION,
        data=[q_emb],
        limit=top_k,
        filter=filter_expr,
        output_fields=["chunk_id", "text", "section", "page", "type", "doc_id"],
        search_params={"metric_type": "COSINE"},
    )[0]   # [0] because we sent one query

    client.close()

    # Build Chunk objects from results
    chunks = []
    for hit in results:
        e = hit["entity"]
        chunks.append(Chunk(
            chunk_id=e["chunk_id"],
            text=e["text"],
            section=e["section"],
            page=e["page"],
            type=e["type"],
        ))

    # Route into EvidencePack by type
    # All chunks are "section" type for now — extend in v2 for tables/figures
    return EvidencePack(
        concepts=[c for c in chunks if c.type == "concept"],
        tables=[c for c in chunks if c.type == "table"],
        figures=[c for c in chunks if c.type == "figure"],
        sections=[c for c in chunks if c.type == "section"],
    )


if __name__ == "__main__":
    query  = sys.argv[1] if len(sys.argv) > 1 else "how does multi-head attention work"
    doc_id = sys.argv[2] if len(sys.argv) > 2 else "Attention_is_all_you_Need"

    print(f"\nQuery  : {query}")
    print(f"Doc ID : {doc_id}")

    pack = retrieve(query, top_k=5, doc_id=doc_id)

    all_chunks = pack.concepts + pack.tables + pack.figures + pack.sections
    print(f"\nRetrieved {len(all_chunks)} chunks\n")

    for i, c in enumerate(all_chunks):
        print(f"--- Chunk {i+1} | {c.section} | page {c.page} ---")
        print(c.text[:200])
        print()
