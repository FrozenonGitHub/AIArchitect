# Levitech MVP Tech Stack

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (Minimal UI)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────────────┐  │
│  │   Folder    │  │   Ask Box   │  │          Sources Panel              │  │
│  │   Picker    │  │   (Input)   │  │  [Client Docs] [Legal Sources]      │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ HTTP/REST
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BACKEND (FastAPI)                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                        API Layer (main.py)                           │   │
│  │   /chat  /upload  /cases  /search  /metadata                         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                 │                                           │
│  ┌──────────────────────────────┴───────────────────────────────────────┐   │
│  │                      Orchestration Layer                              │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐  │   │
│  │  │ Answer Engine  │  │ Citation       │  │ Session State          │  │   │
│  │  │ (2-phase RAG)  │  │ Validator      │  │ Manager                │  │   │
│  │  └────────────────┘  └────────────────┘  └────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                 │                                           │
│  ┌──────────────────────────────┴───────────────────────────────────────┐   │
│  │                        Retrieval Layer                                │   │
│  │  ┌─────────────────────────┐      ┌─────────────────────────────┐    │   │
│  │  │   CLIENT DOC PIPELINE   │      │   LEGAL SOURCE PIPELINE     │    │   │
│  │  │  ┌─────────────────┐    │      │  ┌─────────────────────┐    │    │   │
│  │  │  │ Doc Processor   │    │      │  │ Legal Retriever     │    │    │   │
│  │  │  │ (PDF/Word)      │    │      │  │ (GOV.UK, Caselaw)   │    │    │   │
│  │  │  └────────┬────────┘    │      │  └──────────┬──────────┘    │    │   │
│  │  │  ┌────────▼────────┐    │      │  ┌──────────▼──────────┐    │    │   │
│  │  │  │ Chunker         │    │      │  │ Domain Whitelist    │    │    │   │
│  │  │  │ (500-800 tok)   │    │      │  │ Filter              │    │    │   │
│  │  │  └────────┬────────┘    │      │  └──────────┬──────────┘    │    │   │
│  │  │  ┌────────▼────────┐    │      │             │               │    │   │
│  │  │  │ Hybrid Search   │    │      │             │               │    │   │
│  │  │  │ (BM25+Vector)   │    │      │             │               │    │   │
│  │  │  └─────────────────┘    │      │             │               │    │   │
│  │  └─────────────────────────┘      └─────────────┴───────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                 │                                           │
│  ┌──────────────────────────────┴───────────────────────────────────────┐   │
│  │                         LLM Layer                                     │   │
│  │  ┌────────────────────────────────────────────────────────────────┐  │   │
│  │  │  OpenAI / Claude API  (via AI-Builders or direct)              │  │   │
│  │  │  - Answer generation with source constraints                   │  │   │
│  │  │  - Summary generation for rolling case context                 │  │   │
│  │  └────────────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STORAGE LAYER                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐  │
│  │  Vector DB      │  │  Case Metadata  │  │  File Storage               │  │
│  │  (ChromaDB)     │  │  (JSON/SQLite)  │  │  (Local Folders)            │  │
│  │                 │  │                 │  │                             │  │
│  │  - Embeddings   │  │  - client_name  │  │  /storage/case_docs/{id}/   │  │
│  │  - Chunk refs   │  │  - matter_type  │  │  - Original PDFs/Docs       │  │
│  │  - Metadata     │  │  - key_dates    │  │  - Extracted text cache     │  │
│  └─────────────────┘  │  - notes        │  └─────────────────────────────┘  │
│                       └─────────────────┘                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Technology Options & Trade-offs

### 1. Document Processing (PDF + Word)

| Option | Pros | Cons | MVP Recommendation |
|--------|------|------|-------------------|
| **PyMuPDF (fitz)** | Fast, preserves layout, page numbers | Requires binary install | ✅ **Recommended** |
| **pdfplumber** | Good table extraction | Slower than PyMuPDF | Good alternative |
| **python-docx** | Native .docx support | Only Word, not PDF | ✅ **Use alongside PyMuPDF** |
| **Unstructured.io** | Handles many formats | Heavy dependency, overkill for MVP | Later |

**MVP Choice:** `PyMuPDF` + `python-docx` + `OCRmyPDF` (for scanned PDFs)
```bash
uv pip install pymupdf python-docx ocrmypdf
```

**OCR Handling (Critical for case files):**
- Detect scanned PDFs (low text extraction yield)
- Run OCRmyPDF to create searchable layer
- Tag chunks with `ocr: true` in provenance metadata
- Without OCR, scanned case documents will crater retrieval accuracy

**System deps required for OCRmyPDF (must be installed separately):**
- Tesseract OCR
- Ghostscript

---

### 2. Vector Database (Embeddings Storage)

| Option | Pros | Cons | MVP Recommendation |
|--------|------|------|-------------------|
| **ChromaDB** | Simple, local, Python-native | Limited scale | ✅ **Recommended for MVP** |
| **Qdrant** | Better performance, hybrid search | More setup | Good for P1 |
| **Pinecone** | Managed, scalable | Cloud-only, cost | Not for MVP |
| **pgvector** | Postgres-based, familiar | Requires Postgres | Overkill for MVP |

**MVP Choice:** `ChromaDB` (already in your project structure)
```bash
uv pip install chromadb
```

---

### 3. Embedding Model

| Option | Pros | Cons | MVP Recommendation |
|--------|------|------|-------------------|
| **OpenAI text-embedding-3-small** | High quality, simple API | Cost per request | ✅ **Recommended** |
| **sentence-transformers (local)** | Free, offline | Lower quality, needs GPU | Fallback option |
| **Cohere embed-v3** | Good multilingual | Another API key | Not needed |

**MVP Choice:** `OpenAI text-embedding-3-small` (via your AI-Builders endpoint)
- Dimension: 1536
- Cost: ~$0.02 per 1M tokens

---

### 4. Hybrid Search (Keyword + Vector)

| Option | Pros | Cons | MVP Recommendation |
|--------|------|------|-------------------|
| **BM25 + ChromaDB** | Simple to implement | Manual fusion | ✅ **Recommended** |
| **Qdrant (native hybrid)** | Built-in fusion | Migration needed | P1 |
| **Elasticsearch** | Production-grade | Heavy infrastructure | Not for MVP |

**MVP Choice:** `rank-bm25` + ChromaDB vector search with score fusion
```bash
uv pip install rank-bm25
```

---

### 5. LLM Provider

| Option | Pros | Cons | MVP Recommendation |
|--------|------|------|-------------------|
| **AI-Builders API** | Already configured, free/cheap | Limited model selection | ✅ **Use for MVP** |
| **OpenAI direct** | Full model access | Need separate key | Backup |
| **Claude API** | Better reasoning | Need separate key | Consider for legal analysis |

**MVP Choice:** Keep using AI-Builders API (already in main.py)

---

### 6. Legal Source Retrieval

| Option | Pros | Cons | MVP Recommendation |
|--------|------|------|-------------------|
| **HTTP scraping** | Simple, immediate | Fragile, rate limits | ✅ **MVP start** |
| **SerpAPI / Google** | Reliable search | Cost | Nice to have |
| **Pre-cached corpus** | Fast, reliable | Maintenance | P0.5 |

**MVP Choice:** Direct HTTP fetch with BeautifulSoup (already in your code)
- Whitelist domains:
  - gov.uk
  - legislation.gov.uk
  - caselaw.nationalarchives.gov.uk
  - commonslibrary.parliament.uk

**Source Snapshot Storage (Critical for P0):**
- Store raw HTML/text of every fetched legal source
- Include SHA-256 hash + fetch timestamp
- Enables excerpt verification and drift detection
```
/storage/legal_cache/{domain}/{url_hash}/
├── source.html          # Raw fetched content
├── source.txt           # Extracted text
└── meta.json            # {url, hash, fetched_at, title}
```

**Note:** Access to cached sources should go through `legal_cache_service` (not ad-hoc file reads).

---

### 7. Case Metadata Storage

| Option | Pros | Cons | MVP Recommendation |
|--------|------|------|-------------------|
| **JSON files** | Simple, editable | No queries | ✅ **MVP start** |
| **SQLite** | Queryable, single file | Slightly more complex | P0.5 |
| **PostgreSQL** | Full RDBMS | Overkill for MVP | P1+ |

**MVP Choice:** JSON file per case folder
```
/storage/case_docs/{case_id}/
├── metadata.json
├── document1.pdf
└── document2.docx
```

---

### 8. Frontend

| Option | Pros | Cons | MVP Recommendation |
|--------|------|------|-------------------|
| **Vanilla HTML/JS** | Zero build, simple | Limited interactivity | ✅ **MVP** |
| **HTMX** | Server-driven, minimal JS | Learning curve | Good alternative |
| **React/Vue** | Rich UX | Overkill for 3 components | P1+ |
| **Streamlit** | Rapid prototyping | Less control | Demo only |

**MVP Choice:** Vanilla HTML + JS (you already have `static/index.html`)

---

## Recommended MVP Stack Summary

```
┌────────────────────────────────────────────────────┐
│                 LEVITECH MVP STACK                 │
├────────────────────────────────────────────────────┤
│  Frontend:     Vanilla HTML/JS                     │
│  Backend:      FastAPI (Python 3.11+)              │
│  LLM:          AI-Builders API / OpenAI            │
│  Embeddings:   text-embedding-3-small              │
│  Vector DB:    ChromaDB (local)                    │
│  Keyword:      rank-bm25                           │
│  Doc Extract:  PyMuPDF + python-docx               │
│  Web Fetch:    requests + BeautifulSoup            │
│  Metadata:     JSON files per case                 │
│  Session:      JSON per case (P0) → Redis (P1)     │
└────────────────────────────────────────────────────┘
```

---

## Dependencies to Install

```bash
# Core
uv pip install fastapi uvicorn python-dotenv pydantic

# Document processing (including OCR for scanned PDFs)
uv pip install pymupdf python-docx ocrmypdf

# Vector search
uv pip install chromadb openai

# Hybrid search
uv pip install rank-bm25

# Web scraping (already have)
uv pip install requests beautifulsoup4

# Testing/Eval
uv pip install pytest
```

---

## Security: Path Safety for Case Folders

Prevent directory traversal and cross-case access:

```python
import os
from pathlib import Path

ALLOWED_BASE = Path("/path/to/storage/cases").resolve()

def validate_case_path(case_id: str) -> Path:
    # Block path traversal attempts
    if ".." in case_id or "/" in case_id or "\\" in case_id:
        raise ValueError(f"Invalid case ID: {case_id}")

    case_path = (ALLOWED_BASE / case_id).resolve()

    # Must be under allowed base
    if not str(case_path).startswith(str(ALLOWED_BASE)):
        raise ValueError("Path escape attempt blocked")

    # Block symlinks
    if case_path.is_symlink():
        raise ValueError("Symlinks not allowed")

    return case_path
```

---

## Directory Structure (Proposed)

```
LevitechDemo/
├── main.py                    # FastAPI app
├── config.py                  # Settings, whitelist domains
├── requirements.txt
│
├── services/
│   ├── __init__.py
│   ├── document_processor.py  # PDF/Word extraction + chunking + OCR
│   ├── document_index_service.py  # Chunk provenance + raw text store (separate from vector DB)
│   ├── embedding_service.py   # OpenAI embeddings wrapper
│   ├── chroma_service.py      # Vector DB operations
│   ├── bm25_service.py        # Keyword search + per-doc cap + dedupe
│   ├── legal_retriever.py     # GOV.UK / Caselaw fetcher + snapshot storage
│   ├── legal_cache_service.py # Read/write legal snapshots + hashes
│   ├── citation_validator.py  # 4-check validation including excerpt verify
│   ├── session_manager.py     # Persist session.json per case
│   ├── path_validator.py      # Case folder path safety
│   └── answer_engine.py       # 2-phase RAG orchestration
│
├── models/
│   ├── __init__.py
│   └── schemas.py             # Pydantic models
│
├── storage/
│   ├── cases/
│   │   └── {case_id}/
│   │       ├── metadata.json       # Editable case info
│   │       ├── session.json        # Persisted session state + rolling summary
│   │       └── *.pdf, *.docx
│   └── legal_cache/                # Snapshotted legal sources
│       └── {domain}/{url_hash}/
│           ├── source.html
│           ├── source.txt
│           └── meta.json
│
├── chroma_db/                 # Vector DB persistence
│
├── eval/                      # Evaluation harness
│   ├── run.py                 # Eval runner script
│   └── {case_type}/
│       ├── questions.json     # 10-20 Q/A pairs
│       └── docs/              # Test documents
│
└── static/
    └── index.html             # Minimal UI
```

---

## Key Design Decisions for P0

1. **Two separate retrieval pipelines** - Client docs and legal sources NEVER mix
2. **Citation whitelist enforced at generation time** - Not just filtering
3. **Chunk provenance is sacred** - Every chunk tracks file + page/paragraph
4. **No chat history dependence** - State lives in case metadata + rolling summary (persisted as `session.json`)
5. **Fail loud on citation validation** - Regenerate if any citation fails check
6. **Excerpt verification is mandatory** - Every quoted text must be substring of stored source
7. **Path safety for case folders** - Validate against base dir allowlist, block symlinks
8. **Output contract applies to ALL sources** - Both client docs AND legal sources require quoted excerpts

---

## Citation Validator (Strengthened)

The citation validator performs **4 checks** (all must pass):

```python
def validate_citation(citation, source_cache):
    # 1. ID exists
    if citation.id not in source_cache:
        return False, "Unknown citation ID"

    # 2. URL exists and matches
    source = source_cache[citation.id]  # Provided by legal_cache_service
    if citation.url != source.url:
        return False, "URL mismatch"

    # 3. Domain is whitelisted
    domain = urlparse(citation.url).netloc
    if not any(domain.endswith(w) for w in WHITELIST):
        return False, f"Domain not whitelisted: {domain}"

    # 4. EXCERPT VERIFICATION (Critical!)
    # Quoted text must appear in stored source
    normalized_quote = normalize_whitespace(citation.excerpt)
    normalized_source = normalize_whitespace(source.text)
    if normalized_quote not in normalized_source:
        return False, "Excerpt not found in source"

    return True, "Valid"
```

If any check fails → regenerate with stricter prompt. No exceptions.

---

## Evaluation Harness (Required for >90% Accuracy)

Create a small test set per case type to measure and prevent regressions:

```
/eval/
├── immigration_case_1/
│   ├── questions.json    # 10-20 Q/A pairs
│   └── docs/             # Test documents
└── employment_case_1/
    ├── questions.json
    └── docs/
```

**questions.json format:**
```json
[
  {
    "question": "When did the client start employment?",
    "expected_answer_contains": ["15 March 2023"],
    "expected_source": "employment_contract.pdf",
    "expected_page": 1
  }
]
```

**Run eval:**
```bash
python -m eval.run --case immigration_case_1
# Output: 18/20 correct (90%), 2 failures logged
```

---

## Hybrid Search Improvements

To prevent single-document domination:
- **Per-document cap**: Max 3 chunks per document in top-N results
- **Dedupe by content**: Remove near-duplicate chunks (>90% overlap)
- **Score fusion**: `final_score = 0.5 * bm25_norm + 0.5 * vector_norm`

---

## Next Step

Once you approve this stack, I can scaffold the directory structure and implement the services in order:

1. **Path validator** - Case folder security (prevents traversal attacks)
2. **Document processor** - PDF/Word → chunks with provenance + OCR detection
3. **ChromaDB service** - Store/retrieve embeddings with metadata
4. **BM25 service** - Keyword search with per-doc cap + dedupe
5. **Legal retriever** - Whitelist-only fetching + source snapshot storage
6. **Citation validator** - 4-check validation including excerpt verification
7. **Session manager** - Persist session.json per case (rolling summary)
8. **Answer engine** - 2-phase RAG orchestration
9. **Eval harness** - Test runner for accuracy measurement
