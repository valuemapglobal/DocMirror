"""RegionGraph detector namespace.

Current detectors still live in PageTopologyBuilder. This module names the
future detector boundary and keeps imports stable for incremental migration.
"""

DEFAULT_DETECTOR_IDS = (
    "visual_artifact_region",
    "image_atom_region",
    "vector_atom_group",
    "table_metadata_group",
    "page_evidence_bundle",
    "page_canvas_region",
    "segment_page_blocks",
    "implicit_grid_text_atoms",
    "page_topology_text_region",
)
