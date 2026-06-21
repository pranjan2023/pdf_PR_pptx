# pdf-agent — PDF + Query → Styled PPTX

> **A fully local, open-source agentic pipeline that takes a PDF and a natural language query, reasons about the right presentation structure, and generates a styled `.pptx` file — no cloud APIs, no data leaving your machine.**

[![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)](https://python.org)
[![Ollama](https://img.shields.io/badge/LLM-qwen2.5:14b-purple?style=flat-square)](https://ollama.com)
[![LangGraph](https://img.shields.io/badge/Agent-LangGraph-orange?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![Local](https://img.shields.io/badge/Runs-100%25%20Local-green?style=flat-square)]()

📖 **[View the full styled README →](https://github.com/pranjan2023/pdf_PR_pptx/README.html)**

---

## Quick Start

```bash
# 1 — Ingest a PDF (run once per document)
python main.py offline path/to/paper.pdf

# 2 — Generate a presentation
python main.py online "make a 10 slide technical presentation on transformer architecture" Attention_is_all_you_Need
```

Output: a styled `.pptx` in `./outputs/` with titles, bullets, speaker notes, and a takeaway bar per slide.

---

## Architecture

![Architecture](./images/architecure)

The system follows a two-path design:

```
OFFLINE (once per PDF)
PDF → ingest → chunker → embedder → Milvus Lite

ONLINE (per query) — LangGraph StateGraph
Query → S0 QueryCompiler → S3c Retrieval → S4 Strategy → S4c grade
      → S5 Planner → S5c grade → S6 ContentGen → S7 Compress
      → S9 StyleResolver → S11 Renderer → .pptx
```

The online path runs as a **LangGraph StateGraph** with conditional retry loops at both the strategy and planner stages. Critics are deterministic Python — no extra LLM calls at validation time.

---

## Stack

| Component | Tool |
|---|---|
| PDF parsing | PyMuPDF (fitz) |
| Chunking | LangChain RecursiveCharacterTextSplitter |
| Embeddings | all-MiniLM-L6-v2 (sentence-transformers) |
| Vector store | Milvus Lite |
| LLM | qwen2.5:14b via Ollama |
| Agent orchestration | LangGraph |
| PPTX generation | python-pptx |
| Config | YAML + Pydantic |

---

## Setup

```bash
# Create environment
conda create -n pdf-agent python=3.11 -y
conda activate pdf-agent

# Install dependencies
pip install -r requirements.txt

# Fix OMP conflict on macOS Apple Silicon
conda env config vars set KMP_DUPLICATE_LIB_OK=TRUE -n pdf-agent
conda deactivate && conda activate pdf-agent

# Pull the LLM
ollama pull qwen2.5:14b
```

---

## Usage

```bash
# Technical overview
python main.py online "make a 10 slide technical presentation on the transformer architecture" Attention_is_all_you_Need

# Executive summary
python main.py online "create a 5 slide executive summary of the attention mechanism" Attention_is_all_you_Need

# Beginner tutorial with dark theme
python main.py online "build a beginner tutorial on self-attention dark theme" Attention_is_all_you_Need
```

### Style keywords

| Keywords | Theme |
|---|---|
| `dark`, `minimal` | Dark background, blue accent |
| `corporate`, `formal` | White, navy accent |
| `colorful`, `creative` | Light grey, pink accent |
| *(default)* | White, blue accent |

---

## Project Structure

```
pdf-agent/
├── main.py               # CLI entry point
├── config.yaml           # model names, chunk params, retrieval settings
├── requirements.txt
├── README.md
├── README.html           # Styled full-page README
└── src/
    ├── models.py         # Pydantic artifact definitions
    ├── utils.py          # shared LLM caller, JSON parser, logger
    ├── ingest.py         # S1  — PDF → DocTree
    ├── chunker.py        # S3a — DocTree → list[Chunk]
    ├── embedder.py       # S3b — list[Chunk] → Milvus
    ├── retrieval.py      # S3c — query → EvidencePack
    ├── query_compiler.py # S0  — raw string → PresentationRequest
    ├── strategy.py       # S4  — PresentationStrategy (LLM)
    ├── planner.py        # S5  — SlidePlan (LLM)
    ├── content.py        # S6  — SlideContent (LLM)
    ├── compression.py    # S7  — trim bullets
    ├── visual.py         # S8  — VisualSpec per slide
    ├── style.py          # S9  — StyleConfig from description
    ├── layout.py         # S10 — LayoutSpec (deterministic)
    ├── renderer.py       # S11 — python-pptx → .pptx
    └── agent.py          # LangGraph StateGraph wiring
```

---

## Roadmap

- [x] Phase 1 — MVP (offline ingestion + online generation + PPTX render)
- [x] Phase 2 — LangGraph agent loop with plan critic
- [ ] Phase 3 — Semantic DocTree + BGE-M3 embeddings + hybrid search
- [ ] Phase 3 — S4 strategy critic + S7 compression agent
- [ ] Phase 4 — Gradio UI + FastAPI endpoint
- [ ] Phase 5 — Evaluation harness + open-source release

---

## Design Principles

**Typed artifacts at every boundary** — every stage produces a Pydantic model. No raw strings between stages.

**Constraints propagate as data** — slide count, audience, style extracted at S0 and enforced downstream mechanically.

**Offline / online separation** — ingestion happens once per document. Query-time work starts at retrieval. These paths never mix.

**Critics are cheap** — the plan critic is deterministic Python. LLM calls only when schema validation fails.

---

## Acknowledgements

Built during an internship at [Unicloud](https://unicloud.in). Architecture informed by synthesis of multiple agentic RAG patterns. Built on top of [Milvus](https://milvus.io), [LangGraph](https://langchain-ai.github.io/langgraph/), and [Ollama](https://ollama.com).
