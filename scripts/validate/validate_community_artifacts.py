#!/usr/bin/env python3
"""Validate a persisted Community JSON/Markdown/Dataset Bundle as one contract."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from docmirror.models.schemas.registry import validate_projection_payload
from docmirror.output.markdown_renderer import MARKDOWN_PROFILE_MARKER, validate_markdown

_TOP_LEVEL_BLOCKS = {"schema", "document", "sections", "datasets", "files", "warnings"}
_RECORD_BLOCKS = {"record_id", "normalized", "canonical_raw", "raw", "source"}
_AUDIT_COLUMNS = {
    "dataset_id",
    "record_id",
    "field_key",
    "value",
    "raw",
    "value_type",
    "unit",
    "page_start",
    "page_end",
    "bbox",
    "confidence",
    "evidence_ref",
    "csv_escape_applied",
}
PAYMENT_DIRECTIONS = ("收入", "支出", "其他", "不计收支")


class _FirstTableCellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.td = Counter()
        self.th = Counter()
        self._in_row = False
        self._capturing = False
        self._captured = False
        self._tag = ""
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag == "tr":
            self._in_row = True
            self._captured = False
        elif self._in_row and not self._captured and tag in {"td", "th"}:
            self._capturing = True
            self._captured = True
            self._tag = tag
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._capturing and tag == self._tag:
            value = "".join(self._parts)
            value = "".join(value.split())
            getattr(self, self._tag)[value] += 1
            self._capturing = False
        if tag == "tr":
            self._in_row = False
            self._capturing = False

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)


def payment_direction_cells(markdown: str) -> tuple[Counter[str], Counter[str]]:
    """Return payment-direction counts in ordinary and header cells."""
    parser = _FirstTableCellParser()
    parser.feed(markdown)
    parser.close()

    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        cells = _gfm_table_cells(line)
        if cells is None or _is_gfm_separator(cells):
            continue
        next_cells = _gfm_table_cells(lines[index + 1]) if index + 1 < len(lines) else None
        target = parser.th if next_cells is not None and _is_gfm_separator(next_cells) else parser.td
        target["".join(cells[0].split())] += 1
    return parser.td, parser.th


def _gfm_table_cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped[1:-1]:
        if char == "|" and not escaped:
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
        if char == "\\" and not escaped:
            escaped = True
        else:
            escaped = False
    cells.append("".join(current).strip())
    return cells


def _is_gfm_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _companion_path(root: Path, relative: Any, label: str, issues: list[str]) -> Path | None:
    if not isinstance(relative, str) or not relative:
        issues.append(f"{label}: missing relative path")
        return None
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root.resolve()):
        issues.append(f"{label}: path escapes artifact directory: {relative}")
        return None
    if not candidate.is_file():
        issues.append(f"{label}: file not found: {relative}")
        return None
    return candidate


def validate_community_artifacts(community_path: str | Path) -> list[str]:
    """Return all violations across Community JSON, Markdown, wide CSVs and audit CSV."""
    path = Path(community_path).resolve()
    issues: list[str] = []
    if not path.is_file():
        return [f"community: file not found: {path}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"community: invalid JSON: {exc}"]
    if not isinstance(payload, dict):
        return ["community: top level must be an object"]

    validation = validate_projection_payload("community", payload)
    issues.extend(f"schema: {error}" for error in validation.errors)
    if set(payload) != _TOP_LEVEL_BLOCKS:
        issues.append(f"community: top-level blocks={sorted(payload)}")

    root = path.parent
    files = payload.get("files") if isinstance(payload.get("files"), dict) else {}
    content_path = _companion_path(root, files.get("content_md"), "content", issues)
    audit_path = _companion_path(root, files.get("dataset_audit_csv"), "audit", issues)

    datasets = payload.get("datasets") if isinstance(payload.get("datasets"), list) else []
    dataset_ids: set[str] = set()
    dataset_record_ids: dict[str, set[str]] = {}
    expected_audited_ids: dict[str, set[str]] = {}
    for index, dataset in enumerate(datasets):
        if not isinstance(dataset, dict):
            issues.append(f"dataset[{index}]: must be an object")
            continue
        dataset_id = str(dataset.get("id") or f"dataset[{index}]")
        if dataset_id in dataset_ids:
            issues.append(f"{dataset_id}: duplicate dataset id")
        dataset_ids.add(dataset_id)

        rows = dataset.get("rows") if isinstance(dataset.get("rows"), list) else []
        row_count = dataset.get("row_count")
        completeness = dataset.get("completeness") if isinstance(dataset.get("completeness"), dict) else {}
        emitted = completeness.get("emitted_row_count")
        expected = completeness.get("expected_row_count")
        omitted = completeness.get("omitted_row_count")
        if row_count != len(rows) or emitted != len(rows):
            issues.append(f"{dataset_id}: JSON count mismatch row_count={row_count} emitted={emitted} rows={len(rows)}")
        if isinstance(expected, int) and isinstance(emitted, int):
            expected_omitted = max(0, expected - emitted)
            if omitted != expected_omitted:
                issues.append(f"{dataset_id}: omitted_row_count={omitted}, expected={expected_omitted}")
            verified = completeness.get("verified")
            if verified is not (expected == emitted):
                issues.append(f"{dataset_id}: completeness.verified contradicts expected/emitted counts")

        record_ids: list[str] = []
        audited_ids: set[str] = set()
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                issues.append(f"{dataset_id}.rows[{row_index}]: must be an object")
                continue
            missing = _RECORD_BLOCKS - set(row)
            if missing:
                issues.append(f"{dataset_id}.rows[{row_index}]: missing {sorted(missing)}")
            record_id = str(row.get("record_id") or "")
            record_ids.append(record_id)
            if not record_id:
                issues.append(f"{dataset_id}.rows[{row_index}]: empty record_id")
            for block in ("normalized", "canonical_raw", "raw", "source"):
                if not isinstance(row.get(block), dict):
                    issues.append(f"{dataset_id}.rows[{row_index}].{block}: must be an object")
            normalized = row.get("normalized") if isinstance(row.get("normalized"), dict) else {}
            if any(value not in (None, "", [], {}) for value in normalized.values()) and record_id:
                audited_ids.add(record_id)
        if len(record_ids) != len(set(record_ids)):
            issues.append(f"{dataset_id}: duplicate record_id")
        dataset_record_ids[dataset_id] = set(record_ids)
        expected_audited_ids[dataset_id] = audited_ids

        csv_path = _companion_path(root, dataset.get("csv"), f"{dataset_id}.csv", issues)
        if csv_path is None:
            continue
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            csv_rows = list(csv.DictReader(stream))
        csv_ids = [str(row.get("record_id") or "") for row in csv_rows]
        if len(csv_rows) != len(rows):
            issues.append(f"{dataset_id}: CSV rows={len(csv_rows)}, JSON rows={len(rows)}")
        if csv_ids != record_ids:
            issues.append(f"{dataset_id}: ordered record_id mismatch between JSON and CSV")

    if content_path is not None:
        markdown = content_path.read_text(encoding="utf-8")
        if not markdown.strip():
            issues.append("content: Markdown is empty")
        if MARKDOWN_PROFILE_MARKER not in markdown:
            issues.append("content: DMP profile marker missing")
        issues.extend(f"content: {issue}" for issue in validate_markdown(markdown))

    if audit_path is not None:
        with audit_path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            audit_rows = list(reader)
            audit_columns = set(reader.fieldnames or [])
        if audit_columns != _AUDIT_COLUMNS:
            issues.append(f"audit: columns={sorted(audit_columns)}")
        seen_audited_ids: dict[str, set[str]] = {dataset_id: set() for dataset_id in dataset_ids}
        for row_index, row in enumerate(audit_rows):
            dataset_id = str(row.get("dataset_id") or "")
            record_id = str(row.get("record_id") or "")
            if dataset_id not in dataset_record_ids:
                issues.append(f"audit[{row_index}]: unknown dataset_id={dataset_id}")
                continue
            if record_id not in dataset_record_ids[dataset_id]:
                issues.append(f"audit[{row_index}]: unknown record_id={record_id}")
            seen_audited_ids[dataset_id].add(record_id)
        for dataset_id, expected_ids in expected_audited_ids.items():
            missing_ids = expected_ids - seen_audited_ids.get(dataset_id, set())
            if missing_ids:
                issues.append(f"{dataset_id}: {len(missing_ids)} records missing from audit CSV")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("community_json", type=Path, help="Path to <file_id>_community.json")
    parser.add_argument(
        "--payment-markdown-parity",
        action="store_true",
        help="Require every payment JSON record to appear as a Markdown data row, not a header row.",
    )
    args = parser.parse_args()
    issues = validate_community_artifacts(args.community_json)
    if args.payment_markdown_parity and not issues:
        payload = json.loads(args.community_json.read_text(encoding="utf-8"))
        markdown_path = args.community_json.parent / payload["files"]["content_md"]
        td, th = payment_direction_cells(markdown_path.read_text(encoding="utf-8"))
        transaction_rows = sum(td[direction] for direction in PAYMENT_DIRECTIONS)
        header_rows = sum(th[direction] for direction in PAYMENT_DIRECTIONS)
        payment_datasets = [dataset for dataset in payload["datasets"] if dataset.get("type") == "transaction"]
        expected_rows = sum(int(dataset.get("row_count") or 0) for dataset in payment_datasets)
        if transaction_rows != expected_rows:
            issues.append(f"content: payment data rows={transaction_rows}, JSON rows={expected_rows}")
        if header_rows:
            issues.append(f"content: {header_rows} payment records rendered as header cells")
    if issues:
        for issue in issues:
            print(f"ERROR {issue}")
        return 1
    print(f"OK {args.community_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
