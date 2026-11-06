"""Name/extend a component for connected resources of the same cluster."""

import re

from kubefix.edges import compute_rid, create_new_nodes, process_edges
from kubefix.edges.helpers import query_path

from kubefix.algo_label_intersection import _DEFAULT_CONFIG_PATH, _load_config, _cluster_label_keys
from kubefix.algo_add_proximity_labels import _build_adjacency
from kubefix.common import Warning, Stat

COMPONENT_LABEL = "app.kubernetes.io/component"
APPLICATION_LABEL = "app.kubernetes.io/name"

# Below this length the common substring is meaningless,
# so DEFAULT_COMPONENT_NAME is used instead.
MIN_COMPONENT_LENGTH = 3
DEFAULT_COMPONENT_NAME = "suggested_component"


_MAX_LABEL_VALUE_LENGTH = 63
_INVALID_LABEL_CHARS = re.compile(r"[^A-Za-z0-9_.-]")


def _labels(resource):
    """Returns the labels of a resource ({} if none)."""
    return query_path(resource, "metadata.labels", {}) or {}


def _cluster_labels(resource, cluster_label_keys):
    """Returns the cluster labels of a resource."""
    return {k: v for k, v in _labels(resource).items() if k in cluster_label_keys}


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


def _name_component(members, warnings):
    """Component name for members: the longest common substring of their names,
    or DEFAULT_COMPONENT_NAME (with a warning) when it is too short."""
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
    return value


def _set_component_label(resource, value):
    """Set the component label of a resource, creating metadata.labels if needed."""
    labels = query_path(resource, "metadata.labels")
    if not isinstance(labels, dict):
        labels = {}
        if "metadata" not in resource:
            resource["metadata"] = {}
        resource["metadata"]["labels"] = labels
    labels[COMPONENT_LABEL] = value


def _component_stat(resource):
    return Stat(
        resource_kind=resource.get("kind", "?"),
        resource_name=query_path(resource, "metadata.name", "?"),
        changed_labels=1,
    )


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


def _component_within_application(resources_by_rid, output_rids, adj, warnings):
    """For each K8s application with at least two resources that form a single
    connected component among themselves:
      - if exactly one component label value is used, give it to all of its resources that lack one;
      - if no component label is used, give them all a new component label
        named after the longest common substring of their names.

    Applications with several component values or several connected
    components are skipped for now.

    Returns the list of stats for the labelled resources.
    """
    apps = {}
    for rid in output_rids:
        app = _labels(resources_by_rid[rid]).get(APPLICATION_LABEL)
        if app is not None:
            apps.setdefault(app, set()).add(rid)

    stats = []
    for app_rids in apps.values():
        # skip if there are fewer than 2 resources within the application
        if len(app_rids) <= 1:
            continue

        # Connectivity among the application's resources only.
        app_adj = {rid: adj.get(rid, set()) & app_rids for rid in app_rids}
        if len(_connected_components(list(app_rids), app_adj)) != 1:
            continue

        members = [resources_by_rid[rid] for rid in app_rids]
        values = {_labels(r)[COMPONENT_LABEL] for r in members if COMPONENT_LABEL in _labels(r)}
        if len(values) == 1:
            value = next(iter(values))
        elif not values:
            value = _name_component(members, warnings)
        else:
            continue

        for resource in members:
            if COMPONENT_LABEL in _labels(resource):
                continue
            _set_component_label(resource, value)
            stats.append(_component_stat(resource))
    return stats


def algo_name_component(resources, config_path=None):
    """For each connected component whose resources all share the same cluster-labels and none has a component label, 
    give them all a component label named after the longest common substring of their names.

    Single-resource components are skipped. Synthesised nodes take part in the connectivity but are not checked, named or labelled.

    Then, within each K8s application whose resources are connected among themselves, the single component label value used
    is given to the remaining resources, or, if none is used, a new component is named for all of them.

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

        value = _name_component(members, warnings)
        for resource in members:
            _set_component_label(resource, value)
            stats.append(_component_stat(resource))

    stats.extend(_component_within_application(resources_by_rid, output_rids, adj, warnings))

    return resources, warnings, stats
