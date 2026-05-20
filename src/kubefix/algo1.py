from kubefix.common import Warning

LABEL_MAPPING: dict[str, str] = {
    "release": "app.kubernetes.io/instance",
    "chart":   "helm.sh/chart",
    "app":     "app.kubernetes.io/name",
}

RECOMMENDED_LABELS: set[str] = {
    "app.kubernetes.io/instance",
    "helm.sh/chart",
    "app.kubernetes.io/name",
    "app.kubernetes.io/component",
}


def algo1_normalize_labels(docs: list[dict]) -> tuple[list[dict], list[Warning]]:
    """Replace non-recommended labels with their recommended equivalents."""
    warnings: list[Warning] = []

    for resource in docs:
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

    return docs, warnings