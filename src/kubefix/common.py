from dataclasses import dataclass

@dataclass
class Warning:
    resource_kind: str
    resource_name: str
    message: str

# Labels that define clusters in KubeDiagrams, in order of significance.
CLUSTER_LABELS = [
    "app.kubernetes.io/instance",
    "helm.sh/chart",
    "app.kubernetes.io/name",
    "app.kubernetes.io/component",
]