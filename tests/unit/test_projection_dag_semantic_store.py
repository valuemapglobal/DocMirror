# Copyright (c) 2026 ValueMap Global and contributors. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from docmirror.models.semantic_store import SemanticStore
from docmirror.server.projection_dag import ProjectionDAG, ProjectionNode, architecture_a_projection_dag
from docmirror.server.projection_visualizer import projection_dag_to_json, projection_dag_to_mermaid


def test_architecture_a_projection_dag_order_and_visualization():
    dag = architecture_a_projection_dag(("community", "enterprise", "finance"))

    assert dag.topological_order()[0] == "mirror"
    assert dag.nodes["enterprise"].depends_on == ("mirror", "community")

    graph_json = projection_dag_to_json(dag)
    mermaid = projection_dag_to_mermaid(dag)

    assert graph_json["order"][0] == "mirror"
    assert "community --> enterprise" in mermaid
    assert "community --> finance" in mermaid


def test_projection_dag_executes_in_dependency_order():
    dag = ProjectionDAG()
    dag.add(ProjectionNode("mirror", build=lambda _ctx: {"fact": 1}))
    dag.add(ProjectionNode("community", depends_on=("mirror",), build=lambda ctx: {"from": ctx["mirror"]["fact"]}))

    outputs = dag.run()

    assert outputs["mirror"]["fact"] == 1
    assert outputs["community"]["from"] == 1


def test_projection_dag_rejects_missing_dependency():
    dag = ProjectionDAG()
    dag.add(ProjectionNode("community", depends_on=("mirror",)))

    with pytest.raises(ValueError, match="missing node"):
        dag.topological_order()


def test_semantic_store_keeps_edition_semantics_out_of_mirror_bucket():
    store = SemanticStore.from_domain_specific(
        {
            "plugin_document_type": "bank_statement",
            "entity_merge_hints": [{"id": "a"}],
            "reasoning_traces": [{"step": "x"}],
        },
        edition="finance",
    )

    projected = store.project(edition="finance")

    assert "entity_merge_hints" in projected
    assert "reasoning_traces" in projected
    assert "plugin_document_type" not in projected
