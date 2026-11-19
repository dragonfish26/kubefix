"""Check if at least one workload is among the resources with the same component label, delete the label if no."""

from kubefix.common import Warning, Stat
from kubefix.label_utils import labels, label_stat, is_workload

COMPONENT_LABEL = "app.kubernetes.io/component"


def _comp_has_workload(cv, resources):
    """True if at least one workload of the manifest has the component label value cv."""
    return any(
        is_workload(r) and labels(r).get(COMPONENT_LABEL) == cv
        for r in resources
    )


def algo_check_comp_validity(resources):
    """Remove component labels whose value is not carried by any workload.

    A K8s component is meant to group a workload with the resources around it,
    so a component value with no workload in it is meaningless: the label is
    deleted from every resource that has that value.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings, stats).
    """
    warnings: list[Warning] = []
    stats: list[Stat] = []

    # 1. Find the set of distinct component label values.
    comp_values = {labels(r)[COMPONENT_LABEL] for r in resources if COMPONENT_LABEL in labels(r)}
    if not comp_values:
        return resources, warnings, stats  # no component label

    # 2. Keep the values that have no workload.
    invalid_values = {cv for cv in comp_values if not _comp_has_workload(cv, resources)}

    # 3. Delete the label from each resource that has an invalid value.
    for resource in resources:
        resource_labels = labels(resource)
        cv = resource_labels.get(COMPONENT_LABEL)
        if cv in invalid_values:
            del resource_labels[COMPONENT_LABEL]
            stats.append(label_stat(resource))

    for cv in sorted(invalid_values):
        warnings.append(Warning(
            resource_kind="Component",
            resource_name=cv,
            message=f"no workload has {COMPONENT_LABEL}={cv}, label removed",
        ))

    return resources, warnings, stats
