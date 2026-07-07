def make_semantic_request(
    *,
    request_type: str,
    domain: str,
    capability: str,
    agent: str | None = None,
    action: str | None = None,
    execution_mode: str | None = None,
    risk_level: str = "low",
    requires_approval: bool = False,
    topic: str | None = None,
    entities: dict | None = None,
    parameters: dict | None = None,
    clarification_needed: bool = False,
    missing_parameters: list[str] | None = None,
):
    agent = agent or {
        "knowledge": "knowledge_agent",
        "odoo": "odoo_agent",
        "support": "support_agent",
        "server": "server_agent",
        "security": "security_agent",
        "development": "development_agent",
    }.get(domain, "general_agent")
    entities = dict(entities or {})
    parameters = dict(parameters or {})
    missing_parameters = list(missing_parameters or [])

    if topic:
        entities.setdefault("knowledge_topic", topic)

    return {
        "intent": request_type,
        "request_type": request_type,
        "domain": domain,
        "capability": capability,
        "execution_mode": execution_mode,
        "agent": agent,
        "selected_agent": agent,
        "target_system": domain,
        "action": action or capability.rsplit(".", 1)[-1],
        "risk_level": risk_level,
        "risk": risk_level,
        "requires_approval": requires_approval,
        "approval_required": requires_approval,
        "entities": {**entities, **parameters},
        "parameters": parameters,
        "clarification_needed": clarification_needed,
        "missing_parameters": missing_parameters,
        "semantic_request": {
            "request_type": request_type,
            "domain": domain,
            "capability": capability,
            "requires_internal_context": execution_mode == "retrieval_grounded",
            "topic": topic,
            "entities": entities,
            "parameters": parameters,
            "clarification_needed": clarification_needed,
            "missing_parameters": missing_parameters,
        },
        "confidence": "high",
        "classifier_source": "openai_structured",
        "semantic_source": "openai_structured",
        "classifier_error": None,
    }
