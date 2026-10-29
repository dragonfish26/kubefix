"""Mark unlabeled resources with an isolated-resource label."""
from kubefix.common import Warning, Stat
from kubefix.common import CLUSTER_LABELS

from kubefix.edges import compute_rid, create_new_nodes, process_edges

from kubefix.algo_label_intersection import _DEFAULT_CONFIG_PATH, _load_config, _build_parent_and_child_maps

ISOLATED_LABEL = "isolated-resource"

RESOURCE_KINDS_WITH_RELATIONS = [
    "Secret",
    "ConfigMap",
    "PodDisruptionBudget",
    "ServiceAccount",
    "NetworkPolicy",
    "ClusterRole",
    "Service",
    "ValidatingWebhookConfiguration",
    "Issuer",
]

def _isolated_by_relation(resources):
    """Add an 'isolated-resource' label to resources who doesn't have any relations 
    (edges calculated by Kubediagrams graph) with other resources, but should have at least one relation.
    This could indicate deadcode and other issues.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (warnings, stats).
    """
    warnings: list[Warning] = []
    stats: list[Stat] = []

    config_path = _DEFAULT_CONFIG_PATH
    config = _load_config(config_path)

    # Build {rid: resource} so the edges code can resolve targets. Same
    # objects as in `resources` (by reference), so mutations propagate.
    resources_by_rid = {compute_rid(r, config): r for r in resources}

    # Synthesise PVCs etc, then compute edges.
    create_new_nodes(resources_by_rid, config)
    edges = process_edges(resources_by_rid, config)
    # INVISIBLE edges aren't drawn, so they don't count as relations
    visible_edges = [e for e in edges if e[2] != "INVISIBLE"]

    parent_map, child_map = _build_parent_and_child_maps(visible_edges)

    for resource in resources:
        label_change_count = 0 #counter for stat
        metadata = resource.setdefault("metadata", {})

        kind = resource.get("kind")
        if kind in RESOURCE_KINDS_WITH_RELATIONS:
            rid = compute_rid(resource, config)
            # if no relations to another resource, mark isolated
            if not parent_map.get(rid) and not child_map.get(rid):
                labels = metadata.get("labels") or {}
                labels[ISOLATED_LABEL] = "no-relations"
                metadata["labels"] = labels

                warnings.append(Warning(
                    resource_kind=resource.get("kind", "?"),
                    resource_name=metadata.get("name", "?"),
                    message="Resource has no relations with other resources but should have at least one; marked as isolated.",
                ))
                label_change_count += 1
    
                stats.append(Stat(
                            resource_kind=resource.get("kind", "?"),
                            resource_name=resource.get("metadata", {}).get("name", "?"),
                            changed_labels=label_change_count
                        ))
                
    return warnings, stats


def algo_mark_isolated(resources):
    """Add an 'isolated-resource' label to any resource without cluster labels and
    resources that don't have any relations with other resources but should have at least one relation. 

    To be run as a last resort for truly resources where truly no label was found. 

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings, stats).
    """
    warnings: list[Warning] = []
    stats: list[Stat] = []

    # 1. check relation isolation
    w, s = _isolated_by_relation(resources)
    warnings.extend(w) 
    stats.extend(s)

    # 2. check label isolation
    for resource in resources:
        label_change_count = 0 #counter for stat

        metadata = resource.setdefault("metadata", {})
        labels = metadata.get("labels") or {}

        # check if there are no labels that are cluster labels for the resource
        #if not labels or not any(key in CLUSTER_LABELS for key in labels):
        if not any(key in CLUSTER_LABELS for key in labels): 
            if labels.get(ISOLATED_LABEL) == "no-relations":
                labels[ISOLATED_LABEL] = "no-relations-no-labels"
            else:
                labels[ISOLATED_LABEL] = "no-labels"
            metadata["labels"] = labels

            warnings.append(Warning(
                resource_kind=resource.get("kind", "?"),
                resource_name=metadata.get("name", "?"),
                message="Resource has no cluster labels; marked as isolated.",
            ))
            label_change_count += 1

            stats.append(Stat(
                        resource_kind=resource.get("kind", "?"),
                        resource_name=resource.get("metadata", {}).get("name", "?"),
                        changed_labels=label_change_count
                    ))

    return resources, warnings, stats