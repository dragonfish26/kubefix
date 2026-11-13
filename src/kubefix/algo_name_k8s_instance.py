"""Name a K8s instance for a manifest that has none."""

from kubefix.common import Warning, Stat
from kubefix.label_utils import labels, set_label, label_stat, suggest_name

INSTANCE_LABEL = "app.kubernetes.io/instance"
APPLICATION_LABEL = "app.kubernetes.io/name"

DEFAULT_INSTANCE_NAME = "suggested_instance"


def algo_name_k8s_instance(resources):
    """If no resource of the manifest has a K8s instance label, give every resource the same one.

    The name is the longest common substring of the K8s application label values in the manifest, 
    or DEFAULT_INSTANCE_NAME (with a warning) if there are none or the common substring is too short.

    Args:
        resources: list of Kubernetes resources (dicts).

    Returns:
        A tuple (resources, warnings, stats).
    """
    warnings: list[Warning] = []
    stats: list[Stat] = []

    if not resources or any(INSTANCE_LABEL in labels(r) for r in resources):
        return resources, warnings, stats

    app_names = sorted({labels(r)[APPLICATION_LABEL]
                        for r in resources if APPLICATION_LABEL in labels(r)})
    value = suggest_name(app_names, DEFAULT_INSTANCE_NAME, warnings,
                         resource_kind="Manifest", resource_name=",".join(app_names) or "?")

    for resource in resources:
        set_label(resource, INSTANCE_LABEL, value)
        stats.append(label_stat(resource))

    return resources, warnings, stats
