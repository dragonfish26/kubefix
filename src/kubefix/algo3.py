"""Algo 3: mark unlabeled resources with an isolated-resource label."""
from kubefix.common import Warning

ISOLATED_LABEL = "isolated-resource"


def algo3_mark_isolated(resources):
    """Add an 'isolated-resource' label to any resource without labels.

    To be run as a last resort for truly resources where truly no label was found. 

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings).
    """
    warnings = []
    for resource in resources:
        metadata = resource.setdefault("metadata", {})
        labels = metadata.get("labels")

        # treat "no labels key" and "empty labels dict" the same way
        if not labels:
            metadata["labels"] = {ISOLATED_LABEL: ""}
            warnings.append(Warning(
                resource_kind=resource.get("kind", "?"),
                resource_name=metadata.get("name", "?"),
                message="Resource has no labels; marked as isolated.",
            ))

    return resources, warnings