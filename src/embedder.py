import sys
from pathlib import Path
from pymilvus import MilvusClient, DataType
from sentence_transformers import SentenceTransformer
from src.models import Chunk

COLLECTION = "pdf_chunks"
DB_PATH    = "./data/milvus.db"
MODEL_NAME = "all-MiniLM-L6-v2"   # 90MB — fast on MPS, upgrade to BGE-M3 later
DIM        = 384                   # all-MiniLM output dim


def get_client() -> MilvusClient:
    return MilvusClient(DB_PATH)


def ensure_collection(client: MilvusClient) -> None:
    """Create collection if it doesn't exist."""
    if client.has_collection(COLLECTION):
        return

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("chunk_id",  DataType.VARCHAR, max_length=64, is_primary=True)
    schema.add_field("text",      DataType.VARCHAR, max_length=8192)
    schema.add_field("section",   DataType.VARCHAR, max_length=256)
    schema.add_field("page",      DataType.INT64)
    schema.add_field("type",      DataType.VARCHAR, max_length=64)
    schema.add_field("doc_id",    DataType.VARCHAR, max_length=256)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=DIM)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="FLAT",        # exact search — fine for <10k chunks
        metric_type="COSINE",
    )

    client.create_collection(
        collection_name=COLLECTION,
        schema=schema,
        index_params=index_params,
    )
    print(f"[embedder] Created collection '{COLLECTION}'")


def embed_and_upsert(chunks: list[Chunk], doc_id: str) -> None:
    """Embed chunks and upsert into Milvus."""
    client = get_client()
    ensure_collection(client)

    model = SentenceTransformer(MODEL_NAME)

    texts = [c.text for c in chunks]
    print(f"[embedder] Embedding {len(texts)} chunks with {MODEL_NAME}...")
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        device="mps",             # Apple Silicon — change to "cpu" if issues
    )

    rows = []
    for chunk, emb in zip(chunks, embeddings):
        rows.append({
            "chunk_id":  chunk.chunk_id,
            "text":      chunk.text[:8192],
            "section":   chunk.section,
            "page":      chunk.page,
            "type":      chunk.type,
            "doc_id":    doc_id,
            "embedding": emb.tolist(),
        })

    client.upsert(collection_name=COLLECTION, data=rows)
    print(f"[embedder] Upserted {len(rows)} chunks for doc_id='{doc_id}'")
    client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python embedder.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    doc_id   = Path(pdf_path).stem   # "Attention_is_all_you_Need"

    # Import here to avoid circular deps at module level
    sys.path.insert(0, str(Path(__file__).parent))
    from ingest import ingest_pdf
    from chunker import chunk_doctree

    print(f"[embedder] Ingesting {pdf_path}...")
    doctree = ingest_pdf(pdf_path)
    chunks  = chunk_doctree(doctree)
    print(f"[embedder] Got {len(chunks)} chunks")

    embed_and_upsert(chunks, doc_id)

    # Verify
    client = get_client()
    count  = client.query(
        collection_name=COLLECTION,
        filter=f'doc_id == "{doc_id}"',
        output_fields=["chunk_id"],
    )
    print(f"[embedder] Verified: {len(count)} chunks in Milvus for '{doc_id}'")
    client.close()
