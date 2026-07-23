# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small, domain-scoped lexicon and weighted candidate search."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class CorrectionRule:
    rule_id: str
    observed: str
    canonical: str
    domains: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    pack_id: str | None = None
    pack_version: int | None = None

    def applies(self, *, domain: str | None, role: str) -> bool:
        if self.domains and domain is not None and domain not in self.domains:
            return False
        return not self.roles or role in self.roles


@dataclass(frozen=True)
class CandidateMatch:
    text: str
    distance: float
    score: float
    runner_up_score: float | None = None
    confidence_margin: float | None = None
    candidates: tuple[str, ...] = ()
    pack_id: str | None = None
    pack_version: int | None = None
    priority: int = 0


@dataclass(frozen=True)
class _LexiconTerm:
    text: str
    domains: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    pack_id: str | None = None
    pack_version: int | None = None
    priority: int = 0


class CorrectionLexicon:
    """Loaded once and searched only within a role/domain-sized bucket."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.version = int(data.get("version") or 1)
        thresholds = data.get("thresholds") if isinstance(data.get("thresholds"), dict) else {}
        self.max_distance = float(thresholds.get("max_weighted_distance", 1.0))
        self.min_margin = float(thresholds.get("min_candidate_margin", 0.5))
        self.confusion_costs = _confusion_costs(data.get("confusions"))
        self.confusion_pairs = frozenset(self.confusion_costs)
        self.rules = tuple(_rules(data.get("rules")))
        self._terms: list[_LexiconTerm] = []
        self._load_declared_lexicons(data.get("lexicons"))
        self._load_key_synonyms()

    @classmethod
    @lru_cache(maxsize=1)
    def default(cls) -> CorrectionLexicon:
        from docmirror.ocr.correction.models import CorrectionContext
        from docmirror.ocr.correction.packs import CorrectionPackRegistry

        raw, _packs = CorrectionPackRegistry.default().merged_data(CorrectionContext())
        return cls(raw)

    def applicable_rules(self, *, domain: str | None, role: str) -> tuple[CorrectionRule, ...]:
        return tuple(rule for rule in self.rules if rule.applies(domain=domain, role=role))

    def unique_candidate(self, text: str, *, domain: str | None, role: str) -> CandidateMatch | None:
        normalized = str(text or "").strip()
        if len(normalized) < 3:
            return None
        candidates_by_text: dict[str, CandidateMatch] = {}
        normalized_lower = normalized.lower()
        for item in self._terms:
            term = item.text
            if item.domains and domain is not None and domain not in item.domains:
                continue
            if item.roles and role not in item.roles:
                continue
            if abs(len(term) - len(normalized)) > 1:
                continue
            if term == normalized:
                return None
            distance = weighted_damerau_levenshtein(normalized_lower, term.lower(), self.confusion_costs)
            if distance <= self.max_distance:
                candidate = CandidateMatch(
                    text=term,
                    distance=distance,
                    score=max(0.0, 1.0 - distance / max(len(term), len(normalized), 1)),
                    pack_id=item.pack_id,
                    pack_version=item.pack_version,
                    priority=item.priority,
                )
                existing = candidates_by_text.get(term)
                if existing is None or candidate.priority > existing.priority:
                    candidates_by_text[term] = candidate
        candidates = list(candidates_by_text.values())
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item.distance, -len(item.text), item.text))
        best = candidates[0]
        if len(candidates) > 1 and candidates[1].distance - best.distance < self.min_margin:
            return None
        runner_up_score = candidates[1].score if len(candidates) > 1 else None
        margin = best.score - runner_up_score if runner_up_score is not None else 1.0
        return CandidateMatch(
            text=best.text,
            distance=best.distance,
            score=best.score,
            runner_up_score=runner_up_score,
            confidence_margin=margin,
            candidates=tuple(item.text for item in candidates[:5]),
            pack_id=best.pack_id,
            pack_version=best.pack_version,
            priority=best.priority,
        )

    def _load_declared_lexicons(self, value: Any) -> None:
        if not isinstance(value, dict):
            return
        for entry in value.values():
            if not isinstance(entry, dict):
                continue
            domains = tuple(str(item) for item in entry.get("domains") or [])
            roles = tuple(str(item) for item in entry.get("roles") or [])
            pack_id = str(entry.get("_pack_id") or "") or None
            pack_version = int(entry.get("_pack_version")) if entry.get("_pack_version") is not None else None
            priority = int(entry.get("_priority") or 0)
            for term in entry.get("terms") or []:
                text = str(term or "").strip()
                if text:
                    self._terms.append(_LexiconTerm(text, domains, roles, pack_id, pack_version, priority))

    def _load_key_synonyms(self) -> None:
        from docmirror.configs.domain.registry import KEY_SYNONYMS_BY_DOMAIN

        raw = KEY_SYNONYMS_BY_DOMAIN
        for domain, locales in raw.items():
            if not isinstance(locales, dict):
                continue
            for mappings in locales.values():
                if not isinstance(mappings, dict):
                    continue
                for term in mappings:
                    text = str(term or "").strip()
                    if text:
                        self._terms.append(
                            _LexiconTerm(
                                text, (str(domain),), ("field_label", "table_header"), "builtin.key_synonyms", 1
                            )
                        )


def _rules(value: Any) -> list[CorrectionRule]:
    out: list[CorrectionRule] = []
    for item in value or []:
        if not isinstance(item, dict):
            continue
        observed = str(item.get("observed") or "").strip()
        canonical = str(item.get("canonical") or "").strip()
        if not observed or not canonical or observed == canonical:
            continue
        out.append(
            CorrectionRule(
                rule_id=str(item.get("id") or f"ocr.{len(out) + 1}"),
                observed=observed,
                canonical=canonical,
                domains=tuple(str(value) for value in item.get("domains") or []),
                roles=tuple(str(value) for value in item.get("roles") or []),
                pack_id=str(item.get("_pack_id") or "") or None,
                pack_version=int(item.get("_pack_version")) if item.get("_pack_version") is not None else None,
            )
        )
    return out


def _confusion_costs(value: Any) -> dict[tuple[str, str], float]:
    pairs: dict[tuple[str, str], float] = {}
    if isinstance(value, dict):
        for left, rights in value.items():
            entries = rights.items() if isinstance(rights, dict) else ((right, 0.2) for right in rights or [])
            for right, raw_cost in entries:
                try:
                    cost = max(0.0, min(1.0, float(raw_cost)))
                except (TypeError, ValueError):
                    cost = 0.2
                pairs[(str(left).lower(), str(right).lower())] = cost
                pairs[(str(right).lower(), str(left).lower())] = cost
    return pairs


def weighted_damerau_levenshtein(
    left: str,
    right: str,
    confusion_pairs: frozenset[tuple[str, str]] | dict[tuple[str, str], float] = frozenset(),
) -> float:
    """Restricted Damerau-Levenshtein with cheap known OCR substitutions."""
    if left == right:
        return 0.0
    previous_previous: list[float] | None = None
    previous = [float(index) for index in range(len(right) + 1)]
    for i, left_char in enumerate(left, start=1):
        current = [float(i)]
        for j, right_char in enumerate(right, start=1):
            if left_char == right_char:
                substitution = 0.0
            elif isinstance(confusion_pairs, dict):
                substitution = confusion_pairs.get((left_char, right_char), 1.0)
            else:
                substitution = 0.2 if (left_char, right_char) in confusion_pairs else 1.0
            value = min(
                current[j - 1] + 1.0,
                previous[j] + 1.0,
                previous[j - 1] + substitution,
            )
            if (
                previous_previous is not None
                and i > 1
                and j > 1
                and left_char == right[j - 2]
                and left[i - 2] == right_char
            ):
                value = min(value, previous_previous[j - 2] + 0.75)
            current.append(value)
        previous_previous, previous = previous, current
    return previous[-1]


__all__ = [
    "CandidateMatch",
    "CorrectionLexicon",
    "CorrectionRule",
    "weighted_damerau_levenshtein",
]
