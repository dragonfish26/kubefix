from kubefix.common import Warning

LABEL_MAPPING: dict[str, str] = {
    "release": "app.kubernetes.io/instance",
    "chart":   "helm.sh/chart",
    "app":     "app.kubernetes.io/name",
    "component": "app.kubernetes.io/component",
    "heritage": "app.kubernetes.io/managed-by",
    "version": "app.kubernetes.io/version",
}


def algo1_normalize_labels(resources):
    """Replace non-recommended labels with their recommended equivalents.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings) where resources is the modified
        list and warnings is a list of Warning objects for conflicts.
    """
    warnings: list[Warning] = []

    for resource in resources:
        labels = resource.get("metadata", {}).get("labels")
        if not labels:
            continue

        for old_key, value in list(labels.items()):
            if old_key not in LABEL_MAPPING:
                continue  # already recommended, or unknown, so leave it alone

            new_key = LABEL_MAPPING[old_key]

            if new_key in labels:
                # recommended label already present
                if labels[new_key] == value:
                    # same value, just drop the duplicate
                    del labels[old_key]
                else:
                    # different values : keep recommended, drop non-recommended, warn
                    warnings.append(Warning(
                        resource_kind=resource.get("kind", "?"),
                        resource_name=resource.get("metadata", {}).get("name", "?"),
                        message=(
                            f"Conflict: '{old_key}={value}' vs "
                            f"'{new_key}={labels[new_key]}'. Kept recommended."
                        ),
                    ))
                    del labels[old_key]
            else:
                # recommended label not present, simple rename
                labels[new_key] = value
                del labels[old_key]

    return resources, warnings