"""Algo 4: assign cluster labels to unlabeled resources when the context is unambiguous."""
from kubefix.common import Warning

CLUSTER_LABELS_Algo4 = [
    "app.kubernetes.io/instance",
    "helm.sh/chart",
    "app.kubernetes.io/name",
]

def algo4_assign_unique_cluster_labels(resources):
    """Assign unambiguous cluster labels to resources that are missing them.

    Scans all resources to find cluster labels (instance, chart, name)
    that have exactly one distinct value across the whole manifest. Those are
    considered unambiguous.

    For each resource, we add these labels if they don't have them.

    Resources with no cluster labels at all receive all unambiguous labels.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings).
    """
    warnings = []

    # 1. For each cluster label, find the set of distinct values.
    unique_values = {}
    for label in CLUSTER_LABELS_Algo4:
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

    # 2. For each resource, add any unique label it doesn't already have
    for resource in resources:
        metadata = resource.setdefault("metadata", {})
        labels = metadata.get("labels") or {}

        to_assign = {
            label: value
            for label, value in unique_values.items()
            if label not in labels
        }

        if not to_assign:
            continue

        if not metadata.get("labels"):
            metadata["labels"] = {}
        metadata["labels"].update(to_assign)

        warnings.append(Warning(
            resource_kind=resource.get("kind", "?"),
            resource_name=metadata.get("name", "?"),
            message=f"Assigned unique cluster labels {to_assign}.",
        ))


    return resources, warnings