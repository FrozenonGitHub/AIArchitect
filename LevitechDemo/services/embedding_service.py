"""
Embedding service using AI-Builders API (OpenAI-compatible).
"""
from typing import Optional
from openai import OpenAI

import config


# Initialize client with AI-Builders endpoint
_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    """Get or create the OpenAI client."""
    global _client
    if _client is None:
        if not config.AI_BUILDERS_API_KEY:
            raise ValueError("COURSE_API_KEY not set in environment")
        _client = OpenAI(
            api_key=config.AI_BUILDERS_API_KEY,
            base_url=config.AI_BUILDERS_BASE_URL,
        )
    return _client


def embed_text(text: str) -> list[float]:
    """
    Generate embedding for a single text.

    Args:
        text: The text to embed

    Returns:
        Embedding vector as list of floats
    """
    client = _get_client()

    # Clean and truncate text if needed
    text = text.strip()
    if not text:
        # Return zero vector for empty text
        return [0.0] * config.EMBEDDING_DIMENSION

    response = client.embeddings.create(
        model=config.EMBEDDING_MODEL,
        input=text,
    )

    return response.data[0].embedding


def embed_batch(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.

    Args:
        texts: List of texts to embed
        batch_size: Number of texts per API call

    Returns:
        List of embedding vectors
    """
    client = _get_client()
    all_embeddings = []

    # Clean texts
    cleaned_texts = [t.strip() if t.strip() else " " for t in texts]

    # Process in batches
    for i in range(0, len(cleaned_texts), batch_size):
        batch = cleaned_texts[i:i + batch_size]

        response = client.embeddings.create(
            model=config.EMBEDDING_MODEL,
            input=batch,
        )

        # Sort by index to maintain order
        sorted_data = sorted(response.data, key=lambda x: x.index)
        batch_embeddings = [d.embedding for d in sorted_data]
        all_embeddings.extend(batch_embeddings)

    return all_embeddings


def get_embedding_dimension() -> int:
    """Get the dimension of embeddings produced by the model."""
    return config.EMBEDDING_DIMENSION
