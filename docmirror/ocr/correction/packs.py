# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load, select, and merge versioned OCR correction packs."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import yaml

from docmirror.configs.paths import OCR_CORRECTION_PACKS_DIR, OCR_CORRECTIONS_YAML
from docmirror.ocr.correction.config_schema import ConfigIssue, validate_pack_data
from docmirror.ocr.correction.language import normalize_country, normalize_language, normalize_locale
from docmirror.ocr.correction.models import CorrectionContext


@dataclass(frozen=True)
class CorrectionPack:
    pack_id: str
    version: int
    priority: int
    data: dict[str, Any]
    path: str = ""
    language: str | None = None
    country: str | None = None
    locale: str | None = None
    domains: tuple[str, ...] = ()

    def matches(self, context: CorrectionContext) -> bool:
        if self.data.get("opt_in") is True and self.pack_id not in context.pack_ids:
            return False
        if self.language and context.language != self.language:
            return False
        if self.country and context.country != self.country:
            return False
        if self.locale and context.locale != self.locale:
            return False
        if self.domains and context.domain not in self.domains:
            return False
        return True

    def summary(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "version": self.version,
            "priority": self.priority,
            **({"language": self.language} if self.language else {}),
            **({"country": self.country} if self.country else {}),
            **({"locale": self.locale} if self.locale else {}),
            **({"domains": list(self.domains)} if self.domains else {}),
            **({"path": self.path} if self.path else {}),
        }


class CorrectionPackRegistry:
    def __init__(self, packs: Iterable[CorrectionPack], issues: Iterable[ConfigIssue] = ()) -> None:
        self.issues = tuple(issues)
        rejected_paths = {issue.path for issue in self.issues if issue.level == "error" and issue.path}
        self.packs = tuple(
            sorted(
                (pack for pack in packs if pack.path not in rejected_paths),
                key=lambda pack: (pack.priority, pack.pack_id),
            )
        )

    @classmethod
    @lru_cache(maxsize=1)
    def default(cls) -> CorrectionPackRegistry:
        packs: list[CorrectionPack] = []
        issues: list[ConfigIssue] = []
        legacy = _read_yaml(OCR_CORRECTIONS_YAML)
        if isinstance(legacy, dict):
            packs.append(
                CorrectionPack(
                    pack_id="builtin.legacy",
                    version=int(legacy.get("version") or 1),
                    priority=-1000,
                    data=legacy,
                    path=str(OCR_CORRECTIONS_YAML),
                )
            )
        if OCR_CORRECTION_PACKS_DIR.is_dir():
            for path in sorted(OCR_CORRECTION_PACKS_DIR.rglob("*.yaml")):
                raw = _read_yaml(path)
                pack_issues = validate_pack_data(raw, path=path)
                issues.extend(pack_issues)
                if not isinstance(raw, dict) or any(issue.level == "error" for issue in pack_issues):
                    continue
                packs.append(_pack_from_data(raw, path=path))
        for raw_path in os.environ.get("DOCMIRROR_OCR_CORRECTION_PACKS", "").split(os.pathsep):
            if not raw_path.strip():
                continue
            external = Path(raw_path).expanduser().resolve()
            candidates = sorted(external.rglob("*.yaml")) if external.is_dir() else [external]
            for path in candidates:
                raw = _read_yaml(path)
                pack_issues = validate_pack_data(raw, path=path)
                issues.extend(pack_issues)
                if isinstance(raw, dict) and not any(issue.level == "error" for issue in pack_issues):
                    packs.append(_pack_from_data(raw, path=path))
        issues.extend(_cross_pack_issues(packs))
        return cls(packs, issues)

    @classmethod
    def from_paths(cls, paths: Iterable[str | Path], *, include_builtin: bool = True) -> CorrectionPackRegistry:
        base = list(cls.default().packs) if include_builtin else []
        issues: list[ConfigIssue] = []
        for raw_path in paths:
            path = Path(raw_path).expanduser().resolve()
            candidates = sorted(path.rglob("*.yaml")) if path.is_dir() else [path]
            for candidate in candidates:
                raw = _read_yaml(candidate)
                pack_issues = validate_pack_data(raw, path=candidate)
                issues.extend(pack_issues)
                if isinstance(raw, dict) and not any(issue.level == "error" for issue in pack_issues):
                    base.append(_pack_from_data(raw, path=candidate))
        issues.extend(_cross_pack_issues(base))
        return cls(base, issues)

    def select(self, context: CorrectionContext) -> tuple[CorrectionPack, ...]:
        return tuple(pack for pack in self.packs if pack.matches(context))

    def merged_data(self, context: CorrectionContext) -> tuple[dict[str, Any], tuple[CorrectionPack, ...]]:
        selected = self.select(context)
        merged: dict[str, Any] = {"version": 1, "thresholds": {}, "confusions": {}, "rules": [], "lexicons": {}}
        for pack in selected:
            data = pack.data
            thresholds = data.get("thresholds")
            if isinstance(thresholds, dict):
                merged["thresholds"].update(thresholds)
            confusions = data.get("confusions")
            if isinstance(confusions, dict):
                for source, targets in confusions.items():
                    existing = merged["confusions"].setdefault(str(source), {})
                    if isinstance(targets, dict):
                        for target, cost in targets.items():
                            existing[str(target)] = cost
                    else:
                        for target in targets or []:
                            existing.setdefault(str(target), 0.2)
            for rule in data.get("exact_rules", data.get("rules", [])) or []:
                if isinstance(rule, dict):
                    merged["rules"].append(
                        {
                            **rule,
                            "_pack_id": pack.pack_id,
                            "_pack_version": pack.version,
                            "_language": pack.language,
                            "_country": pack.country,
                            "_priority": pack.priority,
                        }
                    )
            lexicons = data.get("lexicons")
            if isinstance(lexicons, dict):
                for name, entry in lexicons.items():
                    if isinstance(entry, dict):
                        merged["lexicons"][f"{pack.pack_id}:{name}"] = {
                            **entry,
                            "_pack_id": pack.pack_id,
                            "_pack_version": pack.version,
                            "_priority": pack.priority,
                        }
            declared = data.get("lexicon")
            if isinstance(declared, list):
                merged["lexicons"][f"{pack.pack_id}:default"] = {
                    "domains": data.get("domains") or [],
                    "roles": data.get("roles") or [],
                    "terms": declared,
                    "_pack_id": pack.pack_id,
                    "_pack_version": pack.version,
                    "_priority": pack.priority,
                }
        merged["rules"].sort(key=lambda rule: int(rule.get("_priority") or 0), reverse=True)
        return merged, selected

    def summaries(self) -> list[dict[str, Any]]:
        return [pack.summary() for pack in self.packs]


def _pack_from_data(data: dict[str, Any], *, path: Path) -> CorrectionPack:
    return CorrectionPack(
        pack_id=str(data["pack_id"]),
        version=int(data.get("version") or 1),
        priority=int(data.get("priority") or 0),
        data=data,
        path=str(path),
        language=normalize_language(str(data.get("language") or "") or None),
        country=normalize_country(str(data.get("country") or "") or None),
        locale=normalize_locale(str(data.get("locale") or "") or None),
        domains=tuple(str(value) for value in data.get("domains") or []),
    )


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None


def _cross_pack_issues(packs: Iterable[CorrectionPack]) -> list[ConfigIssue]:
    issues: list[ConfigIssue] = []
    seen_ids: dict[str, CorrectionPack] = {}
    seen_rules: dict[tuple[str, tuple[str, ...], tuple[str, ...], int], tuple[str, CorrectionPack]] = {}
    for pack in packs:
        previous = seen_ids.get(pack.pack_id)
        if previous and previous.path != pack.path:
            issues.append(
                ConfigIssue(
                    "error",
                    "pack.id_duplicate",
                    f"pack_id {pack.pack_id!r} appears in both {previous.path} and {pack.path}",
                    pack.path,
                )
            )
        seen_ids[pack.pack_id] = pack
        for rule in pack.data.get("exact_rules", pack.data.get("rules", [])) or []:
            if not isinstance(rule, dict):
                continue
            observed = str(rule.get("observed") or rule.get("source") or "").strip()
            canonical = str(rule.get("canonical") or rule.get("target") or "").strip()
            key = (
                observed,
                tuple(sorted(str(value) for value in rule.get("domains") or pack.domains)),
                tuple(sorted(str(value) for value in rule.get("roles") or [])),
                pack.priority,
            )
            previous = seen_rules.get(key)
            if observed and previous and previous[0] != canonical:
                issues.append(
                    ConfigIssue(
                        "error",
                        "rule.cross_pack_conflict",
                        f"{observed!r} maps to {previous[0]!r} in {previous[1].pack_id} and {canonical!r} in {pack.pack_id}",
                        pack.path,
                    )
                )
            seen_rules[key] = (canonical, pack)
    return issues


__all__ = ["CorrectionPack", "CorrectionPackRegistry"]
