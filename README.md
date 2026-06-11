# pdf-agent — PDF + Query → Styled PPTX

A fully local, open-source agentic pipeline that takes a PDF and a natural language query, reasons about the right presentation structure, and generates a styled `.pptx` file — no cloud APIs, no data leaving your machine.

Built during an internship at [Unicloud](https://unicloud.in) as a production-grade document intelligence system.

---

## Demo

```bash
# Ingest a PDF into the vector store (run once per document)
python main.py offline path/to/paper.pdf

# Generate a presentation from a query
python main.py online "make a 10 slide technical presentation on the transformer architecture" Attention_is_all_you_Need
```

Output: a styled `.pptx` file in `./outputs/` with titles, bullets, speaker notes, and a takeaway bar per slide.

---

## Architecture

The system follows a two-path design:

```
OFFLINE (once per PDF)
────────────────────────────────────────────
PDF → DocIntelligence → Chunker → Embedder → Milvus Lite

ONLINE (per query)
────────────────────────────────────────────
Query → S0 QueryCompiler → PresentationRequest
      → S3c Retrieval    → EvidencePack
      → S5 Planner       → SlidePlan          ← LLM
      → S5c PlanCritic   → grade (deterministic)
      → S6 ContentGen    → list[SlideContent] ← LLM
      → S9 StyleResolver → StyleConfig
      → S11 Renderer     → .pptx
```

The online path runs as a **LangGraph StateGraph** with a conditional retry loop between the planner and critic — if the plan fails validation, the agent re-retrieves with the missing topic and replans.

### Typed artifact chain

Every stage boundary is a validated Pydantic model — no raw strings passed between stages:

```
str (raw query)
  → PresentationRequest
  → EvidencePack
  → SlidePlan
  → list[SlideContent]
  → StyleConfig
  → .pptx
```

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

Everything runs locally. No OpenAI, no Anthropic, no external APIs.

---

## Project structure

```
pdf-agent/
├── main.py               # CLI entry point (offline + online modes)
├── config.yaml           # model names, chunk params, retrieval settings
├── requirements.txt
└── src/
    ├── models.py         # all Pydantic artifact definitions
    ├── utils.py          # shared LLM caller, JSON parser, logger, CONFIG
    ├── ingest.py         # S1  — PDF → DocTree
    ├── chunker.py        # S3a — DocTree → list[Chunk]
    ├── embedder.py       # S3b — list[Chunk] → Milvus
    ├── retrieval.py      # S3c — query → EvidencePack
    ├── query_compiler.py # S0  — raw string → PresentationRequest
    ├── strategy.py       # S4  — PresentationStrategy (LLM)
    ├── planner.py        # S5  — SlidePlan (LLM)
    ├── content.py        # S6  — SlideContent (LLM)
    ├── compression.py    # S7  — trim bullets for slide format
    ├── visual.py         # S8  — VisualSpec per slide
    ├── style.py          # S9  — StyleConfig from description
    ├── layout.py         # S10 — LayoutSpec (deterministic)
    ├── renderer.py       # S11 — python-pptx → .pptx
    └── agent.py          # LangGraph StateGraph wiring
```

---

## Setup

### Prerequisites

- Python 3.11
- [Ollama](https://ollama.com) running locally with `qwen2.5:14b` pulled
- Conda (recommended) or venv

### Install

```bash
# Create environment
conda create -n pdf-agent python=3.11 -y
conda activate pdf-agent

# Install dependencies
pip install -r requirements.txt

# Fix OMP conflict on macOS (Apple Silicon)
conda env config vars set KMP_DUPLICATE_LIB_OK=TRUE -n pdf-agent
conda deactivate && conda activate pdf-agent

# Pull the LLM
ollama pull qwen2.5:14b
```

### Verify setup

```bash
# Test Ollama connection
python -c "
import requests
r = requests.post('http://localhost:11434/api/chat',
    json={'model':'qwen2.5:14b','messages':[{'role':'user','content':'ping'}],'stream':False})
print(r.json()['message']['content'])
"

# Test Milvus
python -c "from pymilvus import MilvusClient; print('Milvus ok')"
```

---

## Usage

### Ingest a PDF

```bash
python main.py offline /path/to/document.pdf
```

This parses, chunks, embeds, and stores the document in `./data/milvus.db`. Run once per document. The `doc_id` is the filename stem (e.g. `Attention_is_all_you_Need` for `Attention_is_all_you_Need.pdf`).

### Generate a presentation

```bash
python main.py online "<query>" <doc_id>
```

Examples:

```bash
# Technical overview
python main.py online "make a 10 slide technical presentation on the transformer architecture" Attention_is_all_you_Need

# Executive summary
python main.py online "create a 5 slide executive summary of the attention mechanism" Attention_is_all_you_Need

# Beginner tutorial with dark theme
python main.py online "build a beginner tutorial on self-attention dark theme" Attention_is_all_you_Need
```

Output is saved to `./outputs/presentation.pptx`.

### Style options

Specify style keywords in your query:

| Keywords | Theme |
|---|---|
| `dark`, `minimal` | Dark background, blue accent |
| `corporate`, `formal` | White, navy accent |
| `colorful`, `creative` | Light grey, pink accent |
| default | White, blue accent |

---

## Configuration

All tuneable parameters live in `config.yaml`:

```yaml
llm:
  model: qwen2.5:14b
  base_url: http://localhost:11434/api/chat
  timeout: 120

embedding:
  model: all-MiniLM-L6-v2
  device: mps          # change to "cpu" if not on Apple Silicon

retrieval:
  top_k: 15
  min_evidence: 3

chunking:
  chunk_size: 512
  overlap: 64

agent:
  max_plan_retries: 3
  max_content_retries: 2
```

---

## How the agent loop works

The planner and critic form a retry loop inside the LangGraph graph:

```
retrieve → plan → grade_plan
                    ├── good      → generate_content → style → render
                    └── retry     → plan (re-attempt, max 3×)
```

The `grade_plan` node is deterministic Python — it checks slide count tolerance (±1), non-empty purposes, and no duplicate purposes. No LLM call at the critic stage keeps latency low.

---

## Roadmap

- [x] Phase 1 — MVP (offline ingestion + online generation + PPTX render)
- [x] Phase 2 — LangGraph agent loop with plan critic
- [ ] Phase 3 — Semantic DocTree (heading-level chunking, table/figure extraction)
- [ ] Phase 3 — BGE-M3 embeddings + hybrid search (dense + BM25)
- [ ] Phase 3 — S4 strategy stage + strategy critic
- [ ] Phase 3 — S7 compression agent
- [ ] Phase 4 — Gradio UI (PDF upload, query input, style selector, download)
- [ ] Phase 4 — FastAPI endpoint
- [ ] Phase 5 — Evaluation harness + open-source release

---

## Design principles

**Typed artifacts at every boundary** — every stage produces a Pydantic model. No raw strings between stages. Enables caching, partial regeneration, and model swapping.

**Constraints propagate as data** — slide count, audience, style extracted at S0 and enforced mechanically downstream, not passed as vague prompt instructions.

**Offline/online separation** — ingestion happens once per document. Query-time work starts at retrieval. These paths never mix.

**Critics are cheap** — the plan critic is deterministic Python. LLM critic calls only when schema validation fails.

---

## Acknowledgements

Architecture design informed by synthesis of multiple agentic RAG patterns. Built on top of the [Milvus](https://milvus.io), [LangGraph](https://langchain-ai.github.io/langgraph/), and [Ollama](https://ollama.com) ecosystems.
