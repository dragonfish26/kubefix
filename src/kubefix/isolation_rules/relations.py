"""Generic rule: resources that should be related to something but have no edge at all."""

# kinds that should always have at least one relation with another resource
RESOURCE_KINDS_WITH_RELATIONS = [
    "Secret",
    "ConfigMap",
    "ServiceAccount",
    "NetworkPolicy",
    "Service",
    "ValidatingWebhookConfiguration",
    "Issuer",
]


def no_relation_rule(resource, rid, ctx):
    """No relation (edge in the KubeDiagrams graph) with any other resource.
    This could indicate dead code and other issues."""
    if not ctx.parent_map.get(rid) and not ctx.child_map.get(rid):
        return [("no-relations", "Resource has no relations with other resources but should have at least one")]
    return []
