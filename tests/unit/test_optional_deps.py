from __future__ import annotations

import pytest

from docmirror.runtime.optional_deps import (
    FeatureUnavailableError,
    require_optional_module,
    require_optional_modules,
)


def test_require_optional_module_loads_present_module() -> None:
    module = require_optional_module("json", feature="json smoke", extra="dev")
    assert module.__name__ == "json"


def test_require_optional_module_reports_install_hint() -> None:
    with pytest.raises(FeatureUnavailableError) as exc_info:
        require_optional_module("__docmirror_missing_optional__", feature="OCR", extra="ocr")

    exc = exc_info.value
    assert exc.feature == "OCR"
    assert exc.missing == ("__docmirror_missing_optional__",)
    assert exc.install_hint == "pip install 'docmirror[ocr]'"
    assert "Install with: pip install 'docmirror[ocr]'" in str(exc)


def test_require_optional_modules_reports_all_missing_modules() -> None:
    with pytest.raises(FeatureUnavailableError) as exc_info:
        require_optional_modules(
            ("json", "__docmirror_missing_a__", "__docmirror_missing_b__"),
            feature="AI",
            extra="ai",
        )

    assert exc_info.value.missing == ("__docmirror_missing_a__", "__docmirror_missing_b__")
