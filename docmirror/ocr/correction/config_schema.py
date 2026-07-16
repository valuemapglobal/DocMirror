# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validation helpers for declarative OCR correction packs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ConfigIssue:
    level: str
    code: str
    message: str
    path: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            **({"path": self.path} if self.path else {}),
        }


class CorrectionPackConfigError(ValueError):
    def __init__(self, issues: Iterable[ConfigIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(issue.message for issue in self.issues))


def validate_pack_data(data: Any, *, path: str | Path = "") -> tuple[ConfigIssue, ...]:
    location = str(path)
    issues: list[ConfigIssue] = []
    if not isinstance(data, dict):
        return (ConfigIssue("error", "pack.not_mapping", "correction pack must be a mapping", location),)
    pack_id = str(data.get("pack_id") or "").strip()
    if not pack_id:
        issues.append(ConfigIssue("error", "pack.id_missing", "pack_id is required", location))
    elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", pack_id):
        issues.append(ConfigIssue("error", "pack.id_invalid", f"invalid pack_id: {pack_id!r}", location))
    try:
        version = int(data.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version < 1:
        issues.append(ConfigIssue("error", "pack.version_invalid", "version must be a positive integer", location))
    priority = data.get("priority", 0)
    if not isinstance(priority, int):
        issues.append(ConfigIssue("error", "pack.priority_invalid", "priority must be an integer", location))
    language = str(data.get("language") or "")
    country = str(data.get("country") or "")
    locale = str(data.get("locale") or "")
    if language and not re.fullmatch(r"[A-Za-z]{2,3}", language):
        issues.append(ConfigIssue("error", "pack.language_invalid", f"invalid language: {language!r}", location))
    if country and not re.fullmatch(r"[A-Za-z]{2}", country):
        issues.append(ConfigIssue("error", "pack.country_invalid", f"invalid country: {country!r}", location))
    if locale and not re.fullmatch(r"[A-Za-z]{2,3}(?:[-_][A-Za-z]{2})?", locale):
        issues.append(ConfigIssue("error", "pack.locale_invalid", f"invalid locale: {locale!r}", location))
    if "opt_in" in data and not isinstance(data["opt_in"], bool):
        issues.append(ConfigIssue("error", "pack.opt_in_invalid", "opt_in must be true or false", location))

    seen_ids: set[str] = set()
    seen_observed: dict[tuple[str, tuple[str, ...], tuple[str, ...]], str] = {}
    rules = data.get("exact_rules", data.get("rules", [])) or []
    if not isinstance(rules, list):
        issues.append(ConfigIssue("error", "pack.rules_invalid", "exact_rules must be a list", location))
        rules = []
    for index, rule in enumerate(rules):
        rule_path = f"{location}:exact_rules[{index}]"
        if not isinstance(rule, dict):
            issues.append(ConfigIssue("error", "rule.not_mapping", "rule must be a mapping", rule_path))
            continue
        rule_id = str(rule.get("id") or "").strip()
        observed = str(rule.get("observed") or rule.get("source") or "").strip()
        canonical = str(rule.get("canonical") or rule.get("target") or "").strip()
        if not rule_id:
            issues.append(ConfigIssue("error", "rule.id_missing", "rule id is required", rule_path))
        elif rule_id in seen_ids:
            issues.append(ConfigIssue("error", "rule.id_duplicate", f"duplicate rule id: {rule_id}", rule_path))
        seen_ids.add(rule_id)
        if not observed or not canonical:
            issues.append(ConfigIssue("error", "rule.text_missing", "observed and canonical are required", rule_path))
        elif observed == canonical:
            issues.append(ConfigIssue("error", "rule.noop", f"rule {rule_id or index} does not change text", rule_path))
        key = (
            observed,
            tuple(sorted(str(value) for value in rule.get("domains") or [])),
            tuple(sorted(str(value) for value in rule.get("roles") or [])),
        )
        previous = seen_observed.get(key)
        if previous and previous != canonical:
            issues.append(
                ConfigIssue(
                    "error",
                    "rule.conflict",
                    f"{observed!r} maps to both {previous!r} and {canonical!r} in the same scope",
                    rule_path,
                )
            )
        seen_observed[key] = canonical

    edges = {
        str(rule.get("observed") or rule.get("source") or "").strip(): str(
            rule.get("canonical") or rule.get("target") or ""
        ).strip()
        for rule in rules
        if isinstance(rule, dict)
    }
    for source, target in edges.items():
        if source and target and edges.get(target) == source:
            issues.append(
                ConfigIssue("error", "rule.cycle", f"two-way correction cycle: {source!r} <-> {target!r}", location)
            )
    seen_terms: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    lexicons = data.get("lexicons") or {}
    if not isinstance(lexicons, dict):
        issues.append(ConfigIssue("error", "pack.lexicons_invalid", "lexicons must be a mapping", location))
    else:
        for name, entry in lexicons.items():
            if not isinstance(entry, dict):
                issues.append(
                    ConfigIssue("error", "lexicon.not_mapping", f"lexicon {name!r} must be a mapping", location)
                )
                continue
            domains = tuple(sorted(str(value) for value in entry.get("domains") or data.get("domains") or []))
            roles = tuple(sorted(str(value) for value in entry.get("roles") or []))
            for term in entry.get("terms") or []:
                key = (str(term).strip(), domains, roles)
                if key in seen_terms:
                    issues.append(
                        ConfigIssue(
                            "warning",
                            "lexicon.term_duplicate",
                            f"duplicate lexicon term in the same scope: {key[0]!r}",
                            location,
                        )
                    )
                seen_terms.add(key)
    return tuple(issues)


def raise_for_pack_issues(data: Any, *, path: str | Path = "") -> None:
    issues = tuple(issue for issue in validate_pack_data(data, path=path) if issue.level == "error")
    if issues:
        raise CorrectionPackConfigError(issues)


__all__ = ["ConfigIssue", "CorrectionPackConfigError", "raise_for_pack_issues", "validate_pack_data"]
