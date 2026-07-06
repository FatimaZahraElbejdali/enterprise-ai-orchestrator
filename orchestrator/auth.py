import hashlib
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Header, HTTPException, status

from orchestrator.permission_policy import resolve_route_permission


AUTH_REQUIRED_MESSAGE = "Authentification requise."
INVALID_SESSION_MESSAGE = "Session invalide ou expirée."
INVALID_CREDENTIALS_MESSAGE = "Identifiants incorrects."
ACCESS_DENIED_MESSAGE = "Accès refusé : votre rôle ne permet pas d’effectuer cette action."

DEMO_PASSWORD_SALT = "enterprise-ai-orchestrator-demo"
SESSION_TTL_HOURS = 8

ROLE_LABELS = {
    "admin": "Administrateur",
    "odoo_manager": "Responsable Odoo",
    "it_manager": "Responsable IT",
    "support_agent": "Agent Support",
    "employee": "Employé",
    "readonly_viewer": "Lecture seule",
}

ROLE_PERMISSIONS = {
    "admin": {"all"},
    "odoo_manager": {
        "chat_access",
        "view_odoo_products",
        "view_odoo_documents",
        "request_odoo_write",
        "approve_odoo_actions",
        "view_approvals",
    },
    "it_manager": {
        "chat_access",
        "server_diagnostics",
        "view_audit_logs",
        "approve_technical_actions",
    },
    "support_agent": {
        "chat_access",
        "support_diagnostics",
        "view_limited_logs",
    },
    "employee": {
        "chat_access",
        "support_questions",
        "view_limited_odoo_info",
    },
    "readonly_viewer": {
        "chat_access",
        "view_limited_odoo_info",
    },
}

_audit_user_context: ContextVar[dict | None] = ContextVar(
    "audit_user_context",
    default=None,
)


@dataclass(frozen=True)
class DemoUser:
    email: str
    role: str
    password_hash: str


def _hash_password(password: str) -> str:
    return hashlib.sha256(
        f"{DEMO_PASSWORD_SALT}:{password}".encode("utf-8")
    ).hexdigest()


# Demo-only local user store. Do not use these credentials or this storage model
# in production; migrate to PostgreSQL, SSO, or an enterprise identity provider.
DEMO_USERS = {
    "admin@company.local": DemoUser(
        email="admin@company.local",
        role="admin",
        password_hash=_hash_password("admin123"),
    ),
    "odoo.manager@company.local": DemoUser(
        email="odoo.manager@company.local",
        role="odoo_manager",
        password_hash=_hash_password("manager123"),
    ),
    "it.manager@company.local": DemoUser(
        email="it.manager@company.local",
        role="it_manager",
        password_hash=_hash_password("it123"),
    ),
    "support@company.local": DemoUser(
        email="support@company.local",
        role="support_agent",
        password_hash=_hash_password("support123"),
    ),
    "employee@company.local": DemoUser(
        email="employee@company.local",
        role="employee",
        password_hash=_hash_password("employee123"),
    ),
    "viewer@company.local": DemoUser(
        email="viewer@company.local",
        role="readonly_viewer",
        password_hash=_hash_password("viewer123"),
    ),
}

_sessions: dict[str, dict] = {}


def _expires_at():
    return datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)


def _serialize_user(user: DemoUser) -> dict:
    permissions = sorted(ROLE_PERMISSIONS.get(user.role, set()))

    return {
        "email": user.email,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "permissions": permissions,
    }


def authenticate_demo_user(email: str, password: str) -> dict | None:
    normalized_email = (email or "").strip().lower()
    user = DEMO_USERS.get(normalized_email)

    if not user:
        return None

    if not secrets.compare_digest(user.password_hash, _hash_password(password or "")):
        return None

    token = secrets.token_urlsafe(32)
    serialized_user = _serialize_user(user)
    _sessions[token] = {
        "user": serialized_user,
        "expires_at": _expires_at(),
    }

    return {
        "access_token": token,
        "user": serialized_user,
    }


def _auth_error(message: str, status_code: int):
    raise HTTPException(
        status_code=status_code,
        detail=message,
    )


def get_current_user(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> dict:
    if not authorization:
        _auth_error(AUTH_REQUIRED_MESSAGE, status.HTTP_401_UNAUTHORIZED)

    scheme, _, token = authorization.partition(" ")

    if scheme.lower() != "bearer" or not token:
        _auth_error(INVALID_SESSION_MESSAGE, status.HTTP_401_UNAUTHORIZED)

    session = _sessions.get(token)

    if not session:
        _auth_error(INVALID_SESSION_MESSAGE, status.HTTP_401_UNAUTHORIZED)

    expires_at = session.get("expires_at")

    if not isinstance(expires_at, datetime) or expires_at <= datetime.now(timezone.utc):
        _sessions.pop(token, None)
        _auth_error(INVALID_SESSION_MESSAGE, status.HTTP_401_UNAUTHORIZED)

    return dict(session["user"])


def get_audit_user_context() -> dict | None:
    return _audit_user_context.get()


def set_audit_user_context(
    user: dict | None,
    permission_decision: str | None = None,
):
    context = None

    if user:
        context = {
            "user_email": user.get("email"),
            "user_role": user.get("role"),
        }

        if permission_decision:
            context["permission_decision"] = permission_decision

    return _audit_user_context.set(context)


def reset_audit_user_context(token):
    _audit_user_context.reset(token)


def role_permissions(user: dict) -> set[str]:
    role = user.get("role")
    return set(user.get("permissions") or ROLE_PERMISSIONS.get(role, set()))


def has_permission(user: dict, permission: str) -> bool:
    permissions = role_permissions(user)
    return "all" in permissions or permission in permissions


def has_any_permission(user: dict, permissions: set[str]) -> bool:
    user_permissions = role_permissions(user)
    return "all" in user_permissions or bool(user_permissions & permissions)


def require_permission(user: dict, permission: str):
    if not has_permission(user, permission):
        _auth_error(ACCESS_DENIED_MESSAGE, status.HTTP_403_FORBIDDEN)


def require_any_permission(user: dict, permissions: set[str]):
    if not has_any_permission(user, permissions):
        _auth_error(ACCESS_DENIED_MESSAGE, status.HTTP_403_FORBIDDEN)


def required_chat_permissions(message: str, classification: dict) -> set[str]:
    del message
    return set(resolve_route_permission(classification).required_permissions)


def check_chat_permission(user: dict, message: str, classification: dict) -> bool:
    required = required_chat_permissions(message, classification)
    route_permission = resolve_route_permission(classification)

    if route_permission.blocked:
        return True

    if route_permission.unsupported:
        return False

    return has_any_permission(user, required)


def access_denied_payload(
    classification: dict | None = None,
    user: dict | None = None,
) -> dict:
    classification = classification or {}

    return {
        "intent": classification.get("intent", "access_denied"),
        "agent": classification.get("selected_agent") or classification.get("agent", "security_agent"),
        "selected_agent": classification.get("selected_agent") or classification.get("agent", "security_agent"),
        "risk": classification.get("risk", classification.get("risk_level", "low")),
        "risk_level": classification.get("risk_level", classification.get("risk", "low")),
        "requires_approval": False,
        "approval_required": False,
        "approval_status": "not_required",
        "status": "access_denied",
        "message": ACCESS_DENIED_MESSAGE,
        "tool_used": None,
        "result": {
            "allowed": False,
            "message": ACCESS_DENIED_MESSAGE,
        },
        "agent_result": {
            "agent": "security_agent",
            "tool_used": None,
            "result": {
                "allowed": False,
                "message": ACCESS_DENIED_MESSAGE,
            },
        },
        "permission_decision": "denied",
        "user": {
            "email": user.get("email"),
            "role": user.get("role"),
            "role_label": user.get("role_label"),
        }
        if user
        else None,
    }


def unsupported_action_payload(
    classification: dict | None = None,
    user: dict | None = None,
) -> dict:
    classification = classification or {}
    agent = classification.get("selected_agent") or classification.get("agent", "general_agent")

    return {
        "intent": classification.get("intent", "unsupported"),
        "agent": agent,
        "selected_agent": agent,
        "risk": classification.get("risk", classification.get("risk_level", "low")),
        "risk_level": classification.get("risk_level", classification.get("risk", "low")),
        "requires_approval": False,
        "approval_required": False,
        "approval_status": "not_required",
        "status": "unsupported",
        "message": "Action non prise en charge. Veuillez préciser une demande métier autorisée.",
        "tool_used": None,
        "result": {
            "allowed": False,
            "message": "Action non prise en charge. Aucun outil n’a été exécuté.",
        },
        "agent_result": {
            "agent": agent,
            "tool_used": None,
            "result": {
                "allowed": False,
                "message": "Action non prise en charge. Aucun outil n’a été exécuté.",
            },
        },
        "permission_decision": "denied",
        "user": {
            "email": user.get("email"),
            "role": user.get("role"),
            "role_label": user.get("role_label"),
        }
        if user
        else None,
    }
