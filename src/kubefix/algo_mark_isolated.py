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
    "Service",
    "ValidatingWebhookConfiguration",
    "Issuer",
]

BINDINGS = [
    "ClusterRoleBinding",
    "RoleBinding",
]

ROLES = [
    "ClusterRole",
    "Role",
]

K8S_AGGREGATE_LABELS = [
    "rbac.authorization.k8s.io/aggregate-to-admin",
    "rbac.authorization.k8s.io/aggregate-to-edit",
    "rbac.authorization.k8s.io/aggregate-to-view",
]


def _isolated_no_relation(resources, parent_map, child_map, config, warnings, stats):
    """Add an 'isolated-resource' label to resources who doesn't have any relations 
    (edges calculated by Kubediagrams graph) with other resources, but should have at least one relation.
    This could indicate deadcode and other issues.

    Args:
        resources: list of Kubernetes resources (dicts).
        parent_map: dict mapping a rid to the rids that point at it.
        child_map: dict mapping a rid to the rids it points to.
        config: edges configuration, used to compute rids and find built-in roles.
        warnings: list of Warning, appended to in place.
        stats: list of Stat, appended to in place.

    """

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

def _isolated_missing_relation(resources, parent_map, child_map, config, resources_by_rid, warnings, stats):
    """Add an 'isolated-resource' label to bindings that has a missing subject and
    roles that have a missing bindings.

    Args:
        resources: list of Kubernetes resources (dicts).
        parent_map: dict mapping a rid to the rids that point at it.
        child_map: dict mapping a rid to the rids it points to.
        config: edges configuration, used to compute rids and find built-in roles.
        resources_by_rid: dict mapping a rid to its resource.
        warnings: list of Warning, appended to in place.
        stats: list of Stat, appended to in place.
    """

    for resource in resources:
        kind = resource.get("kind")
        if kind not in BINDINGS and kind not in ROLES:
            continue

        rid = compute_rid(resource, config)
        metadata = resource.setdefault("metadata", {})
        labels = metadata.get("labels") or {}
        reason = None

        if kind in BINDINGS:
            # skip if resource referenced by this binding is a K8s specific thing
            role_ref = resource.get("roleRef") or {}
            if role_ref.get("kind") == "Role":
                namespace = metadata.get("namespace") or "default"
                role_rid = f"{role_ref.get('name')}/{namespace}/Role/rbac.authorization.k8s.io/v1"
            else:
                role_rid = f"{role_ref.get('name')}/ClusterRole/rbac.authorization.k8s.io/v1"

            if role_rid in config.get("cluster-resources", []):
                continue

            children = [resources_by_rid[c]["kind"] for c in child_map.get(rid, [])]
            if not any(k in ROLES for k in children):
                reason = "Resource is a binding but has no edge to a role"

        else:  # roles
            # skip roles aggregated by K8s = has specific labels
            if any(key in K8S_AGGREGATE_LABELS for key in labels):
                continue

            parents = [resources_by_rid[p]["kind"] for p in parent_map.get(rid, [])]
            if not any(k in BINDINGS for k in parents):
                reason = "Resource is a role but has no edge from a binding"

        if reason is None:
            continue

        if labels.get(ISOLATED_LABEL) != "no-relations":  # keep the stronger signal
            labels[ISOLATED_LABEL] = "missing-relations"
        metadata["labels"] = labels

        warnings.append(Warning(
            resource_kind=kind,
            resource_name=metadata.get("name", "?"),
            message=f"{reason}; marked as isolated.",
        ))
        stats.append(Stat(resource_kind=kind, resource_name=metadata.get("name", "?"), changed_labels=1))


def algo_mark_isolated(resources):
    """Add an 'isolated-resource' label to resources that look isolated. The label
    value gives the reason:

    - 'no-relations': no relations with other resources, but should have at least one
    - 'missing-relations': a binding or role missing a relation its kind requires
    - 'no-labels': no cluster labels

    A resource with no cluster labels that is already marked gets '-no-labels'
    added to its value, for example : 'no-relations-no-labels'.

    To be run as a last resort, after the other algos have assigned labels.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings, stats).
    """
    warnings: list[Warning] = []
    stats: list[Stat] = []

    config_path = _DEFAULT_CONFIG_PATH
    config = _load_config(config_path)

    # Build edges, parent map and child map to check relation isolation
    resources_by_rid = {compute_rid(r, config): r for r in resources}

    create_new_nodes(resources_by_rid, config)
    edges = process_edges(resources_by_rid, config)
    # INVISIBLE edges aren't drawn, so they don't count as relations
    visible_edges = [e for e in edges if e[2] != "INVISIBLE"]
    parent_map, child_map = _build_parent_and_child_maps(visible_edges)

    # 1. check relation isolation
    _isolated_no_relation(resources, parent_map, child_map, config, warnings, stats)

    # 2. check missing relation isolation
    _isolated_missing_relation(resources, parent_map, child_map, config, resources_by_rid, warnings, stats)

    # 3. check label isolation
    for resource in resources:
        label_change_count = 0 #counter for stat

        metadata = resource.setdefault("metadata", {})
        labels = metadata.get("labels") or {}

        # check if there are no labels that are cluster labels for the resource
        if not any(key in CLUSTER_LABELS for key in labels): 
            existing = labels.get(ISOLATED_LABEL)
            labels[ISOLATED_LABEL] = f"{existing}-no-labels" if existing else "no-labels"
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