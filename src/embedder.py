import sys
from pathlib import Path
from pymilvus import MilvusClient, DataType
from sentence_transformers import SentenceTransformer
from src.models import Chunk
from src.utils import CONFIG, log


# Read from config — single source of truth
DB_PATH    = CONFIG["milvus"]["db_path"]
COLLECTION = CONFIG["milvus"]["collection"]
MODEL_NAME = CONFIG["embedding"]["model"]
DIM        = CONFIG["embedding"]["dim"]
DEVICE     = CONFIG["embedding"]["device"]
BATCH_SIZE = CONFIG["embedding"]["batch_size"]


def get_client() -> MilvusClient:
    return MilvusClient(DB_PATH)


def ensure_collection(client: MilvusClient) -> None:
    """Create collection if it doesn't exist."""
    if client.has_collection(COLLECTION):
        return

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("chunk_id",  DataType.VARCHAR, max_length=64,    is_primary=True)
    schema.add_field("text",      DataType.VARCHAR, max_length=32768)  # matches chunker limit
    schema.add_field("section",   DataType.VARCHAR, max_length=256)
    schema.add_field("page",      DataType.INT64)
    schema.add_field("type",      DataType.VARCHAR, max_length=64)
    schema.add_field("doc_id",    DataType.VARCHAR, max_length=256)
    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=DIM)     # from config

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="FLAT",        # exact search — fine for <10k chunks
        metric_type=CONFIG["milvus"]["metric_type"],
    )

    client.create_collection(
        collection_name=COLLECTION,
        schema=schema,
        index_params=index_params,
    )
    log("embedder", f"Created collection '{COLLECTION}' (dim={DIM})")


def delete_doc(client: MilvusClient, doc_id: str) -> None:
    """
    Remove all existing chunks for a doc_id before re-ingesting.
    Prevents duplicates when running offline pipeline twice.
    """
    try:
        client.load_collection(COLLECTION)
        existing = client.query(
            collection_name=COLLECTION,
            filter=f'doc_id == "{doc_id}"',
            output_fields=["chunk_id"],
        )
        if existing:
            ids = [r["chunk_id"] for r in existing]
            client.delete(
                collection_name=COLLECTION,
                filter=f'doc_id == "{doc_id}"',
            )
            log("embedder", f"Deleted {len(ids)} existing chunks for '{doc_id}'")
    except Exception as e:
        log("embedder", f"No existing chunks to delete ({e})")


def embed_and_upsert(chunks: list[Chunk], doc_id: str) -> None:
    """
    Embed chunks with sentence-transformers and upsert into Milvus.
    Deletes existing chunks for doc_id first to prevent duplicates.
    """
    if not chunks:
        log("embedder", "No chunks to embed — skipping")
        return

    client = get_client()
    ensure_collection(client)
    delete_doc(client, doc_id)

    log("embedder", f"Embedding {len(chunks)} chunks with {MODEL_NAME}...")
    model = SentenceTransformer(MODEL_NAME)
    texts = [c.text for c in chunks]

    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        device=DEVICE,
    )

    rows = []
    for chunk, emb in zip(chunks, embeddings):
        rows.append({
            "chunk_id":  chunk.chunk_id,
            "text":      chunk.text[:32768],
            "section":   chunk.section,
            "page":      chunk.page,
            "type":      chunk.type,
            "doc_id":    doc_id,
            "embedding": emb.tolist(),
        })

    client.upsert(collection_name=COLLECTION, data=rows)
    log("embedder", f"Upserted {len(rows)} chunks for doc_id='{doc_id}'")

    # Verify
    client.load_collection(COLLECTION)
    count = client.query(
        collection_name=COLLECTION,
        filter=f'doc_id == "{doc_id}"',
        output_fields=["chunk_id"],
    )
    log("embedder", f"Verified: {len(count)} chunks in Milvus for '{doc_id}'")
    client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.embedder <path_to_pdf>")
        sys.exit(1)

    from src.ingest import ingest_pdf
    from src.chunker import chunk_doctree

    pdf_path = sys.argv[1]
    doc_id   = Path(pdf_path).stem

    log("embedder", f"Starting offline pipeline for '{doc_id}'")
    doctree = ingest_pdf(pdf_path)
    chunks  = chunk_doctree(doctree)
    log("embedder", f"Got {len(chunks)} chunks")

    embed_and_upsert(chunks, doc_id)