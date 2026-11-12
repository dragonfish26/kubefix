"""RBAC rule: bindings missing their role or subject, roles nobody binds,
and service accounts no workload uses."""
from dataclasses import dataclass

from kubefix.isolation_rules.base import BINDINGS, ROLES

RBAC_KINDS = BINDINGS + ROLES + ["ServiceAccount"]

K8S_AGGREGATE_LABELS = [
    "rbac.authorization.k8s.io/aggregate-to-admin",
    "rbac.authorization.k8s.io/aggregate-to-edit",
    "rbac.authorization.k8s.io/aggregate-to-view",
    "rbac.authorization.k8s.io/aggregate-to-cluster-reader",
]


def k8s_aggregate_labels(config):
    """Cluster labels that indicate k8s specific aggregate labels.
    Falls back to K8S_AGGREGATE_LABELS if the config defines no rbac labels."""
    keys = [
        c["label"] for c in config.get("clusters", [])
        if (c.get("label") or "").startswith("rbac.authorization.k8s.io/")
    ]
    return keys if keys else list(K8S_AGGREGATE_LABELS)


def aggregated_crole_rids(edges, resources_by_rid):
    """Rids of ClusterRoles aggregated (whose rules are merged) into another ClusterRole
    (through that role's aggregationRule label selector, drawn as a SELECTOR edge).
    They don't need their own binding: they are used through the role that includes them."""
    return {
        to for frm, to, kind in edges
        if kind == "SELECTOR" and resources_by_rid[frm]["kind"] == "ClusterRole"
    }


@dataclass
class RbacData:
    """Data only the rbac rule needs, computed once by prepare().

    Attributes:
        aggregated_crole_rids: ClusterRole rids aggregated into another ClusterRole.
        k8s_aggregate_labels: labels marking a role as aggregated into a built-in role.
    """
    aggregated_crole_rids: set
    k8s_aggregate_labels: list


def prepare(ctx):
    """Compute the rbac rule's data from the shared context. Call once before the loop."""
    return RbacData(
        aggregated_crole_rids=aggregated_crole_rids(ctx.edges, ctx.resources_by_rid),
        k8s_aggregate_labels=k8s_aggregate_labels(ctx.config),
    )


def rbac_rule(resource, rid, ctx, rbac_data):
    """Dispatch to the check for the resource's RBAC kind."""
    kind = resource.get("kind")
    if kind in BINDINGS:
        return _check_binding(resource, rid, ctx)
    if kind in ROLES:
        return _check_role(resource, rid, ctx, rbac_data)
    if kind == "ServiceAccount":
        return _check_service_account(resource, rid, ctx)
    return []


def _check_binding(resource, rid, ctx):
    """A binding must have an edge to its role and to its ServiceAccount subjects."""
    reasons = []
    namespace = (resource.get("metadata") or {}).get("namespace") or "default"
    children = ctx.child_map.get(rid, [])

    # role check, skipped if the role referenced by this binding is provided by the cluster
    role_ref = resource.get("roleRef") or {}
    if role_ref.get("kind") == "Role":
        role_rid = f"{role_ref.get('name')}/{namespace}/Role/rbac.authorization.k8s.io/v1"
    else:
        role_rid = f"{role_ref.get('name')}/ClusterRole/rbac.authorization.k8s.io/v1"

    if role_rid not in ctx.cluster_resources:
        if not any(ctx.resources_by_rid[c]["kind"] in ROLES for c in children):
            reasons.append(("no-role", "Resource is a binding but has no edge to a role"))

    # subject check, users and groups are external identities so only service accounts can have an edge
    subjects = resource.get("subjects") or []
    if not subjects:
        reasons.append(("no-subject", "Resource is a binding but has no subjects"))
    else:
        for subject in subjects:
            if subject.get("kind") != "ServiceAccount":
                continue
            sa_namespace = subject.get("namespace") or namespace
            sa_rid = f"{subject.get('name')}/{sa_namespace}/ServiceAccount/v1"
            if sa_rid not in ctx.cluster_resources and sa_rid not in children:
                reasons.append(("no-subject", f"Resource is a binding but has no edge to its subject ServiceAccount '{subject.get('name')}'"))
                break

    return reasons


def _check_role(resource, rid, ctx, rbac_data):
    """A role must be bound by a binding, unless it is aggregated into another role."""
    labels = (resource.get("metadata") or {}).get("labels") or {}

    # aggregated into a built-in K8s role = has specific labels
    if any(key in rbac_data.k8s_aggregate_labels for key in labels):
        return []

    # aggregated into another ClusterRole: its rules are granted through that role
    if rid in rbac_data.aggregated_crole_rids:
        return []

    parents = [ctx.resources_by_rid[p]["kind"] for p in ctx.parent_map.get(rid, [])]
    if not any(k in BINDINGS for k in parents):
        return [("no-binding", "Resource is a role but has no edge from a binding")]
    return []


def _check_service_account(resource, rid, ctx):
    """A service account must be used by a workload."""
    # skip 'default', used implicitly by pods without serviceAccountName
    if (resource.get("metadata") or {}).get("name") == "default":
        return []

    # no relations at all is already marked by no_relation_rule
    parents = [ctx.resources_by_rid[p]["kind"] for p in ctx.parent_map.get(rid, [])]

    # no parent other than bindings = no workloads
    if parents and all(k in BINDINGS for k in parents):
        return [("no-workload", "Resource is a service account but has no edge from a workload")]
    return []
