# LevitechDemo - Legal AI Assistant MVP

A RAG-based legal assistant that retrieves facts from client documents and cites only whitelisted UK legal sources.

## Quick Start

```bash
cd /Users/wzmacbook/myProj/AIArchitect/LevitechDemo

# Install dependencies
source ../.venv/bin/activate
uv pip install -r requirements.txt

# Optional: OCR support for scanned PDFs
brew install tesseract ghostscript

# Run the server
uvicorn main:app --reload
```

Open http://127.0.0.1:8000 in your browser.

---

## Project Structure

```
LevitechDemo/
├── main.py                 # FastAPI app (15+ endpoints)
├── config.py               # Settings, whitelist domains, API config
├── requirements.txt
│
├── models/
│   └── schemas.py          # Pydantic models (CaseMetadata, Citation, etc.)
│
├── services/               # Core business logic (12 files)
│   ├── path_validator.py       # Security: prevents directory traversal
│   ├── session_manager.py      # Persists session.json per case
│   ├── legal_cache_service.py  # Stores/retrieves legal source snapshots
│   ├── document_processor.py   # PDF/Word extraction + OCR detection
│   ├── document_index_service.py # Chunk provenance storage
│   ├── embedding_service.py    # AI-Builders API embeddings
│   ├── chroma_service.py       # Vector DB operations
│   ├── bm25_service.py         # Keyword search with per-doc cap
│   ├── hybrid_search.py        # Combined BM25 + vector search
│   ├── legal_retriever.py      # Whitelist-enforced fetching
│   ├── citation_validator.py   # 4-check validation
│   └── answer_engine.py        # 2-phase RAG with validation loop
│
├── static/
│   └── index.html          # Minimal UI
│
├── eval/
│   └── run.py              # Accuracy testing harness
│
├── storage/                # Runtime data (gitignored)
│   ├── cases/{case_id}/    # Case docs + metadata.json + session.json
│   └── legal_cache/        # Cached legal sources
│
└── chroma_db/              # Vector DB persistence
```

---

## Key Design Principles

### Citation Whitelist (Enforced)
Only these domains can be cited:
- `acas.org.uk`
- `gov.uk`
- `citizensadvice.org.uk`

### 4-Check Citation Validation
Every citation must pass:
1. ID exists in source cache
2. URL matches stored URL
3. Domain is whitelisted
4. Excerpt found in stored source text

### Two Separate Pipelines
- **Client Documents** → Hybrid search (BM25 + vector)
- **Legal Sources** → Whitelist-enforced web fetch + cache

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | UI |
| GET | `/health` | Health check |
| POST | `/cases` | Create case |
| GET | `/cases` | List cases |
| GET | `/cases/{id}` | Get case details |
| POST | `/cases/{id}/upload` | Upload document |
| POST | `/cases/{id}/chat` | Ask question (main RAG) |
| POST | `/cases/{id}/search` | Hybrid search |
| GET | `/cases/{id}/session` | Get session state |
| POST | `/search/legal` | Standalone legal search |

---

## Running Evaluation

```bash
python -m eval.run --case <case_id> [--verbose]
```

Target: >90% accuracy on client fact retrieval, 100% verifiable citations.

---

## Documentation

- **[P0_Roadmap.md](P0_Roadmap.md)** - Step-by-step implementation plan
- **[TechStack.md](TechStack.md)** - Architecture and technology decisions

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI |
| Vector DB | ChromaDB |
| Keyword Search | rank-bm25 |
| Embeddings | AI-Builders API |
| LLM | AI-Builders API |
| Doc Processing | PyMuPDF, python-docx, OCRmyPDF |
| Frontend | Vanilla HTML/JS |
