"""Driver code that runs the yaml scripts.

There are two kinds of scripts in kubefix.yaml:

  nodes:  scripts that create extra resources, like one PVC per
          volumeClaimTemplate on a StatefulSet
  edges:  scripts that emit edges between resources

The pipeline is:
    resources = load_manifests(...)   # from loader.py — read the yaml files
    create_new_nodes(resources, config)   # run all `nodes:` scripts
    edges = process_edges(resources, config)   # run all `edges:` scripts

create_new_nodes mutates `resources` in place (adds synthesised resources
and may also mutate originals as a side effect of how the yaml scripts
share dict references). process_edges does not mutate anything.
"""

import functools
import traceback

from .edges_context import EdgesContext
from .helpers import (
    get_name,
    get_namespace,
    get_node_config,
    get_type,
    query_path,
)


# Build the rid (resource id) for a given resource.

def compute_rid(resource, config):
    """The rid format is the same one the yaml scripts use when looking
    up edge targets, so it must match exactly:

        Namespaced resource    -> name/namespace/Kind/apiVersion
        Anything else          -> name/Kind/apiVersion

    """
    scope = get_node_config(resource, config).get("scope")
    name = get_name(resource)
    rtype = get_type(resource)
    if scope == "Namespaced":
        return f"{name}/{get_namespace(resource)}/{rtype}"
    return f"{name}/{rtype}"


# Map from plural resource names ('pods') to kinds ('Pod').
# Used by RBAC edges, which reference resources by plural name.

def _build_plural2kinds(config):
    out = {}
    for k, v in config.get("nodes", {}).items():
        if not isinstance(v, dict):
            continue  # this entry is just an alias pointing to another, skip
        kind = k.split("/")[0]
        plural = v.get("plural", kind.lower() + "s")
        out[plural] = kind
    return out


# Helper called from the Role/ClusterRole `nodes:` script.
#
# A Role can grant 'create' on a resource AND name specific instances in
# resourceNames. Those named instances usually don't exist in the manifest
# yet — the Role lets something else create them. We synthesise placeholder
# resources for them so the REFERENCE-UP edges from the Role can find
# something to point at.

def create_node_for_role_rules_resource_names(role, nodes, resources, plural2kinds):
    for ridx, rule in enumerate(query_path(role, "rules", [])):
        if not isinstance(rule, dict):
            continue
        resource_names = query_path(rule, "resourceNames")
        if resource_names is None:
            continue
        api_groups = query_path(rule, "apiGroups")
        if not api_groups or len(api_groups) != 1:
            print(f"[Error] Role:{get_name(role)}:rules[{ridx}] - "
                  f"apiGroups ({api_groups}) should contain only one value!")
            continue
        api_group = api_groups[0]
        api_version = "v1" if api_group == "" else f"{api_group}/v1"
        for res_plural in query_path(rule, "resources", []):
            if "/" in res_plural:
                continue
            kind = plural2kinds.get(res_plural)
            if kind is None:
                continue
            for rnidx, resource_name in enumerate(resource_names):
                if not isinstance(resource_name, str) or "*" in resource_name:
                    continue
                rid = f"{resource_name}/{get_namespace(role)}/{kind}/{api_version}"
                if rid in resources:
                    continue
                # Only synthesise if some rule actually grants `create`.
                for rule1 in query_path(role, "rules", []):
                    if (api_group in rule1.get("apiGroups", [])
                            and res_plural in rule1.get("resources", [])
                            and "create" in rule1.get("verbs", [])):
                        nodes.append({
                            "kind": kind,
                            "apiVersion": api_version,
                            "metadata": {
                                "name": resource_name,
                                "namespace": get_namespace(role),
                                "labels": query_path(role, "metadata.labels"),
                            },
                        })
                        print(f"[Warning] Role:{get_name(role)}:"
                              f"rules[{ridx}].resourceNames[{rnidx}] - "
                              f"Synthesised {kind}/{resource_name}!")
                        break


# Run every `nodes:` script. Adds new resources to `resources` in place.

def create_new_nodes(resources, config):
    plural2kinds = _build_plural2kinds(config)
    # The yaml script calls create_node_for_role_rules_resource_names(role, nodes)
    # — two args. We need to make `resources` and `plural2kinds` available to
    # it. functools.partial binds them, so the script still sees a two-arg call.
    role_helper = functools.partial(
        create_node_for_role_rules_resource_names,
        resources=resources,
        plural2kinds=plural2kinds,
    )

    def _run_for(resource):
        script = get_node_config(resource, config).get("nodes")
        if not script:
            return
        nodes = []
        try:
            exec(script, {
                "query_path": query_path,
                "get_name": get_name,
                "get_namespace": get_namespace,
                "get_type": get_type,
                "create_node_for_role_rules_resource_names": role_helper,
                "resources": resources,
                "resource": resource,
                "nodes": nodes,
            })
        except Exception as exc:
            print(f"[Error] nodes-script failed for {get_name(resource)}: {exc}")
            traceback.print_exc()
            return
        # A synthesised resource could itself have a `nodes:` script. Recurse
        # so we don't miss anything.
        for node in nodes:
            new_rid = compute_rid(node, config)
            if new_rid not in resources:
                resources[new_rid] = node
            _run_for(node)

    # Snapshot the keys: the loop body adds new entries to `resources`.
    for _, resource in list(resources.items()):
        _run_for(resource)


# Run every `edges:` script. Returns a flat list of (from, to, kind) tuples.

def process_edges(resources, config):
    plural2kinds = _build_plural2kinds(config)
    all_edges = []

    for rid, resource in resources.items():
        if not get_node_config(resource, config).get("show", True):
            continue
        script = get_node_config(resource, config).get("edges")
        if not script:
            continue

        ctx = EdgesContext(rid, resource, resources, config, plural2kinds)
        try:
            exec(script, {
                "query_path": query_path,
                "get_name": get_name,
                "get_namespace": get_namespace,
                "get_type": get_type,
                "edges": ctx,
                "resource": resource,
            })
        except Exception as exc:
            print(f"[Error] edges-script failed for {rid}: {exc}")
            traceback.print_exc()
            continue

        all_edges.extend(ctx.edges)

    return all_edges