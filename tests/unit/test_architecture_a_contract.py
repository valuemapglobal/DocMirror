# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Architecture A contract gate tests."""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import patch

import pytest

from docmirror.models.entities.parse_result import DocumentEntities, ParseResult, ResultStatus
from docmirror.models.sealed import seal_parse_result
from docmirror.plugins._runtime.composition import CompositionReason
from docmirror.server.output_builder import build_all_projections

_REMOVED_DELIVERY_PARAMETERS = {
    "format",
    "formats",
    "edition",
    "editions",
    "geometry",
    "include_geometry",
    "include_text",
    "mirror_level",
    "output_profile",
}


def test_delivery_functions_have_no_output_selection_parameters():
    from docmirror.__main__ import parse_document
    from docmirror.sdk.client import AsyncDocMirrorClient, DocMirrorClient
    from docmirror.server.edition_outputs import write_outputs

    functions = (
        build_all_projections,
        write_outputs,
        parse_document,
        DocMirrorClient.parse,
        AsyncDocMirrorClient.parse,
    )
    for function in functions:
        assert not set(inspect.signature(function).parameters) & _REMOVED_DELIVERY_PARAMETERS


def test_mirror_snapshot_before_editions():
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="business_license")
    order: list[str] = []

    def _extended(*args, **kwargs):
        ed = args[1] if len(args) > 1 else kwargs.get("edition", "unknown")
        order.append(ed)
        return {"edition": ed}

    with patch(
        "docmirror.models.mirror.core.MirrorCoreVNext.process",
        side_effect=lambda *_a, **_kw: order.append("mirror") or {"mirror": {}},
    ):

        with patch("docmirror.server.output_builder.build_extended_output", side_effect=_extended):
            build_all_projections(seal_parse_result(result))

    assert order[0] == "mirror"
    assert set(order[1:]) == {"enterprise", "finance"}


def test_extended_projection_has_composition_reason():
    result = ParseResult(status=ResultStatus.SUCCESS)
    result.entities = DocumentEntities(document_type="business_license")

    with patch(
        "docmirror.server.output_builder.build_extended_output",
        return_value={"edition": "enterprise", "metadata": {}, "status": {"warnings": []}},
    ):
        outputs = build_all_projections(seal_parse_result(result))

    assert outputs["enterprise"] is not None
    assert outputs["enterprise"]["composition"]["reason"] == CompositionReason.INDEPENDENT_EXTRACT.value


def test_parse_result_has_no_intermediate_domain_model():
    result = ParseResult()
    assert not hasattr(result, "domain")


def test_community_projector_does_not_require_domain_extraction():
    from docmirror.models.sealed import seal_parse_result
    from docmirror.output.community_bundle import project_community_bundle

    result = ParseResult(entities=DocumentEntities(document_type="generic"))
    bundle = project_community_bundle(seal_parse_result(result), document_id="doc_direct")
    assert bundle.document["id"] == "doc_direct"
    source = inspect.getsource(project_community_bundle)
    assert "run_plugin_extract" not in source
    assert "ensure_domain_extracted" not in source


def test_removed_domain_layer_files_do_not_exist():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "docmirror/models/entities/normalized_domain.py").exists()
    assert not (root / "docmirror/framework/middlewares/extraction/domain_extractor.py").exists()
    assert not (root / "docmirror/plugins/_runtime/domain_enrichment.py").exists()


def test_removed_projection_dag_files_do_not_exist():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "docmirror/server/projection_dag.py").exists()
    assert not (root / "docmirror/server/projection_visualizer.py").exists()
    assert not (root / "docmirror/server/output_plan.py").exists()
    assert not (root / "docmirror/server/output_selection.py").exists()
    assert not (root / "docmirror/configs/output_profile.py").exists()
    assert not (root / "docmirror/runtime/profiles.py").exists()
    assert not (root / "docmirror/framework/edition_defaults.py").exists()
    assert not (root / "docmirror/framework/delivery_contract.py").exists()
    assert not (root / "docmirror/server/edition_access.py").exists()
    assert not (root / "docmirror/models/semantic_store.py").exists()
    assert not (root / "docmirror/topology/document_graph.py").exists()
    assert not (root / "docmirror/domains/registry.py").exists()
    assert not (root / "docmirror/errors/envelope.py").exists()
    assert not (root / "docmirror/cli/explainability_commands.py").exists()
    assert not (root / "docmirror/ocr/correction/report.py").exists()


def test_dispatcher_accepts_only_accepted_source_and_has_no_validation_stage():
    root = Path(__file__).resolve().parents[2]
    source = (root / "docmirror/framework/dispatcher.py").read_text(encoding="utf-8")
    assert "source: AcceptedSource" in source
    assert "def _validate" not in source
    assert "resolve_capability" not in source
    assert "compute_checksum" not in source
    assert "parse_cache" not in source


def test_removed_request_wrapper_types_are_absent():
    root = Path(__file__).resolve().parents[2]
    source = (root / "docmirror/input/entry/options.py").read_text(encoding="utf-8")
    assert "class Parse" + "Control" not in source
    assert "class Delivery" + "Request" not in source
    assert "class Execution" + "Policy" not in source
    assert "class Execution" + "Control" not in source
    assert "class Resource" + "Control" not in source
    assert "class Output" + "Control" not in source


def test_parse_cache_layer_is_absent():
    root = Path(__file__).resolve().parents[2]
    assert not (root / "docmirror/framework/cache.py").exists()
    assert not (root / "docmirror/framework/execution_fingerprint.py").exists()


def test_obsolete_intermediate_result_layer_is_absent():
    root = Path(__file__).resolve().parents[2]
    obsolete_package = root / "docmirror/input" / "bridge"
    assert not obsolete_package.exists() or not any(obsolete_package.rglob("*.py"))
    physical_source = (root / "docmirror/models/entities/physical.py").read_text(encoding="utf-8")
    model_exports = (root / "docmirror/models/entities/__init__.py").read_text(encoding="utf-8")
    extractor_source = (root / "docmirror/input/extraction/extractor.py").read_text(encoding="utf-8")
    assert "class Base" + "Result" not in physical_source
    assert "Base" + "Result" not in model_exports
    assert "input." + "bridge" not in extractor_source


def test_projection_path_cannot_run_fact_recognition_or_attach_mirror_cache():
    root = Path(__file__).resolve().parents[2]
    source = (root / "docmirror/server/output_builder.py").read_text(encoding="utf-8")
    method = inspect.getsource(build_all_projections)
    assert "run_plugin_extract_sync" not in method
    assert "_runtime_mirror_cache" not in source
    assert "expects SealedParseResult" in method
    assert "seal_parse_result" not in method
    assert "sealed.to_read_view()" in method
    assert "sealed.verify_integrity()" in method
    assert "serialize_dmir" not in source
    assert "available_editions" not in source


def test_projection_builder_accepts_sealed_parse_result_only():
    with pytest.raises(TypeError, match="expects SealedParseResult"):
        build_all_projections({"mirror": {"schema": "docmirror.mirror_json"}})


def test_parse_result_contains_facts_not_mirror_projection():
    assert not hasattr(ParseResult(), "to_mirror_json_vnext")
    source = inspect.getsource(ParseResult)
    assert "MirrorCore" not in source
    assert "project_mirror" not in source


def test_plugins_never_build_or_read_a_mirror_projection():
    root = Path(__file__).resolve().parents[2]
    plugin_root = root / "docmirror/plugins"
    source = "\n".join(path.read_text(encoding="utf-8") for path in plugin_root.rglob("*.py"))
    assert "to_mirror_json_vnext" not in source
    assert "MirrorCore" not in source
    assert "models.mirror.vnext_access" not in source
