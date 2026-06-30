import pytest

from docmirror.configs.runtime.performance import resolve_worker_budget
from docmirror.input.entry.options import (
    OutputControl,
    ParseControl,
    normalize_parse_control,
    parse_editions,
    parse_output_formats,
    parse_page_selection,
)
from docmirror.output.exporters.dispatch import EXPORTER_REGISTRY


def test_page_selection_resolves_ranges_and_max_pages():
    selection = parse_page_selection("2-3,5-", max_pages=3)

    assert selection.resolve(8) == [1, 2, 4]
    assert selection.to_display() == "2-3,5- (max 3)"


def test_large_document_page_selection_is_sparse_and_original_numbered():
    selection = parse_page_selection("5-6,100,150-", max_pages=4)

    assert selection.resolve(200) == [4, 5, 99, 149]


def test_last_page_selection_resolves_from_document_end():
    selection = parse_page_selection("last:2")

    assert selection.resolve(10) == [8, 9]
    assert selection.to_display() == "last:2"


def test_parse_control_maps_mode_to_enhance_mode_and_fingerprint_ignores_workers():
    a = normalize_parse_control(mode="fast", workers=1, formats="json,csv", doc_type_hint="bank_statement")
    b = normalize_parse_control(mode="fast", workers=8, formats="json,csv", doc_type_hint="bank_statement")

    assert a.enhance_mode == "raw"
    assert a.output.formats == ("json", "csv")
    assert a.doc_type_hint is not None
    assert a.doc_type_hint.value == "bank_statement"
    assert a.fingerprint() == b.fingerprint()


def test_auto_mode_records_resolution_decision():
    control = normalize_parse_control(mode="auto")

    assert control.enhance_mode == "standard"
    assert control.mode_decision["resolved_profile"] == "balanced"


def test_output_formats_accept_public_aliases_and_all():
    assert parse_output_formats("text,rag") == ("markdown", "chunks")
    assert parse_output_formats("all") == ("json", "markdown", "csv", "chunks", "html", "parquet")


def test_editions_accept_all_and_dedupe():
    assert parse_editions("mirror,community,mirror") == ("mirror", "community")
    assert parse_editions("finance") == ("mirror", "finance")
    assert parse_editions("all") == ("mirror", "community", "enterprise", "finance")


def test_cache_policy_replaces_skip_cache_boolean():
    refresh = normalize_parse_control(cache_policy="refresh")
    off = normalize_parse_control(cache_policy="off")
    read_only = normalize_parse_control(cache_policy="read-only")

    assert refresh.cache_policy == "refresh"
    assert refresh.skip_cache is True
    assert off.cache_policy == "off"
    assert off.skip_cache is True
    assert read_only.cache_policy == "read-only"
    assert read_only.skip_cache is False


def test_doc_type_and_policy_replace_hint():
    control = normalize_parse_control(doc_type="bank_statement", doc_type_policy="force")

    assert control.doc_type_hint is not None
    assert control.doc_type_hint.value == "bank_statement"
    assert control.doc_type_hint.strength == "force"


def test_ocr_geometry_and_editions_are_normalized():
    control = normalize_parse_control(
        editions="mirror,finance",
        ocr="force",
        geometry="full",
        mirror_level="standard",
    )

    assert control.execution.ocr == "force"
    assert control.output.editions == ("mirror", "finance")
    assert control.output.geometry == "full"
    assert control.output.mirror_level == "forensic"
    assert any(item["from"] == "geometry=full" for item in control.implicit_promotions)


def test_exporter_registry_contains_non_json_formats():
    assert {"chunks", "html", "csv", "parquet"}.issubset(set(EXPORTER_REGISTRY.formats()))


def test_forensic_mode_promotes_mirror_level():
    control = normalize_parse_control(mode="forensic")

    assert control.enhance_mode == "full"
    assert control.output.mirror_level == "forensic"


def test_explicit_standard_mirror_level_is_respected_in_forensic_mode():
    control = normalize_parse_control(mode="forensic", mirror_level="standard")

    assert control.enhance_mode == "full"
    assert control.output.mirror_level == "standard"


def test_compact_mirror_level_is_supported():
    control = normalize_parse_control(mirror_level="compact")

    assert control.output.mirror_level == "compact"


def test_worker_budget_splits_batch_budget():
    budget = resolve_worker_budget(8, file_count=4, page_count=20, cpu_count=8)

    assert budget.total == 8
    assert budget.file_workers == 4
    assert budget.page_workers_per_file == 2
    assert budget.layout_workers == 2


def test_slim_mirror_level_rejected():
    with pytest.raises(ValueError, match="unsupported mirror level: slim"):
        normalize_parse_control(mirror_level="slim")


def test_output_control_default_editions_is_license_aware():
    """GA1.0: OutputControl() must resolve editions from license, not hardcode paid tiers."""
    oc = OutputControl()
    assert oc.editions[:2] == ("mirror", "community")

    pc = ParseControl()
    assert pc.output.editions == oc.editions
