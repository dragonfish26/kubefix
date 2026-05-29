"""Algo 2: label intersection."""

from collections import defaultdict, namedtuple
from pathlib import Path

import yaml

from kubefix.edges import compute_rid, create_new_nodes, process_edges
from kubefix.edges.helpers import query_path


Warning_ = namedtuple("Warning_", ["resource_kind", "resource_name", "message"])


# Cluster labels in order of strength (strongest first). Same list as the
# old algo. Lower index = stronger cluster.
LABEL_HIERARCHY = [
    "app.kubernetes.io/instance",
    "release",
    "helm.sh/chart",
    "chart",
    "app.kubernetes.io/name",
    "app",
    "app.kubernetes.io/component",
    "service",
    "tier",
    "helm.sh/hook",
]
_LABEL_TO_INDEX = {label: i for i, label in enumerate(LABEL_HIERARCHY)}


# Default location of the edges config. Override via the function arg
# if your layout is different.
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "edges" / "kubefix.yaml"


def _load_config(config_path):
    with open(config_path) as f:
        return yaml.safe_load(f)


def _cluster_label_keys(config):
    """Labels that map to clusters in kubefix.yaml. Only these labels
    are eligible for the intersection — others (selectors, etc.) are
    ignored. Falls back to LABEL_HIERARCHY if the config has no
    clusters section, since the two lists overlap heavily anyway."""
    keys = [c.get("label") for c in config.get("clusters", []) if "label" in c]
    return keys if keys else list(LABEL_HIERARCHY)


def _build_parent_and_child_maps(edges):
    """parent_map[to_id]  = list of rids pointing AT to_id
       child_map[from_id] = list of rids that from_id points TO"""
    parent_map = defaultdict(list)
    child_map = defaultdict(list)
    for from_id, to_id, _kind in edges:
        parent_map[to_id].append(from_id)
        child_map[from_id].append(to_id)
    return parent_map, child_map


def _get_intersection(rid, related_map, resources_by_rid, cluster_label_keys):
    """Intersection of cluster-labels across the related resources."""
    related_ids = related_map.get(rid, [])
    if not related_ids:
        return None

    label_sets = []
    for related_rid in related_ids:
        related = resources_by_rid.get(related_rid)
        if related is None:
            continue
        labels = query_path(related, "metadata.labels", {}) or {}
        cluster_labels = {k: v for k, v in labels.items() if k in cluster_label_keys}
        label_sets.append(set(cluster_labels.items()))

    if not label_sets:
        return None
    return dict(set.intersection(*label_sets))


def _has_inter_labels(resource, intersection, cluster_label_keys):
    """True if the resource already has every key in `intersection` set as
    one of its cluster-labels."""
    labels = query_path(resource, "metadata.labels") or {}
    resource_cluster_keys = {k for k in labels if k in cluster_label_keys}
    return set(intersection.keys()).issubset(resource_cluster_keys)


def _can_be_moved(resource, intersection, cluster_label_keys):
    """Check label-hierarchy rules before assigning. Two ways to allow:

       Case 1: the resource's cluster-labels are a subset of the
               intersection (same keys, same values), and the extra
               labels are all WEAKER than what the resource already has.
       Case 2: the resource's strongest label is not stronger than the
               intersection's weakest. (Otherwise applying would put
               the resource into a weaker cluster than it deserves.)

       Returns False if the resource already has these labels (no point
       moving) or if neither case applies.
    """
    if _has_inter_labels(resource, intersection, cluster_label_keys):
        return False

    labels = query_path(resource, "metadata.labels") or {}
    if not isinstance(labels, dict):
        return True

    resource_labels = {k: v for k, v in labels.items() if k in cluster_label_keys}

    resource_label_indices = sorted(
        _LABEL_TO_INDEX[l] for l in resource_labels if l in _LABEL_TO_INDEX
    )
    intersection_label_indices = sorted(
        _LABEL_TO_INDEX[l] for l in intersection if l in _LABEL_TO_INDEX
    )

    if not resource_label_indices:
        return True

    # Case 1
    intersection_items = set(intersection.items())
    resource_items = set(resource_labels.items())
    if resource_items.issubset(intersection_items):
        extras = intersection_items - resource_items
        extra_indices = [_LABEL_TO_INDEX[k] for k, _ in extras if k in _LABEL_TO_INDEX]
        if all(idx > max(resource_label_indices) for idx in extra_indices):
            return True

    # Case 2
    if not intersection_label_indices:
        return True
    resource_strongest = resource_label_indices[0]
    intersection_weakest = intersection_label_indices[-1]
    if resource_strongest < intersection_weakest:
        return False

    return True


def _assign(resource, intersection, cluster_label_keys):
    """Write the intersection labels onto the resource. Returns True if a
    change was made."""
    if not intersection:
        return False
    if not _can_be_moved(resource, intersection, cluster_label_keys):
        return False

    labels = query_path(resource, "metadata.labels")
    if not isinstance(labels, dict):
        labels = {}
        if "metadata" not in resource:
            resource["metadata"] = {}
        resource["metadata"]["labels"] = labels

    labels.update(intersection)
    return True


def algo2_label_intersection(resources, config_path=None):
    """Pull resources into stronger clusters by copying labels that all
    their parents (or all their children) have in common.

    `resources` is the list loaded by main.py. We compute edges with the
    edges package, build parent/child maps, then mutate labels in place.

    Returns (resources, warnings).
    """
    config_path = config_path or _DEFAULT_CONFIG_PATH
    config = _load_config(config_path)
    cluster_label_keys = _cluster_label_keys(config)

    # Build {rid: resource} so the edges code can resolve targets. Same
    # objects as in `resources` (by reference), so mutations propagate.
    resources_by_rid = {compute_rid(r, config): r for r in resources}

    # Synthesise PVCs etc., then compute edges.
    create_new_nodes(resources_by_rid, config)
    edges = process_edges(resources_by_rid, config)

    parent_map, child_map = _build_parent_and_child_maps(edges)

    warnings = []

    # Two passes : parents pull children, then
    # children pull parents.
    for related_map in (parent_map, child_map):
        for resource in resources:
            rid = compute_rid(resource, config)
            inter = _get_intersection(
                rid, related_map, resources_by_rid, cluster_label_keys
            )
            if not inter:
                continue
            _assign(resource, inter, cluster_label_keys)

    return resources, warnings