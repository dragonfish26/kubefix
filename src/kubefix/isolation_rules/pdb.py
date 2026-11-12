"""PodDisruptionBudget rule: a PDB whose selector matches no workload protects nothing."""

def pdb_rule(resource, rid, ctx):
    """A PodDisruptionBudget must have an edge to a workload its selector matches."""
    selector = (resource.get("spec") or {}).get("selector") or {}

    # KubeDiagrams only turns matchLabels into edges: without it, having no children proves nothing
    if not selector.get("matchLabels"):
        return []

    # a PDB's only edges go to the workloads its selector matches
    if not ctx.child_map.get(rid):
        return [("no-matching-workload", "PodDisruptionBudget selector matches no workload")]
    return []
