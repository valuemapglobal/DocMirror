#!/usr/bin/env python3
"""PDF/UA Compliance Validator (GA1.0-ODL-02 Phase 2).

Validates a PDF file for PDF/UA-1 or PDF/UA-2 compliance.

Usage:
    python scripts/validate_pdfua.py input.pdf [--version UA-1|UA-2]

If veraPDF (https://verapdf.org) is installed, it is used for authoritative
validation. Otherwise, a basic structural check is performed using PyMuPDF.

Returns exit code 0 if compliant, 1 if non-compliant, 2 if validation skipped.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _check_pymupdf_tagging(pdf_path: Path) -> dict:
    """Basic structural check using PyMuPDF's tagging API.

    Checks:
      1. Document has a structure tree (is tagged)
      2. Document has /MarkInfo with /Marked true
      3. Document has /Lang set

    Returns dict with 'passed' (bool), 'checks' (list), and 'errors' (list).
    """
    checks: list[dict] = []
    errors: list[str] = []

    try:
        import fitz
    except ImportError:
        return {
            "passed": False,
            "checks": [],
            "errors": ["PyMuPDF not installed. Install with: pip install PyMuPDF>=1.23.0"],
        }

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return {
            "passed": False,
            "checks": [],
            "errors": [f"Cannot open PDF: {e}"],
        }

    # Check 1: Structure tree existence
    try:
        struct = doc.pdf_structure()
        has_struct = struct is not None
    except Exception:
        has_struct = False
    checks.append({
        "name": "Structure tree exists",
        "passed": has_struct,
        "detail": "Document has PDF structure tree (required for tagging)",
    })
    if not has_struct:
        errors.append("No structure tree found — document is not tagged")

    # Check 2: MarkInfo / Marked
    try:
        xref = doc.pdf_catalog()
        mark_info = doc.xref_get_key(xref, "MarkInfo")
        marked = mark_info and "true" in str(mark_info[1]).lower() if mark_info else False
    except Exception:
        marked = False
    checks.append({
        "name": "MarkInfo.Marked = true",
        "passed": marked,
        "detail": "Document /MarkInfo indicates tagged structure",
    })
    if not marked:
        errors.append("MarkInfo.Marked is not set to true — document is not recognized as tagged")

    # Check 3: Language metadata
    try:
        lang = doc.metadata.get("language", "") if hasattr(doc, "metadata") else ""
        has_lang = bool(lang)
    except Exception:
        has_lang = False
    checks.append({
        "name": "Document language set",
        "passed": has_lang,
        "detail": f"Language: {lang or '(not set)'}",
    })
    if not has_lang:
        errors.append("Document language is not set — required for PDF/UA")

    # Check 4: Page count
    page_count = len(doc) if doc else 0
    checks.append({
        "name": "Has pages",
        "passed": page_count > 0,
        "detail": f"Pages: {page_count}",
    })

    doc.close()

    return {
        "passed": len(errors) == 0,
        "checks": checks,
        "errors": errors,
    }


def _check_verapdf(pdf_path: Path, version: str) -> dict | None:
    """Run veraPDF validation if available.

    Returns None if veraPDF is not installed.
    """
    # Check for veraPDF CLI
    verapdf_cmd = shutil.which("verapdf")
    if not verapdf_cmd:
        return None

    # Map version to veraPDF profile
    profile = "1" if version == "UA-1" else "2"

    try:
        result = subprocess.run(
            [verapdf_cmd, "--format", "json", "--flavour", f"ua{profile}", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        data = json.loads(result.stdout)

        # Extract summary from veraPDF JSON output
        jobs = data.get("jobs", [])
        if not jobs:
            return None

        job = jobs[0]
        validation_report = job.get("validationReport", {})
        details = job.get("details", {})

        passed = validation_report.get("result", "") == "PASSED"
        checks = []
        errors = []

        if passed:
            checks.append({
                "name": f"PDF/{version} Compliance",
                "passed": True,
                "detail": "Passed veraPDF validation",
            })
        else:
            error_count = sum(
                len(v)
                for k, v in details.items()
                if k in ("failedRules", "failedChecks")
            )
            errors.append(
                f"PDF/{version} validation failed: {error_count} issues found"
            )
            # Log first few errors
            for rule_list in details.get("failedRules", [])[:5]:
                if isinstance(rule_list, dict):
                    errors.append(f"  Rule: {rule_list.get('rule', 'unknown')}")

        return {
            "passed": passed,
            "checks": checks,
            "errors": errors,
            "validator": "veraPDF",
        }

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        return {
            "passed": False,
            "checks": [],
            "errors": [f"veraPDF validation error: {e}"],
            "validator": "veraPDF",
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate PDF/UA compliance of a PDF file."
    )
    parser.add_argument("input", type=Path, help="Path to PDF file")
    parser.add_argument(
        "--version",
        choices=["UA-1", "UA-2"],
        default="UA-1",
        help="PDF/UA specification version (default: UA-1)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()

    pdf_path: Path = args.input
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        return 2

    # Try veraPDF first (authoritative), fall back to structural check
    result = _check_verapdf(pdf_path, args.version)
    if result is None:
        result = _check_pymupdf_tagging(pdf_path)
        result["validator"] = "pymupdf_structural"
        result["note"] = "Basic structural check (install veraPDF for authoritative validation)"

    result["version"] = args.version
    result["file"] = str(pdf_path.resolve())

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_human(result)

    return 0 if result["passed"] else 1


def _print_human(result: dict) -> None:
    """Print human-readable validation report."""
    print(f"\n{'='*60}")
    print(f"  PDF/UA Compliance Report")
    print(f"{'='*60}")
    print(f"  File:     {result.get('file', 'unknown')}")
    print(f"  Version:  {result.get('version', 'UA-1')}")
    print(f"  Tool:     {result.get('validator', 'unknown')}")
    print(f"  Result:   {'✅ PASSED' if result['passed'] else '❌ FAILED'}")
    print(f"{'='*60}")

    for check in result.get("checks", []):
        status = "✅" if check.get("passed") else "❌"
        print(f"  {status} {check['name']}")
        print(f"     {check.get('detail', '')}")

    for error in result.get("errors", []):
        print(f"  ❌ {error}")

    note = result.get("note", "")
    if note:
        print(f"\n  ℹ️  {note}")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    sys.exit(main())
