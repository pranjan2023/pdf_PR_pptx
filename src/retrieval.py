import sys
from pymilvus import MilvusClient, AnnSearchRequest, RRFRanker
from FlagEmbedding import BGEM3FlagModel
from src.models import Chunk, EvidencePack
from src.utils import CONFIG, log

DB_PATH    = CONFIG["milvus"]["db_path"]
COLLECTION = CONFIG["milvus"]["collection"]
MODEL_NAME = CONFIG["embedding"]["model"]
DEVICE     = CONFIG["embedding"]["device"]

_model: BGEM3FlagModel | None = None

def _get_model() -> BGEM3FlagModel:
    global _model
    if _model is None:
        log("retrieval", f"Loading multi-modal model '{MODEL_NAME}'...")
        # use_fp16=True is highly optimized for Apple Silicon (MPS)
        _model = BGEM3FlagModel(MODEL_NAME, use_fp16=True, device=DEVICE)
    return _model

def retrieve(
    query: str,
    top_k: int = 20,
    doc_id: str | None = None,
) -> EvidencePack:
    """
    Cascading Hybrid Search: Dense + Sparse with RRF.
    Searches local doc_id first, falls back to global database if capacity isn't met.
    """
    model = _get_model()
    
    # 1. Embed Query
    query_embeddings = model.encode(
        [query], return_dense=True, return_sparse=True, return_colbert_vecs=False
    )
    q_dense = query_embeddings['dense_vecs'][0].tolist()
    q_sparse = query_embeddings['lexical_weights'][0]

    client = MilvusClient(DB_PATH)
    client.load_collection(COLLECTION)

    # 2. Reusable Search Wrapper
    def execute_search(limit: int, filter_str: str) -> list:
        dense_req = AnnSearchRequest(
            data=[q_dense], anns_field="embedding",
            param={"metric_type": CONFIG["milvus"]["metric_type"], "params": {"nprobe": 10}},
            limit=limit, expr=filter_str
        )
        sparse_req = AnnSearchRequest(
            data=[q_sparse], anns_field="sparse_embedding",
            param={"metric_type": "IP", "params": {"drop_ratio_build": 0.2}},
            limit=limit, expr=filter_str
        )
        res = client.hybrid_search(
            collection_name=COLLECTION, reqs=[dense_req, sparse_req],
            ranker=RRFRanker(k=60), limit=limit,
            output_fields=["chunk_id", "text", "section", "page", "type", "doc_id", "image_path"]
        )
        return res[0] if res else []

    results = []
    
    # 3. Tier 1: Local Document Search
    if doc_id:
        local_filter = f'doc_id == "{doc_id}"'
        results = execute_search(limit=top_k, filter_str=local_filter)
        log("retrieval", f"Local search yielded {len(results)} chunks for '{doc_id}'.")

    # 4. Tier 2: Global Fallback Search
    if len(results) < top_k:
        fallback_limit = top_k - len(results)
        
        # Exclude the already searched document to prevent duplicate chunks
        global_filter = f'doc_id != "{doc_id}"' if doc_id else ""
        
        log("retrieval", f"Capacity not met. Falling back to global search for {fallback_limit} additional chunks...")
        global_results = execute_search(limit=fallback_limit, filter_str=global_filter)
        results.extend(global_results)

    client.close()

    # 5. Pack Results
    chunks = []
    for hit in results:
        e = hit["entity"]
        chunks.append(Chunk(
            chunk_id=e["chunk_id"],
            text=e["text"],
            section=e["section"],
            page=e["page"],
            type=e["type"],
            image_path=e.get("image_path") or None,
            # We add doc_id here so we can see which paper the chunk came from in the printout
            doc_id=e.get("doc_id", "unknown") 
        ))

    pack = EvidencePack(
        concepts=[c for c in chunks if c.type == "concept"],
        tables=[c for c in chunks if c.type == "table"],
        figures=[c for c in chunks if c.type == "figure"],
        sections=[c for c in chunks if c.type == "section"],
    )

    log("retrieval", f"Final retrieval: {len(chunks)} chunks "
                     f"({len(pack.sections)} sections, {len(pack.tables)} tables, {len(pack.figures)} figures)")

    return pack

if __name__ == "__main__":
    # Removed hardcoded doc_id default to allow pure global searches easily
    query  = sys.argv[1] if len(sys.argv) > 1 else "how does cross-attention work?"
    doc_id = sys.argv[2] if len(sys.argv) > 2 else None 

    print(f"\nQuery  : {query}")
    print(f"Doc ID : {doc_id if doc_id else 'GLOBAL SEARCH'}")

    pack = retrieve(query, top_k=5, doc_id=doc_id)

    all_chunks = pack.sections + pack.tables + pack.figures + pack.concepts
    print(f"\nTotal  : {len(all_chunks)} chunks")

    for i, c in enumerate(all_chunks):
        img = f"  [image: {c.image_path}]" if c.image_path else ""
        # The print statement now shows the doc_id so you can see the fallback working
        print(f"\n--- {i+1} | {c.type} | doc: {getattr(c, 'doc_id', 'unknown')} | {c.section} | page {c.page}{img} ---")
        print(c.text[:300] + "...\n")