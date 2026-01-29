"""
Path validation service to prevent directory traversal attacks.
"""
from pathlib import Path
from typing import Union
import config


class PathValidationError(Exception):
    """Raised when path validation fails."""
    pass


def validate_case_path(case_id: str) -> Path:
    """
    Validate and return the safe path for a case.

    Args:
        case_id: The case identifier (folder name)

    Returns:
        Resolved Path object for the case directory

    Raises:
        PathValidationError: If case_id contains unsafe characters or path escapes base
    """
    # Block path traversal attempts
    if ".." in case_id:
        raise PathValidationError(f"Invalid case ID: path traversal attempt with '..'")

    if "/" in case_id or "\\" in case_id:
        raise PathValidationError(f"Invalid case ID: contains path separator")

    # Block hidden files/folders
    if case_id.startswith("."):
        raise PathValidationError(f"Invalid case ID: cannot start with '.'")

    # Block empty or whitespace-only
    if not case_id or not case_id.strip():
        raise PathValidationError("Invalid case ID: cannot be empty")

    # Construct and resolve the path
    case_path = (config.CASES_DIR / case_id).resolve()

    # Verify path is under allowed base
    try:
        case_path.relative_to(config.CASES_DIR.resolve())
    except ValueError:
        raise PathValidationError("Path escape attempt blocked: path not under allowed base")

    # Block symlinks
    if case_path.exists() and case_path.is_symlink():
        raise PathValidationError("Symlinks not allowed for case directories")

    return case_path


def validate_file_path(case_id: str, file_name: str) -> Path:
    """
    Validate and return the safe path for a file within a case.

    Args:
        case_id: The case identifier
        file_name: The file name (no path components allowed)

    Returns:
        Resolved Path object for the file

    Raises:
        PathValidationError: If validation fails
    """
    # Validate case first
    case_path = validate_case_path(case_id)

    # Block path components in file name
    if "/" in file_name or "\\" in file_name:
        raise PathValidationError(f"Invalid file name: contains path separator")

    if ".." in file_name:
        raise PathValidationError(f"Invalid file name: path traversal attempt")

    # Block hidden files
    if file_name.startswith("."):
        raise PathValidationError(f"Invalid file name: cannot start with '.'")

    # Construct and verify
    file_path = (case_path / file_name).resolve()

    try:
        file_path.relative_to(case_path)
    except ValueError:
        raise PathValidationError("File path escape attempt blocked")

    if file_path.exists() and file_path.is_symlink():
        raise PathValidationError("Symlinks not allowed for files")

    return file_path


def ensure_case_exists(case_id: str) -> Path:
    """
    Validate case ID and ensure the directory exists.

    Args:
        case_id: The case identifier

    Returns:
        Path to the case directory

    Raises:
        PathValidationError: If case doesn't exist or validation fails
    """
    case_path = validate_case_path(case_id)

    if not case_path.exists():
        raise PathValidationError(f"Case not found: {case_id}")

    if not case_path.is_dir():
        raise PathValidationError(f"Case path is not a directory: {case_id}")

    return case_path
