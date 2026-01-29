"""
Evaluation harness for testing answer accuracy and citation validity.

Usage:
    python -m eval.run --case test_immigration
    python -m eval.run --case test_employment --verbose

Questions file format (questions.json):
[
    {
        "question": "When did the client start employment?",
        "expected_answer_contains": ["15 March 2023"],
        "expected_source": "employment_contract.pdf",
        "expected_page": 1
    }
]
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import answer_engine, path_validator


class EvalResult:
    """Result of a single evaluation."""
    def __init__(
        self,
        question: str,
        expected: dict,
        answer: str,
        correct: bool,
        citation_valid: bool,
        source_matched: bool,
        errors: list[str],
    ):
        self.question = question
        self.expected = expected
        self.answer = answer
        self.correct = correct
        self.citation_valid = citation_valid
        self.source_matched = source_matched
        self.errors = errors


def load_questions(eval_dir: Path) -> list[dict]:
    """Load questions from eval directory."""
    questions_path = eval_dir / "questions.json"
    if not questions_path.exists():
        raise FileNotFoundError(f"Questions file not found: {questions_path}")

    with open(questions_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_answer_contains(answer: str, expected_items: list[str]) -> tuple[bool, list[str]]:
    """Check if answer contains expected items."""
    answer_lower = answer.lower()
    missing = []

    for item in expected_items:
        if item.lower() not in answer_lower:
            missing.append(item)

    return len(missing) == 0, missing


def check_source_cited(
    response,
    expected_source: Optional[str],
    expected_page: Optional[int],
) -> tuple[bool, str]:
    """Check if expected source was cited."""
    if not expected_source:
        return True, ""

    for result in response.client_evidence:
        if expected_source.lower() in result.provenance.file_name.lower():
            if expected_page is None or result.provenance.page_num == expected_page:
                return True, ""

    return False, f"Expected source not found: {expected_source}" + (f" page {expected_page}" if expected_page else "")


def run_single_eval(case_id: str, question_data: dict, verbose: bool = False) -> EvalResult:
    """Run evaluation for a single question."""
    question = question_data["question"]
    expected_contains = question_data.get("expected_answer_contains", [])
    expected_source = question_data.get("expected_source")
    expected_page = question_data.get("expected_page")

    errors = []

    if verbose:
        print(f"\n  Q: {question}")

    try:
        response = answer_engine.generate_answer(case_id, question, include_legal_sources=False)
        answer = response.answer
    except Exception as e:
        errors.append(f"Answer generation failed: {e}")
        return EvalResult(
            question=question,
            expected=question_data,
            answer="",
            correct=False,
            citation_valid=False,
            source_matched=False,
            errors=errors,
        )

    if verbose:
        print(f"  A: {answer[:200]}...")

    # Check answer content
    content_ok, missing = check_answer_contains(answer, expected_contains)
    if not content_ok:
        errors.append(f"Missing expected content: {missing}")

    # Check citations valid
    citation_valid = response.citations_valid
    if not citation_valid:
        errors.extend(response.validation_errors)

    # Check source cited
    source_matched, source_error = check_source_cited(response, expected_source, expected_page)
    if not source_matched:
        errors.append(source_error)

    correct = content_ok and citation_valid and source_matched

    if verbose:
        status = "PASS" if correct else "FAIL"
        print(f"  Status: {status}")
        if errors:
            for err in errors:
                print(f"    - {err}")

    return EvalResult(
        question=question,
        expected=question_data,
        answer=answer,
        correct=correct,
        citation_valid=citation_valid,
        source_matched=source_matched,
        errors=errors,
    )


def run_eval(case_id: str, verbose: bool = False) -> dict:
    """Run full evaluation for a case."""
    # Verify case exists
    try:
        path_validator.ensure_case_exists(case_id)
    except path_validator.PathValidationError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Find eval directory
    eval_base = Path(__file__).parent
    eval_dir = eval_base / case_id

    if not eval_dir.exists():
        # Try without prefix
        for d in eval_base.iterdir():
            if d.is_dir() and case_id in d.name:
                eval_dir = d
                break

    if not eval_dir.exists():
        print(f"Error: Eval directory not found for case: {case_id}")
        print(f"Expected at: {eval_base / case_id}")
        sys.exit(1)

    # Load questions
    try:
        questions = load_questions(eval_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"\nRunning evaluation for case: {case_id}")
    print(f"Questions: {len(questions)}")
    print("=" * 60)

    # Run evaluations
    results = []
    for i, q in enumerate(questions, 1):
        print(f"\n[{i}/{len(questions)}] Evaluating...")
        result = run_single_eval(case_id, q, verbose)
        results.append(result)

    # Calculate metrics
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    citation_valid = sum(1 for r in results if r.citation_valid)
    source_matched = sum(1 for r in results if r.source_matched)

    accuracy = (correct / total * 100) if total > 0 else 0
    citation_rate = (citation_valid / total * 100) if total > 0 else 0
    source_rate = (source_matched / total * 100) if total > 0 else 0

    # Print summary
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Total questions: {total}")
    print(f"Correct answers: {correct}/{total} ({accuracy:.1f}%)")
    print(f"Valid citations: {citation_valid}/{total} ({citation_rate:.1f}%)")
    print(f"Source matches:  {source_matched}/{total} ({source_rate:.1f}%)")

    # Target check
    if accuracy >= 90:
        print("\n TARGET MET: >90% accuracy achieved!")
    else:
        print(f"\n TARGET NOT MET: Need {90 - accuracy:.1f}% more accuracy")

    # List failures
    failures = [r for r in results if not r.correct]
    if failures:
        print("\nFAILED QUESTIONS:")
        for i, r in enumerate(failures, 1):
            print(f"\n  {i}. {r.question}")
            for err in r.errors:
                print(f"     - {err}")

    # Save results
    output = {
        "case_id": case_id,
        "timestamp": datetime.utcnow().isoformat(),
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "citation_valid": citation_valid,
        "source_matched": source_matched,
        "failures": [
            {
                "question": r.question,
                "errors": r.errors,
                "answer_preview": r.answer[:200],
            }
            for r in failures
        ],
    }

    output_path = eval_dir / f"results_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {output_path}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Run evaluation harness")
    parser.add_argument("--case", required=True, help="Case ID to evaluate")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()
    run_eval(args.case, args.verbose)


if __name__ == "__main__":
    main()
