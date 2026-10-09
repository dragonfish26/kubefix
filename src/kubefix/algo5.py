"""Algo 5: connected-component label union."""

from collections import defaultdict

from kubefix.edges import compute_rid, create_new_nodes, process_edges
from kubefix.edges.helpers import query_path

from kubefix.algo2 import _DEFAULT_CONFIG_PATH, _load_config, _cluster_label_keys
from kubefix.common import Warning, Stat


def _build_adjacency(edges):
    """Builds a dict of undirected adjacency: 
    adj[rid] = set of rids linked to rid by an edge, in either direction.
    """
    adj = defaultdict(set)
    for from_id, to_id, _kind in edges:
        adj[from_id].add(to_id)
        adj[to_id].add(from_id)
    return adj


def _connected_components(rids, adj):
    """Returns a list of connected components (each a set of rids), found by BFS."""
    seen = set()
    components = []
    for start in rids:
        if start in seen:
            continue
        component = set()
        queue = [start]
        seen.add(start)
        while queue:
            rid = queue.pop()
            component.add(rid)
            for neighbour in adj.get(rid, ()):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        components.append(component)
    return components


def _get_union(component, resources_by_rid, cluster_label_keys):
    """Union of cluster-labels across the component.
    Returns None if two resources have the same cluster-label with different
    values (collision)."""
    union = {}
    for rid in component:
        resource = resources_by_rid.get(rid)
        if resource is None:
            continue
        labels = query_path(resource, "metadata.labels", {}) or {}
        for k, v in labels.items():
            if k not in cluster_label_keys:
                continue
            if k in union and union[k] != v:
                return None
            union[k] = v
    return union


def _assign(resource, union):
    """Write the union labels onto the resource.
    Returns the number of labels added."""
    labels = query_path(resource, "metadata.labels")
    if not isinstance(labels, dict):
        labels = {}
        if "metadata" not in resource:
            resource["metadata"] = {}
        resource["metadata"]["labels"] = labels

    # no collision in the union, so we can only add keys, never change values
    to_add = {k: v for k, v in union.items() if k not in labels}
    labels.update(to_add)
    return len(to_add)


def algo5_component_label_union(resources, config_path=None):
    """Give every resource of a connected component the union of the
    component's cluster-labels, if no cluster-label appears with two
    different values in that component.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings, stats).
    """
    config_path = config_path or _DEFAULT_CONFIG_PATH
    config = _load_config(config_path)
    cluster_label_keys = _cluster_label_keys(config)

    # Build {rid: resource} so the edges code can resolve targets. Same
    # objects as in `resources` (by reference), so mutations propagate.
    resources_by_rid = {compute_rid(r, config): r for r in resources}

    # Synthesise PVCs etc, then compute edges. 
    create_new_nodes(resources_by_rid, config)
    edges = process_edges(resources_by_rid, config)

    adj = _build_adjacency(edges)
    output_rids = {compute_rid(r, config) for r in resources} #list of rids, excluding synthetic nodes.

    warnings: list[Warning] = []
    stats: list[Stat] = []

    for component in _connected_components(list(resources_by_rid), adj):
        if len(component) < 2:
            continue
        union = _get_union(component, resources_by_rid, cluster_label_keys)
        if not union:
            continue

        for rid in component:
            # skip synthetic resources and avoid modifying them in the manifest
            if rid not in output_rids:
                continue
            resource = resources_by_rid[rid]
            count = _assign(resource, union)
            if count > 0:
                stats.append(Stat(
                    resource_kind=resource.get("kind", "?"),
                    resource_name=query_path(resource, "metadata.name", "?"),
                    changed_labels=count,
                ))

    return resources, warnings, stats
