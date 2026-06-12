import sys
from pathlib import Path

from src.ingest import ingest_pdf
from src.chunker import chunk_doctree
from src.embedder import embed_and_upsert
from src.retrieval import retrieve
from src.query_compiler import compile_query
from src.planner import generate_slide_plan
from src.content import generate_content
from src.style import resolve_style
from src.renderer import render_pptx
from src.utils import log, CONFIG
from src.agent import run_agent
import argparse




def run_offline(pdf_path: str) -> None:
    """
    Offline pipeline — run once per PDF.
    Ingests, chunks, embeds and stores in Milvus.
    """
    doc_id = Path(pdf_path).stem

    log("main", f"Starting offline pipeline for '{doc_id}'")

    doctree = ingest_pdf(pdf_path)
    log("main", f"Ingested — {len(doctree.sections)} sections, {doctree.word_count} words")

    chunks = chunk_doctree(
        doctree,
        chunk_size=CONFIG["chunking"]["chunk_size"],
        overlap=CONFIG["chunking"]["overlap"],
    )
    log("main", f"Chunked — {len(chunks)} chunks")

    embed_and_upsert(chunks, doc_id)
    log("main", f"Embedded and stored in Milvus")


def run_online(query: str, doc_id: str) -> str:
    log("main", f"Starting agent pipeline")
    output = run_agent(query, doc_id)
    log("main", f"Done — {output}")
    return output

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="PDF to PPTX Agent Orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Offline Pipeline Parser
    offline_parser = subparsers.add_parser("offline", help="Run the offline ingestion pipeline")
    offline_parser.add_argument("pdf_path", type=str, help="Path to the source PDF file")

    # Online Agent Parser
    online_parser = subparsers.add_parser("online", help="Run the online generation agent")
    online_parser.add_argument("query", type=str, help="Your natural language presentation request")
    online_parser.add_argument("doc_id", type=str, help="The document ID (filename stem) stored in Milvus")

    args = parser.parse_args()

    if args.command == "offline":
        run_offline(args.pdf_path)
    elif args.command == "online":
        run_online(args.query, args.doc_id)