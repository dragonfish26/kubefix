"""Name a component for connected resources of the same cluster."""

import re

from kubefix.edges import compute_rid, create_new_nodes, process_edges
from kubefix.edges.helpers import query_path

from kubefix.algo_label_intersection import _DEFAULT_CONFIG_PATH, _load_config, _cluster_label_keys
from kubefix.algo_comp_label_union import _build_adjacency, _connected_components
from kubefix.common import Warning, Stat

COMPONENT_LABEL = "app.kubernetes.io/component"

# Below this length the common substring is meaningless,
# so DEFAULT_COMPONENT_NAME is used instead.
MIN_COMPONENT_LENGTH = 3
DEFAULT_COMPONENT_NAME = "suggested_component"


_MAX_LABEL_VALUE_LENGTH = 63
_INVALID_LABEL_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _cluster_labels(resource, cluster_label_keys):
    """Returns the cluster labels of a resource."""
    labels = query_path(resource, "metadata.labels", {}) or {}
    return {k: v for k, v in labels.items() if k in cluster_label_keys}


def _longest_common_substring(names):
    """Longest continuous string present in every name. 
    Ties go to the leftmost one in the shortest name."""
    shortest = min(names, key=lambda n: (len(n), n))
    for length in range(len(shortest), 0, -1):
        for start in range(len(shortest) - length + 1):
            candidate = shortest[start:start + length]
            if all(candidate in name for name in names):
                return candidate
    return ""


def _to_label_value(s):
    """Make s a valid label value: replace invalid chars by -, 
    cut to max number of chars, strip non-alphanumeric chars at both ends."""
    s = _INVALID_LABEL_CHARS.sub("-", s)[:_MAX_LABEL_VALUE_LENGTH]
    return s.strip("-_.")


def algo_name_component(resources, config_path=None):
    """For each connected component whose resources all share the same
    cluster-labels and none has a component label, give them all a
    component label named after the longest common substring of their names.

    Single-resource components are skipped. Synthesised nodes take part in
    the connectivity but are not checked, named or labelled.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings, stats).
    """
    config_path = config_path or _DEFAULT_CONFIG_PATH
    config = _load_config(config_path)
    cluster_label_keys = _cluster_label_keys(config)

    # Same objects as in `resources` (by reference), so mutations propagate.
    resources_by_rid = {compute_rid(r, config): r for r in resources}
    output_rids = set(resources_by_rid)

    create_new_nodes(resources_by_rid, config)
    edges = process_edges(resources_by_rid, config)

    adj = _build_adjacency(edges)

    warnings: list[Warning] = []
    stats: list[Stat] = []

    for component in _connected_components(list(resources_by_rid), adj):
        members = [resources_by_rid[rid] for rid in component if rid in output_rids]
        if len(members) < 2:
            continue

        # all resources must be in the same clusters.
        cluster_labels = _cluster_labels(members[0], cluster_label_keys)
        if any(_cluster_labels(r, cluster_label_keys) != cluster_labels for r in members[1:]):
            continue

        # none of them has a component label yet.
        if COMPONENT_LABEL in cluster_labels:
            continue

        names = [query_path(r, "metadata.name", "") or "" for r in members]
        value = _to_label_value(_longest_common_substring(names))
        if len(value) < MIN_COMPONENT_LENGTH:
            warnings.append(Warning(
                resource_kind=members[0].get("kind", "?"),
                resource_name=names[0],
                message=f"No common name for {sorted(names)}; "
                        f"using default component '{DEFAULT_COMPONENT_NAME}'.",
            ))
            value = DEFAULT_COMPONENT_NAME

        for resource in members:
            labels = query_path(resource, "metadata.labels")
            if not isinstance(labels, dict):
                labels = {}
                if "metadata" not in resource:
                    resource["metadata"] = {}
                resource["metadata"]["labels"] = labels
            labels[COMPONENT_LABEL] = value

            stats.append(Stat(
                resource_kind=resource.get("kind", "?"),
                resource_name=query_path(resource, "metadata.name", "?"),
                changed_labels=1,
            ))

    return resources, warnings, stats
