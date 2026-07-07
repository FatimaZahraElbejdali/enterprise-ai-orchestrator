import re
import unicodedata
from dataclasses import dataclass

from orchestrator.tool_registry import get_capability_metadata


WRITE_TOKENS = {
    "approve",
    "cancel",
    "change",
    "create",
    "delete",
    "modify",
    "reject",
    "remove",
    "set",
    "toggle",
    "update",
    "write",
}

READ_TOKENS = {
    "answer",
    "check",
    "detail",
    "details",
    "diagnose",
    "diagnostic",
    "explain",
    "get",
    "health",
    "help",
    "list",
    "read",
    "search",
    "status",
    "summary",
    "troubleshoot",
    "usage",
    "view",
}

UNKNOWN_ACTIONS = {
    "",
    "none",
    "null",
    "unknown",
    "unsupported",
    "needs_clarification",
}


@dataclass(frozen=True)
class RoutePermission:
    agent: str
    target_system: str
    action: str
    risk_level: str
    action_category: str
    permission_category: str
    required_permissions: frozenset[str]
    blocked: bool = False
    unsupported: bool = False
    requires_approval: bool = False


def normalize_policy_value(value) -> str:
    if value is None:
        return ""

    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")


def _normalized_fields(classification: dict, *keys: str) -> list[str]:
    return [
        normalize_policy_value(classification.get(key))
        for key in keys
        if normalize_policy_value(classification.get(key))
    ]


def _contains_token(value: str, tokens: set[str]) -> bool:
    parts = set(value.split("_"))
    return bool(parts & tokens) or any(token in value for token in tokens)


def _has_read_signal(values: list[str]) -> bool:
    return any(_contains_token(value, READ_TOKENS) for value in values)


def _has_write_signal(values: list[str]) -> bool:
    return any(_contains_token(value, WRITE_TOKENS) for value in values)


def _is_unknown_signal(values: list[str]) -> bool:
    return not values or all(value in UNKNOWN_ACTIONS for value in values)


def _is_document_route(values: list[str]) -> bool:
    return any("document" in value or "invoice" in value or "order" in value for value in values)


def resolve_route_permission(classification: dict | None) -> RoutePermission:
    classification = classification or {}
    capability_name = classification.get("capability")
    capability_metadata = (
        get_capability_metadata(capability_name)
        if isinstance(capability_name, str)
        else None
    )
    agent = normalize_policy_value(
        classification.get("selected_agent") or classification.get("agent")
    ) or "general_agent"
    target_system = normalize_policy_value(classification.get("target_system"))
    risk_level = normalize_policy_value(
        classification.get("risk_level") or classification.get("risk")
    ) or "low"

    if capability_metadata:
        capability_domain = normalize_policy_value(
            capability_metadata.get("domain") or capability_metadata.get("system")
        )

        if capability_domain and target_system in {"", "general"}:
            target_system = capability_domain

        if agent == "general_agent" and capability_domain:
            agent = {
                "knowledge": "knowledge_agent",
                "odoo": "odoo_agent",
                "support": "support_agent",
                "server": "server_agent",
                "security": "security_agent",
                "development": "development_agent",
            }.get(capability_domain, agent)

        metadata_risk = normalize_policy_value(capability_metadata.get("risk_level"))

        if metadata_risk in {"medium", "high", "blocked"} and risk_level == "low":
            risk_level = metadata_risk

    action_values = _normalized_fields(
        classification,
        "action",
        "parsed_action",
        "business_action",
        "tool_used",
    )
    intent_values = _normalized_fields(classification, "intent")
    values = action_values + intent_values
    action = values[0] if values else ""
    unknown_without_category = (
        _is_unknown_signal(action_values)
        and not _has_read_signal(intent_values)
        and not _has_write_signal(intent_values)
    )

    security_blocked = (
        risk_level == "blocked"
        or (
            agent == "security_agent"
            and any(
                token in value
                for value in values
                for token in {"block", "blocked", "secret", "sensitive", "password", "ssh_key"}
            )
        )
    )

    if security_blocked:
        return RoutePermission(
            agent=agent,
            target_system=target_system,
            action=action,
            risk_level=risk_level,
            action_category="blocked",
            permission_category="security_blocked",
            required_permissions=frozenset(),
            blocked=True,
        )

    if agent == "server_agent" or target_system == "server":
        if unknown_without_category:
            return _unsupported(agent, target_system, action, risk_level)

        return RoutePermission(
            agent=agent,
            target_system=target_system,
            action=action,
            risk_level=risk_level,
            action_category="server_diagnostic",
            permission_category="server_diagnostics",
            required_permissions=frozenset({"server_diagnostics"}),
        )

    if agent == "support_agent" or target_system == "support":
        if unknown_without_category:
            return _unsupported(agent, target_system, action, risk_level)

        return RoutePermission(
            agent=agent,
            target_system=target_system,
            action=action,
            risk_level=risk_level,
            action_category="support",
            permission_category="support_access",
            required_permissions=frozenset({"support_diagnostics", "support_questions"}),
        )

    if agent == "odoo_agent" or target_system == "odoo" or any(
        value.startswith("odoo") for value in values
    ):
        if unknown_without_category:
            return _unsupported(agent, target_system or "odoo", action, risk_level)

        if capability_metadata:
            permission_category = capability_metadata.get("permission_category")
            io_mode = str(capability_metadata.get("io_mode") or "")
            is_capability_write = (
                permission_category == "odoo_write"
                or io_mode.startswith("write")
                or capability_metadata.get("requires_approval") is True
            )

            if is_capability_write:
                return RoutePermission(
                    agent=agent,
                    target_system=target_system or "odoo",
                    action=action or str(capability_name),
                    risk_level=risk_level,
                    action_category="write",
                    permission_category="odoo_write",
                    required_permissions=frozenset({"request_odoo_write"}),
                    requires_approval=True,
                )

            if permission_category == "odoo_document_read":
                return RoutePermission(
                    agent=agent,
                    target_system=target_system or "odoo",
                    action=action or str(capability_name),
                    risk_level=risk_level,
                    action_category="read",
                    permission_category="odoo_document_read",
                    required_permissions=frozenset({"view_odoo_documents", "view_limited_odoo_info"}),
                )

            if permission_category == "odoo_read":
                return RoutePermission(
                    agent=agent,
                    target_system=target_system or "odoo",
                    action=action or str(capability_name),
                    risk_level=risk_level,
                    action_category="read",
                    permission_category="odoo_read",
                    required_permissions=frozenset({"view_odoo_documents", "view_odoo_products", "view_limited_odoo_info"}),
                )

            return RoutePermission(
                agent=agent,
                target_system=target_system or "odoo",
                action=action or str(capability_name),
                risk_level=risk_level,
                action_category="read",
                permission_category="odoo_product_read",
                required_permissions=frozenset({"view_odoo_products", "view_limited_odoo_info"}),
            )

        is_write = (
            classification.get("requires_approval") is True
            or classification.get("approval_required") is True
            or _has_write_signal(values)
            or (risk_level in {"medium", "high"} and not _has_read_signal(values))
        )

        if is_write:
            return RoutePermission(
                agent=agent,
                target_system=target_system or "odoo",
                action=action,
                risk_level=risk_level,
                action_category="write",
                permission_category="odoo_write",
                required_permissions=frozenset({"request_odoo_write"}),
                requires_approval=True,
            )

        if _is_document_route(values):
            return RoutePermission(
                agent=agent,
                target_system=target_system or "odoo",
                action=action,
                risk_level=risk_level,
                action_category="read",
                permission_category="odoo_document_read",
                required_permissions=frozenset({"view_odoo_documents", "view_limited_odoo_info"}),
            )

        return RoutePermission(
            agent=agent,
            target_system=target_system or "odoo",
            action=action,
            risk_level=risk_level,
            action_category="read",
            permission_category="odoo_product_read",
            required_permissions=frozenset({"view_odoo_products", "view_limited_odoo_info"}),
        )

    if unknown_without_category and agent not in {"general_agent", "knowledge_agent", "development_agent"}:
        return _unsupported(agent, target_system, action, risk_level)

    return RoutePermission(
        agent=agent,
        target_system=target_system or "general",
        action=action,
        risk_level=risk_level,
        action_category="general",
        permission_category="chat_access",
        required_permissions=frozenset({"chat_access"}),
    )


def _unsupported(agent: str, target_system: str, action: str, risk_level: str) -> RoutePermission:
    return RoutePermission(
        agent=agent,
        target_system=target_system,
        action=action,
        risk_level=risk_level,
        action_category="unsupported",
        permission_category="unsupported",
        required_permissions=frozenset(),
        unsupported=True,
    )
