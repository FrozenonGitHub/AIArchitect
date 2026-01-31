"""
FastAPI application for Levitech MVP.
"""
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

import config
from models.schemas import (
    CaseMetadata,
    CaseCreateRequest,
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    SessionState,
    EvidenceItem,
    ConversationThread,
    ThreadSummary,
)
from services import (
    path_validator,
    session_manager,
    thread_manager,
    document_processor,
    document_index_service,
    chroma_service,
    bm25_service,
    hybrid_search,
    answer_engine,
    legal_retriever,
)

app = FastAPI(
    title="Levitech MVP",
    description="Legal assistant with RAG and citation validation",
    version="0.1.0",
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ============================================================================
# Root & Health
# ============================================================================

@app.get("/")
async def root():
    """Serve the main UI."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Levitech MVP API", "docs": "/docs"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# ============================================================================
# Cases
# ============================================================================

@app.post("/cases", response_model=CaseMetadata)
async def create_case(request: CaseCreateRequest):
    """Create a new case folder."""
    try:
        case_path = path_validator.validate_case_path(request.case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if case_path.exists():
        raise HTTPException(status_code=409, detail=f"Case already exists: {request.case_id}")

    # Create case directory
    case_path.mkdir(parents=True)

    # Create initial metadata
    metadata = CaseMetadata(
        case_id=request.case_id,
        client_name=request.client_name,
        matter_type=request.matter_type,
    )

    # Save metadata
    import json
    metadata_path = case_path / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(mode="json"), f, indent=2, default=str)

    return metadata


@app.get("/cases")
async def list_cases() -> list[dict]:
    """List all cases."""
    cases = []
    for case_dir in config.CASES_DIR.iterdir():
        if case_dir.is_dir() and not case_dir.name.startswith("."):
            metadata_path = case_dir / "metadata.json"
            if metadata_path.exists():
                import json
                with open(metadata_path, "r", encoding="utf-8") as f:
                    cases.append(json.load(f))
            else:
                cases.append({"case_id": case_dir.name})
    return cases


@app.get("/cases/{case_id}", response_model=CaseMetadata)
async def get_case(case_id: str):
    """Get case metadata."""
    try:
        case_path = path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    metadata_path = case_path / "metadata.json"
    if not metadata_path.exists():
        return CaseMetadata(case_id=case_id)

    import json
    with open(metadata_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return CaseMetadata(**data)


@app.put("/cases/{case_id}/metadata", response_model=CaseMetadata)
async def update_case_metadata(case_id: str, metadata: CaseMetadata):
    """Update case metadata."""
    try:
        case_path = path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Ensure case_id matches
    metadata.case_id = case_id

    import json
    from datetime import datetime
    metadata.updated_at = datetime.utcnow()

    metadata_path = case_path / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(mode="json"), f, indent=2, default=str)

    return metadata


# ============================================================================
# Documents
# ============================================================================

@app.post("/cases/{case_id}/upload", response_model=DocumentInfo)
async def upload_document(case_id: str, file: UploadFile = File(...)):
    """Upload and index a document."""
    try:
        case_path = path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Validate file extension
    suffix = Path(file.filename).suffix.lower()
    if suffix not in document_processor.get_supported_extensions():
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: {document_processor.get_supported_extensions()}"
        )

    # Save file (validate file name to prevent traversal)
    try:
        file_path = path_validator.validate_file_path(case_id, file.filename)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Process document
    try:
        chunks = document_processor.process_document(file_path)
    except Exception as e:
        # Clean up on failure
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Document processing failed: {e}")

    # Index chunks
    doc_info = document_index_service.index_document(case_id, file.filename, chunks)

    # Add to vector DB
    chroma_service.add_chunks(case_id, chunks)

    # Invalidate BM25 index
    bm25_service.invalidate_index(case_id)

    return doc_info


@app.get("/cases/{case_id}/documents", response_model=list[DocumentInfo])
async def list_documents(case_id: str):
    """List all documents in a case."""
    try:
        path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return document_index_service.list_documents(case_id)


@app.delete("/cases/{case_id}/documents/{file_name}")
async def delete_document(case_id: str, file_name: str):
    """Delete a document from a case."""
    try:
        file_path = path_validator.validate_file_path(case_id, file_name)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Get chunk IDs before deleting
    index = document_index_service._load_index(case_id)
    doc_data = index["documents"].get(file_name, {})
    chunk_ids = doc_data.get("chunk_ids", [])

    # Delete from vector DB
    if chunk_ids:
        chroma_service.delete_chunks(case_id, chunk_ids)

    # Delete from document index
    document_index_service.delete_document(case_id, file_name)

    # Delete physical file
    if file_path.exists():
        file_path.unlink()

    # Invalidate BM25 index
    bm25_service.invalidate_index(case_id)

    return {"deleted": file_name}


# ============================================================================
# Chat
# ============================================================================

@app.post("/cases/{case_id}/chat", response_model=ChatResponse)
async def chat(case_id: str, request: ChatRequest):
    """
    Main Q&A endpoint with RAG and citation validation.
    """
    try:
        path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Generate answer
    response = answer_engine.generate_answer(
        case_id=case_id,
        question=request.question,
        include_legal_sources=True,
    )

    # Format evidence for display
    evidence = answer_engine.format_evidence_for_display(response)

    thread_id = request.thread_id
    if thread_id:
        try:
            thread = thread_manager.append_turn(
                case_id,
                thread_id,
                request.question,
                response.answer,
                evidence,
                response.legal_sources,
            )
        except ValueError:
            thread = thread_manager.create_thread(case_id)
            thread = thread_manager.append_turn(
                case_id,
                thread.id,
                request.question,
                response.answer,
                evidence,
                response.legal_sources,
            )
    else:
        thread = thread_manager.create_thread(case_id)
        thread = thread_manager.append_turn(
            case_id,
            thread.id,
            request.question,
            response.answer,
            evidence,
            response.legal_sources,
        )

    return ChatResponse(
        answer=response.answer,
        evidence=evidence,
        legal_sources=response.legal_sources,
        session_updated=True,
        thread_id=thread.id,
        thread_title=thread.title,
        thread_turn_count=len(thread.turns),
    )


# ============================================================================
# Session
# ============================================================================

@app.get("/cases/{case_id}/session", response_model=SessionState)
async def get_session(case_id: str):
    """Get current session state for a case."""
    try:
        path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return session_manager.load_session(case_id)


@app.delete("/cases/{case_id}/session")
async def reset_session(case_id: str):
    """Reset the session state for a case."""
    try:
        case_path = path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    session_path = case_path / "session.json"
    if session_path.exists():
        session_path.unlink()

    return {"status": "session reset"}


# ============================================================================
# Threads
# ============================================================================

@app.get("/cases/{case_id}/threads", response_model=list[ThreadSummary])
async def list_threads(case_id: str):
    """List conversation threads for a case."""
    try:
        path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return thread_manager.list_thread_summaries(case_id)


@app.post("/cases/{case_id}/threads", response_model=ConversationThread)
async def create_thread(case_id: str):
    """Create a new conversation thread for a case."""
    try:
        path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return thread_manager.create_thread(case_id)


@app.get("/cases/{case_id}/threads/{thread_id}", response_model=ConversationThread)
async def get_thread(case_id: str, thread_id: str):
    """Get a single conversation thread."""
    try:
        path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    thread = thread_manager.get_thread(case_id, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail=f"Thread not found: {thread_id}")
    return thread


@app.delete("/cases/{case_id}/threads/{thread_id}")
async def delete_thread(case_id: str, thread_id: str):
    """Delete a conversation thread."""
    try:
        path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        thread_manager.delete_thread(case_id, thread_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"deleted": thread_id}


# ============================================================================
# Search
# ============================================================================

@app.post("/cases/{case_id}/search")
async def search_documents(case_id: str, query: str = Form(...), top_k: int = Form(10)):
    """Search within case documents."""
    try:
        path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        raise HTTPException(status_code=404, detail=str(e))

    results = hybrid_search.search(case_id, query, top_k=top_k)

    return {
        "query": query,
        "results": [
            {
                "chunk_id": r.chunk_id,
                "text": r.text,
                "score": r.score,
                "file_name": r.provenance.file_name,
                "page_num": r.provenance.page_num,
            }
            for r in results
        ],
    }


@app.post("/search/legal")
async def search_legal_sources(query: str = Form(...)):
    """Search legal sources (standalone, not case-specific)."""
    try:
        sources = legal_retriever.get_legal_sources_for_query(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Legal search failed: {e}")

    return {
        "query": query,
        "sources": [
            {
                "id": s.id,
                "url": s.url,
                "title": s.title,
                "domain": s.domain,
                "excerpt": s.excerpt,
            }
            for s in sources
        ],
    }


# ============================================================================
# Run with: uvicorn main:app --reload
# ============================================================================

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
