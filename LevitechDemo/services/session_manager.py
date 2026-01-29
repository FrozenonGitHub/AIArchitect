"""
Session management service for persisting case state.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from models.schemas import SessionState, RollingSummary
from services.path_validator import validate_case_path, ensure_case_exists


SESSION_FILE = "session.json"


def load_session(case_id: str) -> SessionState:
    """
    Load session state for a case, or create a new one if none exists.

    Args:
        case_id: The case identifier

    Returns:
        SessionState object (new or loaded from disk)
    """
    case_path = ensure_case_exists(case_id)
    session_path = case_path / SESSION_FILE

    if session_path.exists():
        try:
            with open(session_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SessionState(**data)
        except (json.JSONDecodeError, ValueError) as e:
            # Corrupted session file - start fresh but log
            print(f"Warning: Corrupted session.json for {case_id}, starting fresh: {e}")

    # Return new session
    return SessionState(case_id=case_id)


def save_session(case_id: str, state: SessionState) -> None:
    """
    Save session state to disk.

    Args:
        case_id: The case identifier
        state: SessionState to persist
    """
    case_path = ensure_case_exists(case_id)
    session_path = case_path / SESSION_FILE

    # Update timestamp
    state.updated_at = datetime.utcnow()

    # Write atomically (write to temp, then rename)
    temp_path = session_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state.model_dump(mode="json"), f, indent=2, default=str)

    temp_path.replace(session_path)


def update_session_with_turn(
    case_id: str,
    retrieved_facts: list[str],
    legal_source_ids: list[str],
) -> SessionState:
    """
    Update session state after a Q&A turn.

    Args:
        case_id: The case identifier
        retrieved_facts: New facts retrieved in this turn
        legal_source_ids: IDs of legal sources used

    Returns:
        Updated SessionState
    """
    state = load_session(case_id)

    # Append new facts (keep last 20)
    state.retrieved_facts = (state.retrieved_facts + retrieved_facts)[-20:]

    # Append legal sources (keep unique)
    existing = set(state.legal_sources_used)
    for src_id in legal_source_ids:
        if src_id not in existing:
            state.legal_sources_used.append(src_id)

    state.turn_count += 1
    save_session(case_id, state)

    return state


def update_rolling_summary(
    case_id: str,
    client_background: Optional[str] = None,
    chronology_item: Optional[str] = None,
    legal_issue: Optional[str] = None,
    source_reference: Optional[str] = None,
) -> SessionState:
    """
    Update the rolling summary for a case.

    Args:
        case_id: The case identifier
        client_background: New background text (replaces existing)
        chronology_item: New item to add to chronology
        legal_issue: New legal issue to add
        source_reference: New source reference to add

    Returns:
        Updated SessionState
    """
    state = load_session(case_id)
    summary = state.rolling_summary

    if client_background is not None:
        summary.client_background = client_background

    if chronology_item and chronology_item not in summary.key_chronology:
        summary.key_chronology.append(chronology_item)

    if legal_issue and legal_issue not in summary.legal_issues_identified:
        summary.legal_issues_identified.append(legal_issue)

    if source_reference and source_reference not in summary.source_references:
        summary.source_references.append(source_reference)

    summary.version += 1
    summary.updated_at = datetime.utcnow()
    state.rolling_summary = summary

    save_session(case_id, state)
    return state


def get_context_for_prompt(case_id: str) -> str:
    """
    Get formatted context from session state for including in LLM prompt.

    Args:
        case_id: The case identifier

    Returns:
        Formatted string with rolling summary and recent facts
    """
    state = load_session(case_id)
    summary = state.rolling_summary

    parts = []

    if summary.client_background:
        parts.append(f"Client Background:\n{summary.client_background}")

    if summary.key_chronology:
        parts.append("Key Chronology:\n" + "\n".join(f"- {item}" for item in summary.key_chronology))

    if summary.legal_issues_identified:
        parts.append("Legal Issues Identified:\n" + "\n".join(f"- {issue}" for issue in summary.legal_issues_identified))

    if state.retrieved_facts:
        # Include last 5 recent facts
        recent = state.retrieved_facts[-5:]
        parts.append("Recent Retrieved Facts:\n" + "\n".join(f"- {fact[:200]}..." if len(fact) > 200 else f"- {fact}" for fact in recent))

    return "\n\n".join(parts) if parts else ""
