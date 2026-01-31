"""
Conversation thread management for persisting per-case chat threads.
"""
import json
import re
from datetime import datetime
from typing import Optional
from uuid import uuid4

from models.schemas import (
    ConversationThread,
    EvidenceItem,
    LegalSource,
    LegalSourceSummary,
    ThreadSummary,
    ThreadTurn,
)
from services.path_validator import ensure_case_exists


THREADS_FILE = "threads.json"
MAX_TURNS_PER_THREAD = 10
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "of", "on", "or", "that", "the", "to", "was", "were", "with",
    "you", "your", "i", "we", "they", "he", "she", "them", "their", "this", "those",
    "these", "what", "which", "when", "where", "why", "how", "can", "could", "should",
    "would", "will", "do", "does", "did", "not", "no", "yes",
}


def _threads_path(case_id: str):
    case_path = ensure_case_exists(case_id)
    return case_path / THREADS_FILE


def _summarize_title(text: str) -> str:
    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    keywords = [w for w in words if w not in _STOP_WORDS]
    if not keywords:
        keywords = words
    title = " ".join(keywords[:6]).strip()
    if not title:
        return "New thread"
    if len(title) > 80:
        title = title[:77].rstrip() + "..."
    return title


def _load_raw_threads(case_id: str) -> list[dict]:
    path = _threads_path(case_id)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError) as e:
        print(f"Warning: Corrupted threads.json for {case_id}, starting fresh: {e}")
    return []


def _save_threads(case_id: str, threads: list[ConversationThread]) -> None:
    path = _threads_path(case_id)
    serializable = [t.model_dump(mode="json") for t in threads]
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, default=str)
    temp_path.replace(path)


def load_threads(case_id: str) -> list[ConversationThread]:
    raw = _load_raw_threads(case_id)
    threads: list[ConversationThread] = []
    for item in raw:
        try:
            threads.append(ConversationThread(**item))
        except ValueError:
            continue
    return threads


def list_thread_summaries(case_id: str) -> list[ThreadSummary]:
    threads = load_threads(case_id)
    summaries = [
        ThreadSummary(
            id=t.id,
            title=t.title or "New thread",
            turn_count=len(t.turns),
            updated_at=t.updated_at,
        )
        for t in threads
    ]
    summaries.sort(key=lambda s: s.updated_at, reverse=True)
    return summaries


def create_thread(case_id: str, title: Optional[str] = None) -> ConversationThread:
    threads = load_threads(case_id)
    now = datetime.utcnow()
    thread = ConversationThread(
        id=uuid4().hex,
        title=title or "New thread",
        turns=[],
        created_at=now,
        updated_at=now,
    )
    threads.append(thread)
    _save_threads(case_id, threads)
    return thread


def get_thread(case_id: str, thread_id: str) -> Optional[ConversationThread]:
    threads = load_threads(case_id)
    for thread in threads:
        if thread.id == thread_id:
            return thread
    return None


def append_turn(
    case_id: str,
    thread_id: str,
    question: str,
    answer: str,
    evidence: list[EvidenceItem],
    legal_sources: list[LegalSource],
) -> ConversationThread:
    threads = load_threads(case_id)
    now = datetime.utcnow()
    for idx, thread in enumerate(threads):
        if thread.id == thread_id:
            thread.turns.append(ThreadTurn(question=question, answer=answer, created_at=now))
            if len(thread.turns) > MAX_TURNS_PER_THREAD:
                thread.turns = thread.turns[-MAX_TURNS_PER_THREAD:]
            thread.last_evidence = evidence
            thread.last_legal_sources = [
                LegalSourceSummary(
                    id=s.id,
                    url=s.url,
                    domain=s.domain,
                    title=s.title,
                    excerpt=s.excerpt,
                )
                for s in legal_sources
            ]
            if not thread.title or thread.title == "New thread":
                thread.title = _summarize_title(question)
            thread.updated_at = now
            threads[idx] = thread
            _save_threads(case_id, threads)
            return thread
    raise ValueError(f"Thread not found: {thread_id}")


def delete_thread(case_id: str, thread_id: str) -> None:
    threads = load_threads(case_id)
    remaining = [t for t in threads if t.id != thread_id]
    if len(remaining) == len(threads):
        raise ValueError(f"Thread not found: {thread_id}")
    _save_threads(case_id, remaining)
