# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Conservative, deterministic OCR post-correction engine."""

from __future__ import annotations

import re
from dataclasses import replace

from docmirror.ocr.correction.language import resolve_language_hint
from docmirror.ocr.correction.lexicon import CandidateMatch, CorrectionLexicon
from docmirror.ocr.correction.models import CorrectionContext, CorrectionDecision
from docmirror.ocr.correction.normalizers import NormalizerRegistry, UnicodeTextNormalizer
from docmirror.ocr.correction.packs import CorrectionPackRegistry
from docmirror.ocr.correction.tokenizers import TokenizerRegistry
from docmirror.ocr.correction.validator_registry import ValidatorRegistry
from docmirror.ocr.correction.validators import (
    validate_amount_text,
    validate_date_text,
)

_ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9]{4,}")
_IBAN_TOKEN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}[A-Z0-9]{13,32}(?![A-Z0-9])", re.IGNORECASE)


class SafeOCRCorrector:
    """Apply only contextual, uniquely-supported text corrections."""

    def __init__(
        self,
        lexicon: CorrectionLexicon | None = None,
        *,
        pack_registry: CorrectionPackRegistry | None = None,
        validator_registry: ValidatorRegistry | None = None,
        tokenizer_registry: TokenizerRegistry | None = None,
        normalizer_registry: NormalizerRegistry | None = None,
    ) -> None:
        self.lexicon = lexicon
        self.pack_registry = pack_registry or CorrectionPackRegistry.default()
        self.validator_registry = validator_registry or ValidatorRegistry.default()
        self.tokenizer_registry = tokenizer_registry or TokenizerRegistry.default()
        self.normalizer_registry = normalizer_registry or NormalizerRegistry.default()
        self._lexicon_cache: dict[tuple[object, ...], tuple[CorrectionLexicon, tuple[tuple[str, int], ...]]] = {}

    def correct(self, text: str, context: CorrectionContext | None = None) -> CorrectionDecision:
        context = context or CorrectionContext()
        original = str(text or "")
        if not original:
            return self._decision(original, original, context)

        initial_hint = resolve_language_hint(
            original,
            language=context.language,
            country=context.country,
            locale=context.locale,
            script=context.script,
        )
        normalized = self.normalizer_registry.resolve(
            language=initial_hint.language,
            script=initial_hint.script,
        ).normalize(original)
        hint = resolve_language_hint(
            normalized,
            language=initial_hint.language,
            country=initial_hint.country,
            locale=initial_hint.locale,
            script=initial_hint.script,
        )
        effective_context = replace(
            context,
            language=hint.language,
            country=hint.country,
            locale=hint.locale,
            script=hint.script,
        )
        if context.role in {"text_line", "unknown"} and _looks_like_labeled_line(normalized):
            effective_context = replace(effective_context, role="field_label")
        if context.mode == "off":
            return self._finalize(
                original,
                normalized,
                effective_context,
                rule_id="unicode.normalize" if normalized != original else None,
                reasons=("unicode_normalization",) if normalized != original else (),
                score=1.0,
                pack_id="builtin.unicode" if normalized != original else None,
                pack_version=1 if normalized != original else None,
            )
        lexicon, selected_packs = self._lexicon_for(effective_context)
        selected_pack_ids = tuple(pack_id for pack_id, _version in selected_packs)

        candidate = normalized
        rule_id: str | None = None
        reasons: list[str] = []
        score = 1.0
        pack_id: str | None = None
        pack_version: int | None = None
        candidates: tuple[str, ...] = ()
        runner_up_score: float | None = None
        confidence_margin: float | None = None

        if normalized != original:
            rule_id = "unicode.normalize"
            pack_id = "builtin.unicode"
            pack_version = 1
            reasons.append("unicode_normalization")

        embedded_candidate, embedded_type = self._repair_embedded_identifiers(candidate, effective_context)
        if embedded_candidate != candidate:
            candidate = embedded_candidate
            rule_id = f"code.{embedded_type}_checksum"
            pack_id = "builtin.validators"
            pack_version = 1
            reasons.extend(("character_confusion", "unique_checksum_candidate"))

        registered_candidate, registered_rule, registered_reason = self._repair_registered_value(
            candidate, effective_context
        )
        if registered_candidate != candidate:
            candidate = registered_candidate
            rule_id = registered_rule
            pack_id = "builtin.validators"
            pack_version = 1
            reasons.extend(registered_reason)

        format_candidate, format_rule, format_reason = self._repair_typed_value(candidate, effective_context)
        if format_candidate != candidate:
            candidate = format_candidate
            rule_id = format_rule
            pack_id = "builtin.validators"
            pack_version = 1
            reasons.extend(format_reason)

        for rule in lexicon.applicable_rules(domain=effective_context.domain, role=effective_context.role):
            if rule.observed in candidate:
                candidate = candidate.replace(rule.observed, rule.canonical)
                rule_id = rule.rule_id
                pack_id = rule.pack_id
                pack_version = rule.pack_version
                reasons.extend(("exact_alias", "context_matched"))
                score = 1.0
                break

        candidate, fuzzy_rule, fuzzy_reasons, fuzzy_match = self._repair_lexicon(candidate, effective_context, lexicon)
        if fuzzy_rule and fuzzy_match:
            rule_id = fuzzy_rule
            reasons.extend(fuzzy_reasons)
            score = fuzzy_match.score
            pack_id = fuzzy_match.pack_id
            pack_version = fuzzy_match.pack_version
            candidates = fuzzy_match.candidates
            runner_up_score = fuzzy_match.runner_up_score
            confidence_margin = fuzzy_match.confidence_margin

        return self._finalize(
            original,
            candidate,
            effective_context,
            rule_id=rule_id,
            reasons=tuple(dict.fromkeys(reasons)),
            score=score,
            pack_id=pack_id,
            pack_version=pack_version,
            candidates=candidates,
            runner_up_score=runner_up_score,
            confidence_margin=confidence_margin,
            selected_pack_ids=selected_pack_ids,
            selected_packs=selected_packs,
        )

    def _lexicon_for(self, context: CorrectionContext) -> tuple[CorrectionLexicon, tuple[tuple[str, int], ...]]:
        if self.lexicon is not None:
            return self.lexicon, ()
        key = (context.language, context.country, context.locale, context.domain, context.role, context.pack_ids)
        cached = self._lexicon_cache.get(key)
        if cached is not None:
            return cached
        data, packs = self.pack_registry.merged_data(context)
        value = (CorrectionLexicon(data), tuple((pack.pack_id, pack.version) for pack in packs))
        self._lexicon_cache[key] = value
        return value

    def _repair_embedded_identifiers(self, text: str, context: CorrectionContext) -> tuple[str, str | None]:
        declarations = [
            declaration
            for pack in self.pack_registry.select(context)
            for declaration in pack.data.get("embedded_identifiers") or []
            if isinstance(declaration, dict)
        ]
        out = text
        repaired_type: str | None = None
        for declaration in declarations:
            field_type = str(declaration.get("field_type") or "")
            country = str(declaration.get("country") or context.country or "") or None
            validator = self.validator_registry.resolve(field_type, country=country)
            if validator is None or validator.repair is None or not validator.candidate_pattern:
                continue
            for match in tuple(re.finditer(validator.candidate_pattern, out, re.IGNORECASE)):
                repaired = validator.repair(match.group(0))
                if repaired and repaired != match.group(0).upper():
                    out = out.replace(match.group(0), repaired, 1)
                    repaired_type = field_type
        return out, repaired_type

    def _repair_typed_value(
        self,
        text: str,
        context: CorrectionContext,
    ) -> tuple[str, str | None, tuple[str, ...]]:
        if context.role == "date" and not validate_date_text(text):
            candidate = _typed_char_substitution(text, digits_only=True)
            candidate = re.sub(r"[~～]", "-", candidate)
            if validate_date_text(candidate):
                return candidate, "format.date", ("typed_character_set", "date_validation")
        if context.role == "amount" and not validate_amount_text(text):
            candidate = _typed_char_substitution(text, digits_only=True)
            candidate = candidate.replace(";", ",").replace(":", ".")
            if validate_amount_text(candidate):
                return candidate, "format.amount", ("typed_character_set", "amount_validation")
        return text, None, ()

    def _repair_registered_value(
        self,
        text: str,
        context: CorrectionContext,
    ) -> tuple[str, str | None, tuple[str, ...]]:
        field_type = str(context.metadata.get("field_type") or "").strip().lower()
        if not field_type and context.role in {"date", "amount"}:
            field_type = context.role
        if not field_type and re.search(r"\bIBAN\b", text, re.IGNORECASE):
            field_type = "iban"
        if not field_type:
            return text, None, ()
        if field_type == "iban":
            for match in _IBAN_TOKEN_RE.finditer(text):
                outcome = self.validator_registry.evaluate(match.group(0), field_type="iban", country=context.country)
                if outcome and outcome.repaired and outcome.repaired != match.group(0):
                    repaired_text = f"{text[: match.start()]}{outcome.repaired}{text[match.end() :]}"
                    return (
                        repaired_text,
                        f"validator.{outcome.validator_id}",
                        ("registered_validator", "unique_checksum_candidate"),
                    )
        outcome = self.validator_registry.evaluate(text, field_type=field_type, country=context.country)
        if outcome and outcome.repaired and outcome.repaired != text:
            return (
                outcome.repaired,
                f"validator.{outcome.validator_id}",
                ("registered_validator", "unique_checksum_candidate"),
            )
        return text, None, ()

    def _repair_lexicon(
        self,
        text: str,
        context: CorrectionContext,
        lexicon: CorrectionLexicon,
    ) -> tuple[str, str | None, tuple[str, ...], CandidateMatch | None]:
        if context.role in {"field_label", "table_header", "unknown"}:
            stripped = text.strip()
            label, separator, suffix = _split_label(stripped)
            probe = label if separator else stripped
            match = lexicon.unique_candidate(probe, domain=context.domain, role=context.role)
            if match:
                replacement = f"{match.text}{separator}{suffix}" if separator else match.text
                return (
                    text.replace(stripped, replacement, 1),
                    "lexicon.unique_candidate",
                    ("weighted_edit_distance", "unique_candidate", "context_matched"),
                    match,
                )

        if context.role not in {"text_line", "field_label", "table_header", "institution", "unknown"}:
            return text, None, (), None
        output = text
        best_match = None
        tokenizer = self.tokenizer_registry.resolve(language=context.language, script=context.script)
        tokens = [token.text for token in tokenizer.tokenize(text) if 3 <= len(token.text) <= 64]
        for token in dict.fromkeys(tokens or _ASCII_TOKEN_RE.findall(text)):
            match = lexicon.unique_candidate(token, domain=context.domain, role=context.role)
            if not match:
                continue
            replacement = _match_case(token, match.text)
            output = output.replace(token, replacement)
            if best_match is None or match.score < best_match.score:
                best_match = match
        if best_match is not None:
            return (
                output,
                "lexicon.unique_candidate",
                ("weighted_edit_distance", "unique_candidate", "token_context"),
                best_match,
            )
        return text, None, (), None

    def _finalize(
        self,
        original: str,
        candidate: str,
        context: CorrectionContext,
        *,
        rule_id: str | None,
        reasons: tuple[str, ...],
        score: float,
        pack_id: str | None = None,
        pack_version: int | None = None,
        candidates: tuple[str, ...] = (),
        runner_up_score: float | None = None,
        confidence_margin: float | None = None,
        selected_pack_ids: tuple[str, ...] = (),
        selected_packs: tuple[tuple[str, int], ...] = (),
    ) -> CorrectionDecision:
        if candidate == original:
            return self._decision(original, original, context)
        semantic_change = any(reason != "unicode_normalization" for reason in reasons)
        action = "suggested" if context.mode == "suggest" and semantic_change else "applied"
        return self._decision(
            original,
            candidate,
            context,
            action=action,
            rule_id=rule_id,
            reasons=reasons,
            score=score,
            pack_id=pack_id,
            pack_version=pack_version,
            candidates=candidates,
            runner_up_score=runner_up_score,
            confidence_margin=confidence_margin,
            selected_pack_ids=selected_pack_ids,
            selected_packs=selected_packs,
        )

    @staticmethod
    def _decision(
        original: str,
        corrected: str,
        context: CorrectionContext,
        *,
        action: str = "unchanged",
        rule_id: str | None = None,
        reasons: tuple[str, ...] = (),
        score: float = 1.0,
        pack_id: str | None = None,
        pack_version: int | None = None,
        candidates: tuple[str, ...] = (),
        runner_up_score: float | None = None,
        confidence_margin: float | None = None,
        selected_pack_ids: tuple[str, ...] = (),
        selected_packs: tuple[tuple[str, int], ...] = (),
    ) -> CorrectionDecision:
        return CorrectionDecision(
            original=original,
            corrected=corrected,
            action=action,  # type: ignore[arg-type]
            rule_id=rule_id,
            reason_codes=reasons,
            score=score,
            source_ref=context.source_ref,
            role=context.role,
            domain=context.domain,
            ocr_confidence=context.ocr_confidence,
            candidates=candidates,
            pack_id=pack_id,
            pack_version=pack_version,
            language=context.language,
            country=context.country,
            locale=context.locale,
            script=context.script,
            runner_up_score=runner_up_score,
            confidence_margin=confidence_margin,
            selected_pack_ids=selected_pack_ids,
            selected_packs=selected_packs,
        )


def normalize_ocr_unicode(text: str) -> str:
    return UnicodeTextNormalizer("NFKC").normalize(text)


def _typed_char_substitution(text: str, *, digits_only: bool) -> str:
    mapping = str.maketrans(
        {"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "S": "5", "s": "5", "B": "8", "b": "8", "Z": "2", "z": "2"}
    )
    return text.translate(mapping) if digits_only else text


def _match_case(observed: str, canonical: str) -> str:
    if observed.isupper():
        return canonical.upper()
    if observed.islower():
        return canonical.lower()
    return canonical


def _looks_like_labeled_line(text: str) -> bool:
    label, separator, _suffix = _split_label(text.strip())
    return bool(separator and 1 < len(label) <= 20)


def _split_label(text: str) -> tuple[str, str, str]:
    match = re.match(r"^(.{1,20}?)([:：])(.*)$", text)
    if not match:
        return text, "", ""
    return match.group(1).strip(), match.group(2), match.group(3)


__all__ = ["SafeOCRCorrector", "normalize_ocr_unicode"]
