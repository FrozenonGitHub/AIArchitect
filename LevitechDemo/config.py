"""
Configuration settings for Levitech MVP.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from parent .env file
load_dotenv(Path(__file__).parent.parent / ".env")

# Base paths
BASE_DIR = Path(__file__).parent.resolve()
STORAGE_BASE = BASE_DIR / "storage"
CASES_DIR = STORAGE_BASE / "cases"
LEGAL_CACHE_DIR = STORAGE_BASE / "legal_cache"
CHROMA_DB_PATH = BASE_DIR / "chroma_db"

# Ensure directories exist
CASES_DIR.mkdir(parents=True, exist_ok=True)
LEGAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)

# AI-Builders API configuration
# Prefer explicit COURSE_API_KEY, fallback to AI_BUILDER_TOKEN injected at deploy time.
AI_BUILDERS_API_KEY = os.getenv("COURSE_API_KEY") or os.getenv("AI_BUILDER_TOKEN")
AI_BUILDERS_BASE_URL = "https://space.ai-builders.com/backend/v1"

# Embedding model
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536

# LLM model
LLM_MODEL = "gpt-5"  # or available model on AI-Builders

# Citation whitelist - ONLY these domains can be cited
WHITELIST_DOMAINS = [
    "acas.org.uk",
    "gov.uk",
    "citizensadvice.org.uk",
]

# Document processing
CHUNK_SIZE_TOKENS = 600  # Target chunk size (500-800 range)
CHUNK_OVERLAP_TOKENS = 100  # Overlap between chunks
OCR_TEXT_THRESHOLD = 100  # Characters per page to trigger OCR

# Search settings
HYBRID_SEARCH_TOP_K = 10
MAX_CHUNKS_PER_DOC = 3  # Per-document cap in results
DEDUPE_SIMILARITY_THRESHOLD = 0.9  # For removing near-duplicates

# Answer generation
MAX_CITATION_RETRIES = 2  # Regeneration attempts if citation fails
