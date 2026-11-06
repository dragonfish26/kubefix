"""For each resource, add the missing cluster-labels of its best neighbor (the eligible neighbor with the most cluster-labels), 
if they don't conflict with the resource or with its other neighbors."""

from collections import defaultdict

from kubefix.edges import compute_rid, create_new_nodes, process_edges
from kubefix.edges.helpers import query_path

from kubefix.algo_label_intersection import _DEFAULT_CONFIG_PATH, _load_config, _cluster_label_keys, _can_be_moved
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


def _cluster_labels(resource, cluster_label_keys):
    """Cluster-labels of a resource, as a dict."""
    labels = query_path(resource, "metadata.labels", {}) or {}
    if not isinstance(labels, dict):
        return {}
    return {k: v for k, v in labels.items() if k in cluster_label_keys}


def _conflicts(labels_a, labels_b):
    """True if a key is present in both with different values."""
    return any(k in labels_b and labels_b[k] != v for k, v in labels_a.items())


def _assign(resource, additional):
    """Write the additional labels onto the resource.
    Returns the number of labels added."""
    labels = query_path(resource, "metadata.labels")
    if not isinstance(labels, dict):
        labels = {}
        if "metadata" not in resource:
            resource["metadata"] = {}
        resource["metadata"]["labels"] = labels

    # never change an existing value, only add missing keys
    to_add = {k: v for k, v in additional.items() if k not in labels}
    labels.update(to_add)
    return len(to_add)


def _get_additional_labels_from_neighbors(resource, neighbor_rids, resources_by_rid, cluster_label_keys):
    """Missing cluster-labels to add to the resource, taken from one neighbor.

    1. A neighbor is eligible if its cluster-labels don't conflict with the
       resource's own and can be assigned to it (label hierarchy rules).
    2. The eligible neighbor with the most cluster-labels is chosen.
    3. If the chosen neighbor conflicts with any other neighbor, nothing is
       added.

    Returns a dict of labels the resource doesn't have yet (possibly empty).
    """
    own_labels = _cluster_labels(resource, cluster_label_keys)

    neighbor_labels = {}
    for n_rid in neighbor_rids:
        neighbor = resources_by_rid.get(n_rid)
        if neighbor is not None:
            neighbor_labels[n_rid] = _cluster_labels(neighbor, cluster_label_keys)

    # 1. keep only neighbors whose labels can be assigned to the resource
    eligible = {
        n_rid: labels for n_rid, labels in neighbor_labels.items()
        if labels
        and not _conflicts(labels, own_labels)
        and _can_be_moved(resource, labels, cluster_label_keys)
    }
    if not eligible:
        return {}

    # 2. neighbor with the most labels (rid as tie-breaker, to be deterministic)
    best_rid = min(eligible, key=lambda n_rid: (-len(eligible[n_rid]), n_rid))
    best_labels = eligible[best_rid]

    # 3. the chosen neighbor must not conflict with any other neighbor
    for n_rid, labels in neighbor_labels.items():
        if n_rid != best_rid and _conflicts(best_labels, labels):
            return {}

    return {k: v for k, v in best_labels.items() if k not in own_labels}


def algo_proximity_labels(resources, config_path=None):
    """Give every resource the missing cluster-labels of its neighbor with
    the most cluster-labels, if no other neighbor has a different value for
    one of these labels and the resource's own labels don't contradict them.
    Repeat until no change happens.

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

    warnings: list[Warning] = []

    # rid -> total labels added across all iterations, so a resource changed
    # several times still gets a single Stat entry.
    changed_labels_by_rid: dict[str, int] = {}

    # Labels are only ever added (never changed) and the set of cluster-label keys is finite, so this loop terminates.
    changed = True
    while changed:
        changed = False

        # Compute every addition from the labels at the start of the pass, so the result doesn't depend on the order of the resources.
        # Only real resources are modified, synthetic nodes are neighbors only.
        pending = {}
        for resource in resources:
            rid = compute_rid(resource, config)
            neighbor_rids = adj.get(rid, set()) - {rid}
            additional = _get_additional_labels_from_neighbors(
                resource, neighbor_rids, resources_by_rid, cluster_label_keys
            )
            if additional:
                pending[rid] = additional

        # Then apply them all at once.
        for rid, additional in pending.items():
            count = _assign(resources_by_rid[rid], additional)
            if count > 0:
                changed_labels_by_rid[rid] = changed_labels_by_rid.get(rid, 0) + count
                changed = True

    stats = [
        Stat(
            resource_kind=resources_by_rid[rid].get("kind", "?"),
            resource_name=query_path(resources_by_rid[rid], "metadata.name", "?"),
            changed_labels=count,
        )
        for rid, count in changed_labels_by_rid.items()
    ]

    return resources, warnings, stats
