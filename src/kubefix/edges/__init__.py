"""Compute kubediagrams-style edges from kubernetes manifests.

Typical use:
    import yaml
    from edges import load_manifests, create_new_nodes, process_edges

    config = yaml.safe_load(open("kubefix.yaml"))
    resources = load_manifests(["my-manifest.yaml"], config)
    create_new_nodes(resources, config)
    edges = process_edges(resources, config)
    # edges is a list of (from_rid, to_rid, edge_kind) tuples
"""

from .edges_context import EdgesContext
from .loader import load_manifests
from .process import (
    compute_rid,
    create_new_nodes,
    create_node_for_role_rules_resource_names,
    process_edges,
)

__all__ = [
    "EdgesContext",
    "compute_rid",
    "create_new_nodes",
    "create_node_for_role_rules_resource_names",
    "load_manifests",
    "process_edges",
]