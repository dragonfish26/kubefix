"""Isolation rules used by algo_mark_isolated, one module per domain.

To add a rule: write `rule(resource, rid, ctx, ...) -> list[(code, message)]`
in a module here, then call it in _apply_isolation_rules in algo_mark_isolated.py.
If it needs precomputed data, give its module a prepare(ctx) function and pass
the result to the rule as an extra argument (see rbac.py).
"""
from kubefix.isolation_rules.base import ISOLATED_LABEL, IsolationContext, mark_isolated
from kubefix.isolation_rules import rbac
from kubefix.isolation_rules.relations import RESOURCE_KINDS_WITH_RELATIONS, no_relation_rule
from kubefix.isolation_rules.rbac import RBAC_KINDS, rbac_rule
from kubefix.isolation_rules.pdb import pdb_rule
from kubefix.isolation_rules.labels import no_labels_rule
