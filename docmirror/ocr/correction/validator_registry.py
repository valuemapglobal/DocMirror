# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Country and field-type registry for deterministic OCR validators."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from docmirror.ocr.correction.validators import (
    repair_iban_if_unique,
    repair_uscc_if_unique,
    validate_amount_text,
    validate_bic,
    validate_date_text,
    validate_email_text,
    validate_eu_vat_format,
    validate_iban,
    validate_jp_corporate_number_format,
    validate_phone_text,
    validate_sg_uen_format,
    validate_us_ein_format,
    validate_uscc,
)

Validator = Callable[[str], bool]
Repairer = Callable[[str], str | None]


@dataclass(frozen=True)
class RegisteredValidator:
    validator_id: str
    field_type: str
    country: str | None
    validate: Validator
    repair: Repairer | None = None
    format_only: bool = False


@dataclass(frozen=True)
class ValidationOutcome:
    validator_id: str
    valid: bool
    repaired: str | None = None
    format_only: bool = False


class ValidatorRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str | None, str], RegisteredValidator] = {}

    def register(
        self,
        *,
        validator_id: str,
        field_type: str,
        validator: Validator,
        country: str | None = None,
        repairer: Repairer | None = None,
        format_only: bool = False,
    ) -> None:
        key = (country.upper() if country else None, field_type.lower())
        self._items[key] = RegisteredValidator(
            validator_id=validator_id,
            field_type=field_type.lower(),
            country=key[0],
            validate=validator,
            repair=repairer,
            format_only=format_only,
        )

    def resolve(self, field_type: str, *, country: str | None = None) -> RegisteredValidator | None:
        normalized_type = str(field_type or "").strip().lower()
        normalized_country = str(country or "").strip().upper() or None
        return self._items.get((normalized_country, normalized_type)) or self._items.get((None, normalized_type))

    def evaluate(self, value: str, *, field_type: str, country: str | None = None) -> ValidationOutcome | None:
        item = self.resolve(field_type, country=country)
        if item is None:
            return None
        valid = item.validate(value)
        repaired = None if valid or item.repair is None or item.format_only else item.repair(value)
        return ValidationOutcome(item.validator_id, valid, repaired, item.format_only)

    def summaries(self) -> list[dict[str, str | bool | None]]:
        return [
            {
                "validator_id": item.validator_id,
                "field_type": item.field_type,
                "country": item.country,
                "repair_enabled": item.repair is not None and not item.format_only,
                "format_only": item.format_only,
            }
            for item in sorted(self._items.values(), key=lambda value: value.validator_id)
        ]

    @classmethod
    @lru_cache(maxsize=1)
    def default(cls) -> ValidatorRegistry:
        registry = cls()
        registry.register(
            validator_id="cn.uscc",
            field_type="uscc",
            country="CN",
            validator=validate_uscc,
            repairer=repair_uscc_if_unique,
        )
        registry.register(
            validator_id="international.iban",
            field_type="iban",
            validator=validate_iban,
            repairer=repair_iban_if_unique,
        )
        registry.register(validator_id="international.bic", field_type="bic", validator=validate_bic, format_only=True)
        registry.register(validator_id="eu.vat", field_type="vat", validator=validate_eu_vat_format, format_only=True)
        registry.register(
            validator_id="us.ein", field_type="ein", country="US", validator=validate_us_ein_format, format_only=True
        )
        registry.register(
            validator_id="jp.corporate_number",
            field_type="corporate_number",
            country="JP",
            validator=validate_jp_corporate_number_format,
            format_only=True,
        )
        registry.register(
            validator_id="sg.uen", field_type="uen", country="SG", validator=validate_sg_uen_format, format_only=True
        )
        registry.register(validator_id="international.date", field_type="date", validator=validate_date_text)
        registry.register(validator_id="international.amount", field_type="amount", validator=validate_amount_text)
        registry.register(
            validator_id="international.email", field_type="email", validator=validate_email_text, format_only=True
        )
        registry.register(
            validator_id="international.phone", field_type="phone", validator=validate_phone_text, format_only=True
        )
        return registry


__all__ = ["RegisteredValidator", "ValidationOutcome", "ValidatorRegistry"]
