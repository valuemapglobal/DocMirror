"""A provider implemented exclusively against DocMirror's public plugin API."""

from __future__ import annotations

from docmirror.plugin_api import PluginProvider, hookimpl


class ReferenceProjector:
    domain_name = "reference_document"
    edition = "enterprise"

    def project(self, result):
        view = result.to_read_view()
        reference_word_count = len((view.full_text or view.raw_text).split())
        return {
            "edition": self.edition,
            "document": {"document_type": view.entities.document_type},
            "data": {"reference_word_count": reference_word_count},
            "sealed_fact_fingerprint": result.fact_fingerprint(),
        }


@hookimpl
def docmirror_plugin_provider() -> PluginProvider:
    return PluginProvider(
        provider_id="reference-provider",
        version="2.0.0",
        api_version="2",
        projectors=(ReferenceProjector(),),
        resource_package="docmirror_reference_provider",
        resources={"output_template": "resources/classification.yaml"},
    )
