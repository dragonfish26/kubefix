"""Mark unlabeled resources with an isolated-resource label."""
from kubefix.common import Warning, Stat

from kubefix.edges import compute_rid, create_new_nodes, process_edges

from kubefix.algo_label_intersection import _build_parent_and_child_maps
from kubefix.label_utils import load_config

from kubefix.isolation_rules import (
    IsolationContext,
    mark_isolated,
    rbac,
    RESOURCE_KINDS_WITH_RELATIONS,
    no_relation_rule,
    RBAC_KINDS,
    rbac_rule,
    pdb_rule,
    no_labels_rule,
)


def _apply_isolation_rules(resources, ctx, rbac_data, warnings, stats):
    """Run every rule that applies to each resource and mark it isolated
    with the reasons found: one label, one warning and one stat per resource.

    A kind can be checked by several rules, hence separate ifs and not elif.
    The order of the rules sets the order of the codes in the label value,
    for example : 'no-relations-no-labels'.
    """
    for resource in resources:
        kind = resource.get("kind")
        rid = compute_rid(resource, ctx.config)
        reasons = []

        if kind in RESOURCE_KINDS_WITH_RELATIONS:
            reasons += no_relation_rule(resource, rid, ctx)
        if kind in RBAC_KINDS:
            reasons += rbac_rule(resource, rid, ctx, rbac_data)
        if kind == "PodDisruptionBudget":
            reasons += pdb_rule(resource, rid, ctx)
        # every kind, last so '-no-labels' comes after the relation reasons
        reasons += no_labels_rule(resource, rid, ctx)

        if reasons:
            mark_isolated(resource, reasons, warnings, stats)


def algo_mark_isolated(resources):
    """Add an 'isolated-resource' label to resources that look isolated. The label
    value gives the reason:

    - 'no-relations': no relations with other resources, but should have at least one
    - 'no-role' / 'no-subject': a binding missing its role and/or a subject,
      concatenated when both are missing, for example : 'no-role-no-subject'
    - 'no-binding': a role that isn't bound by any binding, nor aggregated into another role
    - 'no-workload': a service account that isn't used by any workload
    - 'no-matching-workload': a PodDisruptionBudget whose selector matches no workload
    - 'no-labels': no cluster labels

    A resource with no cluster labels that is already marked gets '-no-labels'
    added to its value, for example : 'no-relations-no-labels'.

    The rules live in the isolation_rules package and are called in
    _apply_isolation_rules.

    To be run as a last resort, after the other algos have assigned labels.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings, stats).
    """
    warnings: list[Warning] = []
    stats: list[Stat] = []

    config = load_config()

    # Build edges, parent map and child map to check relation isolation
    resources_by_rid = {compute_rid(r, config): r for r in resources}

    create_new_nodes(resources_by_rid, config)
    edges = process_edges(resources_by_rid, config)
    # INVISIBLE edges aren't drawn, so they don't count as relations
    visible_edges = [e for e in edges if e[2] != "INVISIBLE"]
    parent_map, child_map = _build_parent_and_child_maps(visible_edges)

    ctx = IsolationContext(
        config=config,
        resources_by_rid=resources_by_rid,
        edges=visible_edges,
        parent_map=parent_map,
        child_map=child_map,
        cluster_resources=config.get("cluster-resources", []),
    )
    # data specific to a rule, prepared once by its module
    rbac_data = rbac.prepare(ctx)

    _apply_isolation_rules(resources, ctx, rbac_data, warnings, stats)

    return resources, warnings, stats
