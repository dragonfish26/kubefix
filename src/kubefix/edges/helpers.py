"""Small helpers used across edges, process, and loader.

These are also the helpers passed into the yaml scripts via exec's globals:
the scripts call query_path(), get_name(), get_namespace(), and get_type()
directly.
"""


def query_path(data, path, default=None):
    """Look up a dotted path like 'spec.template.metadata.name' in a dict."""
    paths = path.split(".")
    for p in paths[:-1]:
        if not isinstance(data, dict):
            return default
        data = data.get(p)
        if data is None:
            return default
    if not isinstance(data, dict):
        return default
    data = data.get(paths[-1])
    if data is None:
        return default
    return data


def get_name(resource):
    return query_path(resource, "metadata.name") \
        or query_path(resource, "metadata.generateName", "NO-NAME")


def get_namespace(resource, default_namespace="default"):
    return query_path(resource, "metadata.namespace", default_namespace)


def get_type(resource):
    return query_path(resource, "kind", "kind-NOT-SET") + "/" \
        + query_path(resource, "apiVersion", "apiVersion-NOT-SET")


def get_node_config_of_resource_type(resource_type, config):
    """Get the config block for a resource type like 'Deployment/apps/v1'.

    Some entries in config['nodes'] are just strings pointing to another
    entry (aliases for older api versions). We follow those until we
    reach a real config dict.
    """
    cfg = config.get("nodes", {}).get(resource_type)
    while isinstance(cfg, str):
        cfg = config.get("nodes", {}).get(cfg)
    return cfg or {}


def get_node_config(resource, config):
    return get_node_config_of_resource_type(get_type(resource), config)