from __future__ import annotations

from docmirror.input.bridge.parse_result_bridge import ParseResultBridge
from docmirror.models.entities.domain import BaseResult, Block, PageLayout, TextSpan
from docmirror.models.mirror.core import MirrorCoreVNext


def test_mirror_projects_ocr_correction_audit_without_losing_source_text():
    event = {
        "event_id": "corr:000001",
        "source_ref": "ocr:p0001:0001",
        "original": "Microsofl Corporation",
        "corrected": "Microsoft Corporation",
        "action": "applied",
        "rule_id": "lexicon.unique_candidate",
        "reason_codes": ["unique_candidate"],
        "score": 0.9,
        "role": "text_line",
        "pack_id": "en.business",
        "pack_version": 1,
        "language": "en",
        "country": "US",
        "locale": "en-US",
        "selected_pack_ids": ["builtin.legacy", "en.business"],
    }
    audit = {
        "mode": "safe",
        "rules_version": 1,
        "processed_count": 1,
        "applied_count": 1,
        "suggested_count": 0,
        "unchanged_count": 0,
        "selected_pack_ids": ["builtin.legacy", "en.business"],
        "events": [event],
    }
    block = Block(
        block_id="ocr:p0001:0001",
        block_type="text",
        spans=(TextSpan(text="Microsoft Corporation", bbox=(0.0, 0.0, 10.0, 10.0)),),
        bbox=(0.0, 0.0, 10.0, 10.0),
        page=1,
        raw_content="Microsoft Corporation",
        attrs={
            "ocr_source": "rapidocr",
            "confidence": 0.8,
            "ocr_original_text": "Microsofl Corporation",
            "ocr_correction": event,
        },
        evidence_ids=("ocr:p0001:0001",),
    )
    base = BaseResult(
        pages=(PageLayout(page_number=1, blocks=(block,), is_scanned=True),),
        metadata={
            "parser": "test",
            "extraction_method": "ocr",
            "overall_confidence": 0.8,
            "ocr_correction_mode": "safe",
            "ocr_corrections": audit,
        },
        full_text="Microsoft Corporation",
    )

    payload = MirrorCoreVNext().process(ParseResultBridge.from_base_result(base)).to_dict()

    assert payload["mirror"]["schema_version"] == "1.0.4"
    assert payload["quality"]["ocr_correction"]["applied_count"] == 1
    assert payload["evidence"]["indexes"]["ocr_corrections"]["corr:000001"]["original"] == ("Microsofl Corporation")
    atom = payload["evidence"]["text_atoms"][0]
    assert atom["text"] == "Microsoft Corporation"
    assert atom["metadata"]["ocr_original_text"] == "Microsofl Corporation"
    assert atom["metadata"]["ocr_correction_id"] == "corr:000001"
    assert atom["metadata"]["ocr_correction_pack_id"] == "en.business"
    assert atom["metadata"]["ocr_correction_locale"] == "en-US"
