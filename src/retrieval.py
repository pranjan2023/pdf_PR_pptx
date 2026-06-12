import sys
from pymilvus import MilvusClient
from sentence_transformers import SentenceTransformer
from src.models import Chunk, EvidencePack
from src.utils import CONFIG, log


# Constants from config
DB_PATH    = CONFIG["milvus"]["db_path"]
COLLECTION = CONFIG["milvus"]["collection"]
MODEL_NAME = CONFIG["embedding"]["model"]
DEVICE     = CONFIG["embedding"]["device"]

# Minimum cosine similarity to include a chunk — below this is noise
MIN_SCORE  = CONFIG["retrieval"].get("min_score", 0.3)

# Load model once at module level — not on every query
_model: SentenceTransformer | None = None

def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        log("retrieval", f"Loading embedding model '{MODEL_NAME}'...")
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def retrieve(
    query: str,
    top_k: int = 10,
    doc_id: str | None = None,
) -> EvidencePack:
    """
    Embed query, search Milvus with optional doc_id filter.
    Returns typed EvidencePack with chunks routed by type.
    Filters out chunks below MIN_SCORE threshold.
    """
    model = _get_model()
    q_emb = model.encode([query], device=DEVICE)[0].tolist()

    client = MilvusClient(DB_PATH)
    client.load_collection(COLLECTION)

    filter_expr = f'doc_id == "{doc_id}"' if doc_id else ""

    results = client.search(
        collection_name=COLLECTION,
        data=[q_emb],
        limit=top_k,
        filter=filter_expr,
        output_fields=["chunk_id", "text", "section", "page", "type", "doc_id"],
        search_params={"metric_type": CONFIG["milvus"]["metric_type"]},
    )[0]

    client.close()

    # Build Chunk objects — filter by minimum relevance score
    chunks = []
    filtered = 0
    for hit in results:
        score = hit.get("distance", 1.0)   # cosine distance → higher = more similar
        if score < MIN_SCORE:
            filtered += 1
            continue
        e = hit["entity"]
        chunks.append(Chunk(
            chunk_id=e["chunk_id"],
            text=e["text"],
            section=e["section"],
            page=e["page"],
            type=e["type"],
        ))

    if filtered > 0:
        log("retrieval", f"Filtered {filtered} low-relevance chunks (score < {MIN_SCORE})")

    # Route into EvidencePack by type
    pack = EvidencePack(
        concepts=[c for c in chunks if c.type == "concept"],
        tables=[c for c in chunks if c.type == "table"],
        figures=[c for c in chunks if c.type == "figure"],
        sections=[c for c in chunks if c.type == "section"],
    )

    total = len(chunks)
    log("retrieval", (
        f"Retrieved {total} chunks — "
        f"{len(pack.sections)} sections, "
        f"{len(pack.tables)} tables, "
        f"{len(pack.figures)} figures, "
        f"{len(pack.concepts)} concepts"
    ))

    return pack


if __name__ == "__main__":
    query  = sys.argv[1] if len(sys.argv) > 1 else "how does multi-head attention work"
    doc_id = sys.argv[2] if len(sys.argv) > 2 else "Attention_is_all_you_Need"

    print(f"\nQuery  : {query}")
    print(f"Doc ID : {doc_id}")

    pack = retrieve(query, top_k=10, doc_id=doc_id)

    all_chunks = pack.sections + pack.tables + pack.figures + pack.concepts
    print(f"\nTotal  : {len(all_chunks)} chunks")

    for i, c in enumerate(all_chunks):
        print(f"\n--- {i+1} | {c.type} | {c.section} | page {c.page} ---")
        print(c.text[:200])