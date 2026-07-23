# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Structure signal detectors for SSO (document-agnostic)."""

from __future__ import annotations

import re

from docmirror.configs.structure_policy import pipe_grid_veto_threshold, scene_hint_prior_delta
from docmirror.tables.structure_detect import detect_pipe_grid_in_text

_SECTION_PATTERNS = [
    re.compile(r"^(一|二|三|四|五|六|七|八|九|十)\s{1,4}[\u4e00-\u9fff]"),
    re.compile(r"^[（(](一|二|三|四|五|六|七|八|九|十)[）)]"),
    re.compile(r"^第[一二三四五六七八九十百]+[章节部分篇]"),
    re.compile(r"^\d+\.\s+[A-Z\u4e00-\u9fff]"),
    re.compile(r"^(Section|Chapter|Part)\s+\d+", re.IGNORECASE),
]

PIPE_GRID_VETO_THRESHOLD = pipe_grid_veto_threshold()
SECTION_SCORE_NORMALIZER = 6.0


def sso_sample_page_indices(num_pages: int) -> list[int]:
    """Page indices for SSO pipe-grid sampling (first 10 + last 2)."""
    indices = list(range(min(10, num_pages)))
    if num_pages > 10:
        indices.extend([num_pages - 2, num_pages - 1])
    return indices


def build_sso_sample_text(fitz_doc, num_pages: int | None = None) -> str:
    """Concatenate text from SSO sample pages for H_pipe_grid / SDU."""
    n = num_pages if num_pages is not None else len(fitz_doc)
    parts: list[str] = []
    for idx in sso_sample_page_indices(n):
        if idx < len(fitz_doc):
            parts.append(fitz_doc[idx].get_text())
    return "\n".join(parts)


def score_section_headers(text: str) -> float:
    """H_section: normalized section header density in sample text."""
    if not text:
        return 0.0
    count = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for pat in _SECTION_PATTERNS:
            if pat.match(line):
                count += 1
                break
    return min(1.0, count / SECTION_SCORE_NORMALIZER)


def score_pipe_grid(text: str) -> float:
    """H_pipe_grid: SDU pipe ledger confidence."""
    return detect_pipe_grid_in_text(text).confidence


def score_table_pdf(table_pages: int, sample_size: int) -> float:
    """H_table_pdf: pdfplumber find_tables signal from sampled pages."""
    if sample_size <= 0:
        return 0.0
    ratio = table_pages / sample_size
    return min(1.0, ratio * 1.2)


def score_scan(scanned_pages: int, sample_size: int, has_text: bool) -> float:
    """H_scan: scanned page ratio."""
    if not has_text:
        return 1.0
    if sample_size <= 0:
        return 0.0
    return min(1.0, scanned_pages / sample_size)


def score_prose(table_pdf: float, pipe_grid: float, section: float) -> float:
    """H_prose: inverse of strong structure signals."""
    structural = max(table_pdf, pipe_grid, section)
    return max(0.0, 1.0 - structural)


def apply_scene_hint_prior(scores: dict[str, float], scene_hint: str | None) -> dict[str, float]:
    """Apply a weak prior from the plugin-selected structural profile."""
    delta = scene_hint_prior_delta()
    if not scene_hint or scene_hint == "unknown":
        return scores

    from docmirror.layout.profile.registry import get_profile
    from docmirror.layout.scene.scene_resolver import scene_to_layout_profile_id

    profile_id = scene_to_layout_profile_id(scene_hint)
    if profile_id is None:
        return scores
    segmentation_mode = get_profile(profile_id).segmentation_mode.value

    out = dict(scores)
    if segmentation_mode == "full_page_table":
        out["H_pipe_grid"] = min(1.0, out.get("H_pipe_grid", 0) + delta)
        out["H_table_pdf"] = min(1.0, out.get("H_table_pdf", 0) + delta)
    elif segmentation_mode == "section":
        out["H_section"] = min(1.0, out.get("H_section", 0) + delta)
    return out
