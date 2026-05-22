"""Algo 4: assign cluster labels to unlabeled resources when the context is unambiguous."""
from kubefix.common import Warning

# Labels that define clusters in KubeDiagrams, in order of significance.
CLUSTER_LABELS = [
    "app.kubernetes.io/instance",
    "helm.sh/chart",
    "app.kubernetes.io/name",
    "app.kubernetes.io/component",
]


def algo4_assign_unique_cluster_labels(resources):
    """Give unlabeled resources the cluster labels of the only candidate cluster.

    For each cluster-defining label, if exactly one distinct value exists
    across all resources, then any resource missing that label receives it.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings).
    """
    warnings = []

    # 1. For each cluster label, find the set of distinct values.
    unique_values = {}
    for label in CLUSTER_LABELS:
        values = set()
        for resource in resources:
            labels = resource.get("metadata", {}).get("labels") or {}
            if label in labels:
                values.add(labels[label])
        # keep only labels that have exactly one distinct value across the app.
        if len(values) == 1:
            unique_values[label] = next(iter(values))

    if not unique_values:
        return resources, warnings  # no unique clusters

    # 2. Assign those unambiguous labels to resources that lack them.
    for resource in resources:
        metadata = resource.setdefault("metadata", {})
        labels = metadata.get("labels")

        # skip resources with labels.
        if labels:
            continue 

        # assign all unambiguous cluster labels.
        metadata["labels"] = dict(unique_values)
        warnings.append(Warning(
            resource_kind=resource.get("kind", "?"),
            resource_name=metadata.get("name", "?"),
            message=f"Assigned unique cluster labels {unique_values} (no labels found).",
        ))

    return resources, warnings