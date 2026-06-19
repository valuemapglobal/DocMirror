from docmirror.configs.runtime.performance import resolve_worker_budget
from docmirror.core.entry.options import normalize_parse_control, parse_output_formats, parse_page_selection
from docmirror.exporters.dispatch import EXPORTER_REGISTRY
import pytest


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


def test_output_formats_accept_legacy_aliases_and_all():
    assert parse_output_formats("text,rag") == ("markdown", "chunks")
    assert parse_output_formats("all") == ("json", "markdown", "csv", "chunks", "html", "parquet")


def test_exporter_registry_contains_non_json_formats():
    assert {"chunks", "html", "csv", "parquet"}.issubset(set(EXPORTER_REGISTRY.formats()))


def test_forensic_mode_promotes_mirror_level():
    control = normalize_parse_control(mode="forensic", mirror_level="standard")

    assert control.enhance_mode == "full"
    assert control.output.mirror_level == "forensic"


def test_worker_budget_splits_batch_budget():
    budget = resolve_worker_budget(8, file_count=4, page_count=20, cpu_count=8)

    assert budget.total == 8
    assert budget.file_workers == 4
    assert budget.page_workers_per_file == 2
    assert budget.layout_workers == 2


def test_slim_mirror_level_rejected():
    with pytest.raises(ValueError, match="unsupported mirror level: slim"):
        normalize_parse_control(mirror_level="slim")
