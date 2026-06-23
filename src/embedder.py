import sys
from pathlib import Path
from pymilvus import MilvusClient, DataType
from FlagEmbedding import BGEM3FlagModel
from src.models import Chunk
from src.utils import CONFIG, log

DB_PATH    = CONFIG["milvus"]["db_path"]
COLLECTION = CONFIG["milvus"]["collection"]
MODEL_NAME = CONFIG["embedding"]["model"]
DIM        = CONFIG["embedding"]["dim"]
DEVICE     = CONFIG["embedding"]["device"]
BATCH_SIZE = CONFIG["embedding"]["batch_size"]

def get_client() -> MilvusClient:
    return MilvusClient(DB_PATH)

def ensure_collection(client: MilvusClient) -> None:
    """Create collection with both Dense and Sparse vector fields."""
    if client.has_collection(COLLECTION):
        return

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("chunk_id",         DataType.VARCHAR, max_length=64, is_primary=True)
    schema.add_field("text",             DataType.VARCHAR, max_length=32768)
    schema.add_field("section",          DataType.VARCHAR, max_length=256)
    schema.add_field("page",             DataType.INT64)
    schema.add_field("type",             DataType.VARCHAR, max_length=64)
    schema.add_field("doc_id",           DataType.VARCHAR, max_length=256)
    schema.add_field("image_path",       DataType.VARCHAR, max_length=512)
    schema.add_field("embedding",        DataType.FLOAT_VECTOR, dim=DIM)
    schema.add_field("sparse_embedding", DataType.SPARSE_FLOAT_VECTOR) # ← NEW: Sparse Field

    index_params = client.prepare_index_params()
    
    # 1. Index for Dense Vectors
    index_params.add_index(
        field_name="embedding",
        index_type="FLAT",
        metric_type=CONFIG["milvus"]["metric_type"],
    )
    
    # 2. Index for Sparse Vectors (BM25-style keywords)
    index_params.add_index(
        field_name="sparse_embedding",
        index_type="SPARSE_INVERTED_INDEX",
        metric_type="IP",
    )

    client.create_collection(
        collection_name=COLLECTION,
        schema=schema,
        index_params=index_params,
    )
    log("embedder", f"Created hybrid collection '{COLLECTION}' (dense_dim={DIM})")

def drop_collection(client: MilvusClient) -> None:
    """Drop collection entirely — use when schema changes."""
    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)
        log("embedder", f"Dropped collection '{COLLECTION}'")

def delete_doc(client: MilvusClient, doc_id: str) -> None:
    """Remove all existing chunks for a doc_id before re-ingesting."""
    try:
        client.load_collection(COLLECTION)
        existing = client.query(
            collection_name=COLLECTION,
            filter=f'doc_id == "{doc_id}"',
            output_fields=["chunk_id"],
        )
        if existing:
            client.delete(
                collection_name=COLLECTION,
                filter=f'doc_id == "{doc_id}"',
            )
            log("embedder", f"Deleted {len(existing)} existing chunks for '{doc_id}'")
    except Exception as e:
        log("embedder", f"No existing chunks to delete ({e})")

def embed_and_upsert(chunks: list[Chunk], doc_id: str) -> None:
    """
    Embed chunks (Dense + Sparse) and upsert into Milvus.
    Includes pre-flight profiling to catch pathological chunks before they crash the GPU.
    """
    if not chunks:
        log("embedder", "No chunks to embed — skipping")
        return

    # 1. Initialize the BGE-M3 model first to prevent timeouts
    log("embedder", f"Loading multi-modal model {MODEL_NAME}...")
    model = BGEM3FlagModel(MODEL_NAME, use_fp16=True, device=DEVICE)

    # 2. Open DB Connection
    client = get_client()
    ensure_collection(client)
    delete_doc(client, doc_id)

    log("embedder", f"Embedding {len(chunks)} chunks...")
    texts = [c.text for c in chunks]
    
    # --- PRE-FLIGHT PROFILING ---
    max_chars = max(len(text) for text in texts)
    print(f"Largest chunk in batch: {max_chars} characters")

    # Identify specific rogue chunks
    for i, chunk in enumerate(chunks):
        if len(chunk.text) > 15000:
            print(f"Pathological chunk found at index {i} in section '{chunk.section}' (Length: {len(chunk.text)})")
    # ----------------------------

    # 3. Generate both dense and sparse representations
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False
    )
    
    dense_vecs = embeddings['dense_vecs']
    sparse_vecs = embeddings['lexical_weights']

    # 4. Map to Milvus rows
    rows = []
    for i, chunk in enumerate(chunks):
        rows.append({
            "chunk_id":         chunk.chunk_id,
            "text":             chunk.text[:32768],
            "section":          chunk.section,
            "page":             chunk.page,
            "type":             chunk.type,
            "doc_id":           doc_id,
            "image_path":       chunk.image_path or "",
            "embedding":        dense_vecs[i].tolist(),
            "sparse_embedding": sparse_vecs[i],
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

    image_chunks = client.query(
        collection_name=COLLECTION,
        filter=f'doc_id == "{doc_id}" and image_path != ""',
        output_fields=["chunk_id", "image_path"],
    )
    log("embedder", f"Verified: {len(count)} chunks, {len(image_chunks)} with image_path")
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
    doctree = ingest_pdf(pdf_path, doc_id=doc_id)
    chunks  = chunk_doctree(doctree)
    log("embedder", f"Got {len(chunks)} chunks")

    embed_and_upsert(chunks, doc_id)