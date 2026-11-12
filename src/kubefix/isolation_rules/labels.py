"""Label rule: resources with no cluster label, so no cluster can group them."""
from kubefix.common import CLUSTER_LABELS


def no_labels_rule(resource, rid, ctx):
    """No cluster label (app.kubernetes.io/instance, app, ...) on the resource.
    Applies to every kind; registered last so '-no-labels' comes after the relation reasons."""
    labels = (resource.get("metadata") or {}).get("labels") or {}
    if not any(key in CLUSTER_LABELS for key in labels):
        return [("no-labels", "Resource has no cluster labels")]
    return []
