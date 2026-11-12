"""Shared pieces of the isolation rules: the context passed to every rule,
the kind groups they use, and the function that marks a resource as isolated.

A rule is a function `rule(resource, rid, ctx, ...) -> list[(code, message)]`.
It returns one (label code, warning message) pair per problem found,
or an empty list if the resource isn't isolated. A rule that needs its own
precomputed data takes it as an extra argument.
"""
from dataclasses import dataclass, field

from kubefix.common import Warning, Stat

ISOLATED_LABEL = "isolated-resource"

BINDINGS = [
    "ClusterRoleBinding",
    "RoleBinding",
]

ROLES = [
    "ClusterRole",
    "Role",
]

@dataclass
class IsolationContext:
    """Generic graph data shared by all rules, computed once before the rules run.
    Data specific to one rule is prepared by that rule's module (e.g. rbac.prepare).

    Attributes:
        config: edges configuration (kubefix.yaml).
        resources_by_rid: dict mapping a rid to its resource.
        edges: visible edges, as (from_rid, to_rid, edge_kind) tuples.
        parent_map: dict mapping a rid to the rids that point at it.
        child_map: dict mapping a rid to the rids it points to.
        cluster_resources: rids provided by the Kubernetes cluster itself.
    """
    config: dict
    resources_by_rid: dict
    edges: list
    parent_map: dict
    child_map: dict
    cluster_resources: list = field(default_factory=list)


def mark_isolated(resource, reasons, warnings, stats):
    """Add the reasons to the resource's 'isolated-resource' label and record
    a warning and a stat.

    Codes are joined with '-' and appended to an existing value, for example :
    'no-role-no-subject', or 'no-relations-no-labels'.

    Args:
        resource: the Kubernetes resource (dict), modified in place.
        reasons: non-empty list of (code, message).
        warnings: list of Warning, appended to in place.
        stats: list of Stat, appended to in place.
    """
    metadata = resource.setdefault("metadata", {})
    labels = metadata.get("labels") or {}

    code = "-".join(c for c, _ in reasons)
    existing = labels.get(ISOLATED_LABEL)
    labels[ISOLATED_LABEL] = f"{existing}-{code}" if existing else code
    metadata["labels"] = labels

    kind = resource.get("kind", "?")
    name = metadata.get("name", "?")
    warnings.append(Warning(
        resource_kind=kind,
        resource_name=name,
        message=f"{'; '.join(m for _, m in reasons)}; marked as isolated.",
    ))
    stats.append(Stat(resource_kind=kind, resource_name=name, changed_labels=1))
