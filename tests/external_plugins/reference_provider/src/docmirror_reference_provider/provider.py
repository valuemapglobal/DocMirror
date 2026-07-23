"""A provider implemented exclusively against DocMirror's public plugin API."""

from __future__ import annotations

from docmirror.plugin_api import FactPatch, PluginProvider, hookimpl


class ReferenceRecognizer:
    provider_id = "reference-provider"
    domain_name = "reference_document"

    def recognize_facts(self, result, text: str = "") -> FactPatch:
        return FactPatch(
            provider_id=self.provider_id,
            document_type=self.domain_name,
            domain_facts={"reference_word_count": len((text or result.full_text).split())},
            reason="reference external recognizer",
        )


@hookimpl
def docmirror_plugin_provider() -> PluginProvider:
    return PluginProvider(
        provider_id="reference-provider",
        version="0.1.0",
        api_version="1",
        recognizers=(ReferenceRecognizer(),),
    )
