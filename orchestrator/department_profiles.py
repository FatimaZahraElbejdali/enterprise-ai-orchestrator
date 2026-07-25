from dataclasses import dataclass

from orchestrator.permission_policy import RoutePermission


CANONICAL_DEPARTMENTS = {
    "securite",
    "nettoyage",
    "comptabilite_finance",
    "informatique",
    "commerciale",
    "rh",
    "administration",
}

UNKNOWN_DEPARTMENT_ID = "unknown"

DEPARTMENT_ACCESS_DENIED_MESSAGE = (
    "Cette fonctionnalité n'est pas disponible pour votre département."
)


@dataclass(frozen=True)
class DepartmentProfile:
    department_id: str
    display_name: str
    description: str
    allowed_agent_domains: frozenset[str]
    allowed_capability_categories: frozenset[str]
    allowed_capabilities: frozenset[str]
    odoo_models: frozenset[str]
    knowledge_scopes: tuple[str, ...]
    llm_project_env: str | None = None
    admin_override: bool = False

    def to_public_dict(self) -> dict:
        return {
            "department_id": self.department_id,
            "display_name": self.display_name,
            "description": self.description,
            "allowed_agent_domains": sorted(self.allowed_agent_domains),
            "allowed_capability_categories": sorted(self.allowed_capability_categories),
            "allowed_capabilities": sorted(self.allowed_capabilities),
            "odoo_models": sorted(self.odoo_models),
            "knowledge_scopes": list(self.knowledge_scopes),
            "llm_project_env": self.llm_project_env,
            "admin_override": self.admin_override,
        }


DEPARTMENT_PROFILES = {
    "administration": DepartmentProfile(
        department_id="administration",
        display_name="Administration",
        description="Compte plateforme et supervision générale de l'orchestrateur.",
        allowed_agent_domains=frozenset({"odoo", "support", "server", "security", "knowledge"}),
        allowed_capability_categories=frozenset({
            "knowledge_read",
            "odoo_product_read",
            "odoo_read",
            "odoo_write",
            "security_review",
            "server_diagnostic",
            "support_help",
        }),
        allowed_capabilities=frozenset(),
        odoo_models=frozenset({
            "account.bank.statement",
            "account.bank.statement.line",
            "account.journal",
            "account.move",
            "account.move.line",
            "product.product",
            "product.template",
            "purchase.order",
            "res.partner",
            "sale.order",
            "stock.picking",
        }),
        knowledge_scopes=("company_common", "administration"),
        llm_project_env="OPENAI_API_KEY_ADMINISTRATION",
        admin_override=True,
    ),
    "informatique": DepartmentProfile(
        department_id="informatique",
        display_name="Informatique",
        description="Support IT, diagnostics serveur locaux de démonstration et sécurité technique.",
        allowed_agent_domains=frozenset({"support", "server", "security", "knowledge"}),
        allowed_capability_categories=frozenset({
            "knowledge_read",
            "security_review",
            "server_diagnostic",
            "support_help",
        }),
        allowed_capabilities=frozenset(),
        odoo_models=frozenset(),
        knowledge_scopes=("company_common", "informatique"),
        llm_project_env="OPENAI_API_KEY_INFORMATIQUE",
    ),
    "comptabilite_finance": DepartmentProfile(
        department_id="comptabilite_finance",
        display_name="Comptabilité & Finance",
        description="Lecture et demandes contrôlées liées aux documents financiers Odoo.",
        allowed_agent_domains=frozenset({"odoo", "knowledge"}),
        allowed_capability_categories=frozenset({
            "knowledge_read",
            "odoo_read",
            "odoo_write",
        }),
        allowed_capabilities=frozenset(),
        odoo_models=frozenset({
            "account.bank.statement",
            "account.bank.statement.line",
            "account.journal",
            "account.move",
            "account.move.line",
            "purchase.order",
            "res.partner",
        }),
        knowledge_scopes=("company_common", "comptabilite_finance"),
        llm_project_env="OPENAI_API_KEY_FINANCE",
    ),
    "commerciale": DepartmentProfile(
        department_id="commerciale",
        display_name="Commerciale",
        description="Lecture commerciale Odoo, produits, clients et commandes client.",
        allowed_agent_domains=frozenset({"odoo", "knowledge", "support"}),
        allowed_capability_categories=frozenset({
            "knowledge_read",
            "odoo_product_read",
            "odoo_read",
            "support_help",
        }),
        allowed_capabilities=frozenset(),
        odoo_models=frozenset({"product.product", "product.template", "res.partner", "sale.order"}),
        knowledge_scopes=("company_common", "commerciale"),
        llm_project_env="OPENAI_API_KEY_COMMERCIALE",
    ),
    "rh": DepartmentProfile(
        department_id="rh",
        display_name="Ressources humaines",
        description="Questions RH et support utilisateur, sans accès Odoo RH sensible.",
        allowed_agent_domains=frozenset({"knowledge", "support"}),
        allowed_capability_categories=frozenset({"knowledge_read", "support_help"}),
        allowed_capabilities=frozenset(),
        odoo_models=frozenset(),
        knowledge_scopes=("company_common", "rh"),
        llm_project_env="OPENAI_API_KEY_RH",
    ),
    "securite": DepartmentProfile(
        department_id="securite",
        display_name="Sécurité",
        description="Questions de sécurité, sensibilisation et support utilisateur.",
        allowed_agent_domains=frozenset({"security", "knowledge", "support"}),
        allowed_capability_categories=frozenset({
            "knowledge_read",
            "security_review",
            "support_help",
        }),
        allowed_capabilities=frozenset(),
        odoo_models=frozenset(),
        knowledge_scopes=("company_common", "securite"),
        llm_project_env="OPENAI_API_KEY_SECURITE",
    ),
    "nettoyage": DepartmentProfile(
        department_id="nettoyage",
        display_name="Nettoyage",
        description="Support opérationnel et lectures sûres de produits/inventaire Odoo.",
        allowed_agent_domains=frozenset({"knowledge", "support", "odoo"}),
        allowed_capability_categories=frozenset({
            "knowledge_read",
            "odoo_product_read",
            "support_help",
        }),
        allowed_capabilities=frozenset(),
        odoo_models=frozenset({"product.product", "product.template"}),
        knowledge_scopes=("company_common", "nettoyage"),
        llm_project_env="OPENAI_API_KEY_NETTOYAGE",
    ),
}

UNKNOWN_DEPARTMENT_PROFILE = DepartmentProfile(
    department_id=UNKNOWN_DEPARTMENT_ID,
    display_name="Département inconnu",
    description="Profil de repli restrictif lorsqu'un département n'est pas reconnu.",
    allowed_agent_domains=frozenset(),
    allowed_capability_categories=frozenset(),
    allowed_capabilities=frozenset(),
    odoo_models=frozenset(),
    knowledge_scopes=("company_common",),
    llm_project_env=None,
)


CAPABILITY_CATEGORIES = {
    "knowledge.creative_generation": "knowledge_read",
    "knowledge.enterprise_answer": "knowledge_read",
    "knowledge.general_answer": "knowledge_read",
    "knowledge.writing_assistance": "knowledge_read",
    "support.troubleshooting": "support_help",
    "security.review": "security_review",
    "server.cpu_usage": "server_diagnostic",
    "server.disk_usage": "server_diagnostic",
    "server.local_health": "server_diagnostic",
    "server.ram_usage": "server_diagnostic",
    "server.uptime": "server_diagnostic",
    "odoo.connection_status": "odoo_product_read",
    "odoo.inventory_summary": "odoo_product_read",
    "odoo.product_search": "odoo_product_read",
    "odoo.product_stock": "odoo_product_read",
    "odoo.partner_search": "odoo_read",
    "odoo.purchase_supplier_ranking": "odoo_read",
    "odoo.generic_read": "odoo_read",
    "odoo.generic_read_details": "odoo_read",
    "odoo.generic_read_search": "odoo_read",
    "odoo.accounting_bank_read": "odoo_read",
    "odoo.customer_invoice_list": "odoo_read",
    "odoo.analytic_account_search": "odoo_read",
    "odoo.analytic_account_details": "odoo_read",
    "odoo.document_details": "odoo_read",
    "odoo.document_details_by_id": "odoo_read",
    "odoo.document_search": "odoo_read",
    "odoo.analytic_boolean_field_list": "odoo_write",
    "odoo.analytic_boolean_update": "odoo_write",
    "odoo.document_date_update": "odoo_write",
    "odoo.document_line_update": "odoo_write",
    "odoo.document_partner_update": "odoo_write",
    "odoo.generic_write_execute": "odoo_write",
    "odoo.generic_write_prepare": "odoo_write",
    "odoo.product_price_update": "odoo_write",
    "odoo.product_write_resolve": "odoo_write",
}

CAPABILITY_DOMAINS = {
    capability: capability.split(".", 1)[0]
    for capability in CAPABILITY_CATEGORIES
}

ACTION_CAPABILITY_MAP = {
    "answer_question": "knowledge.general_answer",
    "creative_generation": "knowledge.creative_generation",
    "enterprise_answer": "knowledge.enterprise_answer",
    "writing_assistance": "knowledge.writing_assistance",
    "check_cpu_usage": "server.cpu_usage",
    "check_disk_usage": "server.disk_usage",
    "check_ram_usage": "server.ram_usage",
    "check_server_health": "server.local_health",
    "check_server_status": "server.uptime",
    "check_service_status": "server.local_health",
    "inventory_product_search": "odoo.product_search",
    "inventory_summary": "odoo.inventory_summary",
    "odoo_generic_read": "odoo.generic_read",
    "odoo_get_record_details": "odoo.generic_read_details",
    "odoo_search_records": "odoo.generic_read_search",
    "odoo_update_field_request": "odoo.generic_write_prepare",
    "product_search": "odoo.product_search",
    "read_document": "odoo.document_details",
    "read_document_field": "odoo.document_details",
    "read_product_stock": "odoo.product_stock",
    "bank_accounting_search": "odoo.accounting_bank_read",
    "supplier_ranking": "odoo.purchase_supplier_ranking",
    "search_document": "odoo.document_search",
    "server_diagnostic_summary": "server.local_health",
    "troubleshoot_access": "support.troubleshooting",
    "troubleshoot_issue": "support.troubleshooting",
    "troubleshoot_network": "support.troubleshooting",
    "update_product_price": "odoo.product_price_update",
}

PERMISSION_CAPABILITY_MAP = {
    "chat_access": "knowledge.general_answer",
    "odoo_document_read": "odoo.document_search",
    "odoo_product_read": "odoo.product_stock",
    "odoo_write": "odoo.product_price_update",
    "security_blocked": "security.review",
    "server_diagnostics": "server.local_health",
    "support_access": "support.troubleshooting",
}


def normalize_department(department: str | None) -> str:
    department = (department or "").strip().lower()
    return department if department in CANONICAL_DEPARTMENTS else UNKNOWN_DEPARTMENT_ID


def get_department_profile(department: str | None) -> DepartmentProfile:
    normalized = normalize_department(department)
    return DEPARTMENT_PROFILES.get(normalized, UNKNOWN_DEPARTMENT_PROFILE)


def list_department_profiles() -> list[dict]:
    return [
        DEPARTMENT_PROFILES[department].to_public_dict()
        for department in sorted(DEPARTMENT_PROFILES)
    ]


def get_knowledge_scopes(department: str | None) -> tuple[str, ...]:
    return get_department_profile(department).knowledge_scopes


def capability_category(capability: str) -> str:
    return CAPABILITY_CATEGORIES.get(capability, "knowledge_read")


def capability_domain(capability: str) -> str:
    return CAPABILITY_DOMAINS.get(capability, capability.split(".", 1)[0])


def is_capability_allowed_for_department(
    department: str | None,
    capability: str,
    odoo_model: str | None = None,
) -> bool:
    profile = get_department_profile(department)

    if profile.admin_override:
        return True

    domain = capability_domain(capability)
    category = capability_category(capability)

    if domain not in profile.allowed_agent_domains:
        return False

    if (
        capability not in profile.allowed_capabilities
        and category not in profile.allowed_capability_categories
    ):
        return False

    if odoo_model and domain == "odoo" and odoo_model not in profile.odoo_models:
        return False

    return True


def _classification_values(classification: dict) -> list[str]:
    values = []

    for key in ("action", "parsed_action", "business_action", "tool_used", "intent"):
        value = classification.get(key)

        if value:
            values.append(str(value))

    return values


def odoo_model_from_classification(classification: dict | None) -> str | None:
    classification = classification or {}
    entities = classification.get("entities")

    if not isinstance(entities, dict):
        entities = {}

    for key in ("model", "target_model", "document_model"):
        value = classification.get(key) or entities.get(key)

        if value:
            return str(value)

    document_type = classification.get("document_type") or entities.get("document_type")

    return {
        "sale_order": "sale.order",
        "purchase_order": "purchase.order",
        "invoice": "account.move",
        "delivery": "stock.picking",
    }.get(str(document_type or ""))


def capability_from_route(
    classification: dict | None,
    route_permission: RoutePermission,
) -> str:
    classification = classification or {}
    explicit_capability = classification.get("capability")

    if explicit_capability in CAPABILITY_CATEGORIES:
        return explicit_capability

    for value in _classification_values(classification):
        if value in ACTION_CAPABILITY_MAP:
            return ACTION_CAPABILITY_MAP[value]

    if route_permission.agent == "knowledge_agent":
        return "knowledge.general_answer"

    if route_permission.agent == "support_agent":
        return "support.troubleshooting"

    if route_permission.agent == "server_agent":
        return "server.local_health"

    if route_permission.agent == "security_agent":
        return "security.review"

    return PERMISSION_CAPABILITY_MAP.get(
        route_permission.permission_category,
        "knowledge.general_answer",
    )


def is_route_allowed_for_department(
    department: str | None,
    classification: dict | None,
    route_permission: RoutePermission,
) -> tuple[bool, str]:
    capability = capability_from_route(classification, route_permission)
    model_name = odoo_model_from_classification(classification)
    return (
        is_capability_allowed_for_department(
            department,
            capability,
            odoo_model=model_name,
        ),
        capability,
    )
