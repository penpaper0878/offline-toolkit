"""Role-based access control.

Permissions are ``resource:action`` strings. System roles map to fixed
permission sets; endpoints ask for a permission, never for a role, so new
roles (or per-organisation custom roles, see the backlog) need no endpoint
changes.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ENGINEER = "engineer"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class P(StrEnum):
    ORG_MANAGE = "org:manage"
    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    PROJECT_DELETE = "project:delete"
    DESIGN_READ = "design:read"
    DESIGN_WRITE = "design:write"
    DESIGN_DELETE = "design:delete"
    DESIGN_APPROVE = "design:approve"
    ESTIMATE_READ = "estimate:read"
    ESTIMATE_WRITE = "estimate:write"
    ESTIMATE_ISSUE = "estimate:issue"
    RATES_MANAGE = "rates:manage"  # schedules of rates and the organisation's rate analyses


_READ = {P.PROJECT_READ, P.DESIGN_READ, P.ESTIMATE_READ}

ROLE_PERMISSIONS: dict[Role, frozenset[P]] = {
    Role.OWNER: frozenset(P),
    Role.ADMIN: frozenset(set(P) - {P.ORG_MANAGE}),
    Role.ENGINEER: frozenset(_READ | {P.PROJECT_WRITE, P.DESIGN_WRITE, P.DESIGN_DELETE, P.ESTIMATE_WRITE, P.RATES_MANAGE}),
    Role.REVIEWER: frozenset(_READ | {P.DESIGN_APPROVE, P.ESTIMATE_ISSUE, P.AUDIT_READ}),
    Role.VIEWER: frozenset(_READ),
}

ROLE_LABELS = {
    Role.OWNER: "Owner",
    Role.ADMIN: "Administrator",
    Role.ENGINEER: "Design engineer",
    Role.REVIEWER: "Reviewer / checker",
    Role.VIEWER: "Viewer",
}


def permissions_of(role: str) -> frozenset[P]:
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        return frozenset()


def has_permission(role: str, permission: P) -> bool:
    return permission in permissions_of(role)
