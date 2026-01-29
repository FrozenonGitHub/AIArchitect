"""
Answer engine with 2-phase RAG and citation validation.

Phase A: Retrieval
- Fetch client evidence (hybrid search)
- Fetch legal sources (if needed)

Phase B: Answer Generation
- Generate with strict source constraints
- Validate all citations
- Regenerate if validation fails (max retries)
"""
import json
import re
from typing import Optional
from openai import OpenAI

import config
from models.schemas import (
    AnswerResponse,
    Citation,
    SearchResult,
    LegalSource,
    SessionState,
    EvidenceItem,
)
from services import (
    hybrid_search,
    legal_retriever,
    legal_cache_service,
    citation_validator,
    session_manager,
)


# Initialize LLM client
_llm_client: Optional[OpenAI] = None


def _get_llm_client() -> OpenAI:
    """Get or create the LLM client."""
    global _llm_client
    if _llm_client is None:
        _llm_client = OpenAI(
            api_key=config.AI_BUILDERS_API_KEY,
            base_url=config.AI_BUILDERS_BASE_URL,
        )
    return _llm_client


def _build_system_prompt(
    client_evidence: list[SearchResult],
    legal_sources: list[LegalSource],
    session_context: str,
) -> str:
    """Build the system prompt with source constraints."""
    prompt = """You are a legal assistant helping with case analysis. You MUST follow these rules:

CRITICAL RULES:
1. You may ONLY cite from the sources provided below.
2. Every factual claim MUST include a citation with a quoted excerpt.
3. If information is not in the provided sources, say "This information does not appear in the current case documents."
4. NEVER make up or hallucinate citations.
5. NEVER cite sources not listed below.

CITATION FORMAT:
For client documents:
- Use: [Source: filename.pdf, page X] "quoted text"

For legal sources:
- Use: [Source: URL] "quoted text"

"""

    # Add session context if available
    if session_context:
        prompt += f"CASE CONTEXT (from previous analysis):\n{session_context}\n\n"

    # Add client evidence
    if client_evidence:
        prompt += "CLIENT DOCUMENTS (you may cite from these):\n"
        prompt += "=" * 50 + "\n"
        for i, result in enumerate(client_evidence, 1):
            prov = result.provenance
            location = f"Page {prov.page_num}" if prov.page_num else f"Para {prov.para_idx}"
            prompt += f"\n[{i}] File: {prov.file_name}, {location}\n"
            prompt += f"Content:\n{result.text}\n"
        prompt += "=" * 50 + "\n\n"

    # Add legal sources
    if legal_sources:
        prompt += "LEGAL SOURCES (you may cite from these WHITELISTED domains only):\n"
        prompt += "Allowed domains: " + ", ".join(config.WHITELIST_DOMAINS) + "\n"
        prompt += "=" * 50 + "\n"
        for i, source in enumerate(legal_sources, 1):
            prompt += f"\n[L{i}] URL: {source.url}\n"
            prompt += f"Title: {source.title}\n"
            prompt += f"Content:\n{source.text[:3000]}...\n" if len(source.text) > 3000 else f"Content:\n{source.text}\n"
        prompt += "=" * 50 + "\n"

    return prompt


def _build_stricter_prompt(original_prompt: str, validation_errors: list[str]) -> str:
    """Build a stricter prompt after citation validation failure."""
    error_list = "\n".join(f"- {err}" for err in validation_errors)

    stricter = f"""IMPORTANT: Your previous response had citation errors that MUST be fixed:
{error_list}

REMINDER:
- ONLY quote text that EXACTLY appears in the sources provided
- If you cannot find a supporting quote, DO NOT cite that source
- It is better to say "insufficient information" than to cite incorrectly

"""
    return stricter + original_prompt


def _parse_citations(response_text: str, legal_sources: list[LegalSource], case_id: str) -> list[Citation]:
    """Extract citations from the LLM response."""
    citations = []

    # Pattern for client document citations: [Source: filename.pdf, page X] "quoted text"
    client_pattern = r'\[Source:\s*([^\],]+?)(?:,\s*page\s*(\d+))?\]\s*["""]([^"""]+)["""]'
    for match in re.finditer(client_pattern, response_text, re.IGNORECASE):
        file_name = match.group(1).strip()
        page_num = int(match.group(2)) if match.group(2) else None
        excerpt = match.group(3).strip()

        citations.append(Citation(
            id=f"{file_name}_{page_num or 0}",
            source_type="client",
            file_name=file_name,
            page_num=page_num,
            excerpt=excerpt,
        ))

    # Pattern for legal citations: [Source: URL] "quoted text"
    legal_pattern = r'\[Source:\s*(https?://[^\]]+)\]\s*["""]([^"""]+)["""]'
    for match in re.finditer(legal_pattern, response_text):
        url = match.group(1).strip()
        excerpt = match.group(2).strip()

        # Find matching legal source
        source_id = None
        for source in legal_sources:
            if source.url == url:
                source_id = source.id
                break

        if source_id:
            citations.append(Citation(
                id=source_id,
                source_type="legal",
                url=url,
                excerpt=excerpt,
            ))

    return citations


def generate_answer(
    case_id: str,
    question: str,
    include_legal_sources: bool = True,
) -> AnswerResponse:
    """
    Generate an answer using 2-phase RAG with citation validation.

    Args:
        case_id: The case identifier
        question: The user's question
        include_legal_sources: Whether to search for legal sources

    Returns:
        AnswerResponse with validated citations
    """
    # Phase A: Retrieval

    # Get session context
    session_context = session_manager.get_context_for_prompt(case_id)

    # Search client documents (hybrid search)
    client_evidence = hybrid_search.search(case_id, question, top_k=8)

    # Search legal sources if requested
    legal_sources: list[LegalSource] = []
    if include_legal_sources:
        # Check if question seems to need legal context
        legal_keywords = ["law", "legal", "regulation", "rule", "act", "statute",
                         "immigration", "visa", "tribunal", "court", "judgment"]
        if any(kw in question.lower() for kw in legal_keywords):
            legal_sources = legal_retriever.get_legal_sources_for_query(question)

    # Phase B: Answer Generation with validation loop

    system_prompt = _build_system_prompt(client_evidence, legal_sources, session_context)
    validation_errors: list[str] = []
    evidence_present = bool(client_evidence or legal_sources)

    for attempt in range(config.MAX_CITATION_RETRIES + 1):
        # Adjust prompt for retries
        if attempt > 0 and validation_errors:
            current_prompt = _build_stricter_prompt(system_prompt, validation_errors)
        else:
            current_prompt = system_prompt

        # Call LLM
        client = _get_llm_client()
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[
                {"role": "system", "content": current_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.3,  # Lower temperature for more factual responses
        )

        answer_text = response.choices[0].message.content

        # Parse citations from response
        citations = _parse_citations(answer_text, legal_sources, case_id)

        # Enforce citations only when evidence is present
        if evidence_present and not citations:
            all_valid = False
            errors = ["No citations found despite available evidence."]
        else:
            # Validate all citations
            all_valid, errors = citation_validator.all_citations_valid(case_id, citations)

        if all_valid:
            # Success! Update session and return
            _update_session(case_id, client_evidence, legal_sources)

            return AnswerResponse(
                answer=answer_text,
                client_evidence=client_evidence,
                legal_sources=legal_sources,
                citations=citations,
                citations_valid=True,
                validation_errors=[],
            )

        # Validation failed, prepare for retry
        validation_errors = errors
        print(f"Citation validation failed (attempt {attempt + 1}): {errors}")

    # Max retries exceeded - return with validation warnings
    return AnswerResponse(
        answer=answer_text + "\n\n⚠️ Warning: Some citations could not be verified.",
        client_evidence=client_evidence,
        legal_sources=legal_sources,
        citations=citations,
        citations_valid=False,
        validation_errors=validation_errors,
    )


def _update_session(
    case_id: str,
    client_evidence: list[SearchResult],
    legal_sources: list[LegalSource],
) -> None:
    """Update session state after a successful Q&A turn."""
    # Extract key facts from evidence
    retrieved_facts = [r.text[:200] for r in client_evidence[:5]]

    # Get legal source IDs
    legal_source_ids = [s.id for s in legal_sources]

    session_manager.update_session_with_turn(
        case_id=case_id,
        retrieved_facts=retrieved_facts,
        legal_source_ids=legal_source_ids,
    )


def generate_simple_answer(
    case_id: str,
    question: str,
) -> str:
    """
    Generate a simple answer without full citation validation.
    Useful for quick queries or when validation overhead is not needed.

    Args:
        case_id: The case identifier
        question: The user's question

    Returns:
        Answer text
    """
    response = generate_answer(case_id, question, include_legal_sources=False)
    return response.answer


def format_evidence_for_display(response: AnswerResponse) -> list[EvidenceItem]:
    """
    Format evidence items for UI display.

    Args:
        response: The AnswerResponse

    Returns:
        List of EvidenceItem for display
    """
    items = []

    # Client evidence
    for result in response.client_evidence:
        prov = result.provenance
        items.append(EvidenceItem(
            source_type="client",
            file_name=prov.file_name,
            page_num=prov.page_num,
            excerpt=result.text[:300] + "..." if len(result.text) > 300 else result.text,
        ))

    # Legal sources
    for source in response.legal_sources:
        items.append(EvidenceItem(
            source_type="legal",
            url=source.url,
            domain=source.domain,
            excerpt=source.excerpt,
        ))

    return items
