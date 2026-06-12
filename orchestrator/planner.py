def create_plan(intent: str, message: str, risk_level: str):
    text = message.lower()

    if intent == "odoo":
        if "stock" in text or "inventory" in text or "inventaire" in text:
            return [
                "analyze_stock_request",
                "identify_product",
                "check_or_prepare_odoo_stock_operation",
                "apply_approval_workflow_if_needed",
                "return_stock_result"
            ]

        if "purchase" in text or "achat" in text or "supplier" in text:
            return [
                "analyze_purchase_request",
                "validate_supplier_or_product",
                "prepare_purchase_operation",
                "apply_approval_workflow",
                "return_purchase_result"
            ]

        return [
            "analyze_odoo_request",
            "identify_odoo_module",
            "prepare_odoo_operation",
            "apply_approval_workflow_if_needed",
            "return_odoo_result"
        ]

    if intent == "support":
        return [
            "diagnose_user_issue",
            "identify_affected_system",
            "suggest_resolution_steps",
            "escalate_if_unresolved"
        ]

    if intent == "knowledge":
        return [
            "analyze_information_request",
            "search_relevant_knowledge_source",
            "summarize_answer",
            "return_referenced_response"
        ]

    if intent == "development":
        return [
            "analyze_development_request",
            "identify_component_or_error",
            "suggest_code_or_debugging_steps",
            "return_developer_guidance"
        ]

    if intent == "security":
        return [
            "analyze_security_request",
            "assess_security_risk",
            "recommend_secure_action",
            "apply_approval_workflow_if_needed"
        ]

    if intent == "server":
        return [
            "analyze_infrastructure_request",
            "check_service_or_resource_status",
            "recommend_server_action",
            "apply_approval_workflow_if_needed"
        ]

    return [
        "analyze_general_request",
        "generate_general_response"
    ]