import re
import unicodedata
from datetime import datetime, timezone
from typing import Any


PRODUCT_REFERENCE_TERMS = [
    "it",
    "its",
    "its details",
    "its information",
    "its info",
    "its stock",
    "its quantity",
    "its price",
    "its reference",
    "this product",
    "that product",
    "ses details",
    "ses informations",
    "ses infos",
    "sa fiche",
    "son stock",
    "sa quantite",
    "son prix",
    "sa reference",
    "ce produit",
    "cet article",
    "ce dernier",
    "celui-ci",
    "celui ci",
    "le produit",
    "l article",
    "l'article",
    "larticle",
]

DOCUMENT_REFERENCE_TERMS = [
    "ce document",
    "ce bon",
    "cette facture",
    "ce dernier document",
    "le document",
    "ce document",
    "son fournisseur",
    "son statut",
    "son etat",
    "son état",
    "resume ce document",
    "resumer ce document",
    "résume ce document",
    "montre-moi les details de ce document",
    "montre moi les details de ce document",
    "details de ce document",
    "détails de ce document",
    "show its details",
    "its details",
    "what is its status",
    "who is the supplier",
    "who is the supplier?",
    "supplier",
    "its status",
]

SENSITIVE_KEYS = {
    "url",
    "database",
    "username",
    "uid",
    "api_key",
    "password",
    "token",
    "secret",
}

SAFE_MEMORY_FIELDS = [
    "last_agent",
    "last_intent",
    "last_model",
    "last_business_object",
    "last_action",
    "last_count",
    "last_safe_fields",
    "last_original_request",
    "last_product_name",
    "last_product_id",
    "last_document_name",
    "last_document_id",
    "last_document_model",
    "last_document_type",
    "last_partner_name",
    "recent_document_candidates",
    "updated_at",
]

PENDING_CLARIFICATION_KEY = "pending_clarification"
PENDING_TASK_KEY = "pending_task"

DOCUMENT_MODEL_TO_TYPE = {
    "purchase.order": "purchase_order",
    "sale.order": "sale_order",
    "account.move": "invoice",
    "stock.picking": "delivery",
}

MODEL_BUSINESS_OBJECTS = {
    "res.partner": "contacts",
    "product.product": "produits",
    "product.template": "produits",
    "sale.order": "commandes client",
    "purchase.order": "bons de commande",
    "account.move": "factures",
    "stock.picking": "livraisons",
}

MODEL_SAFE_FOLLOWUP_FIELDS = {
    "res.partner": ["name", "email", "phone", "customer_rank", "supplier_rank", "is_company"],
    "product.product": ["name", "default_code", "qty_available", "virtual_available"],
    "product.template": ["name", "default_code", "list_price"],
    "sale.order": ["name", "partner_id", "state", "date_order"],
    "purchase.order": ["name", "partner_id", "state", "date_order"],
    "account.move": ["name", "partner_id", "state", "date"],
    "stock.picking": ["name", "partner_id", "state", "scheduled_date"],
}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    normalized_text = ascii_value.lower().replace("’", "'")
    return " ".join(normalized_text.split())


def _contains_term(text: str, term: str) -> bool:
    if term in {"it", "its"}:
        return re.search(rf"\b{term}\b", text, re.IGNORECASE) is not None

    return term in text


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower()

    return (
        normalized in SENSITIVE_KEYS
        or "api_key" in normalized
        or "password" in normalized
        or "token" in normalized
        or "secret" in normalized
    )


def _has_value(value: Any) -> bool:
    return value is not None and value != ""


def _clean_product_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = value.strip()

    if not cleaned or cleaned == "-":
        return None

    return cleaned


def _normalize_agent(value: Any) -> Any:
    if value == "odoo_agent":
        return "odoo"

    return value


def _extract_followup_limit(message: str, default: int = 3) -> int:
    normalized = _normalize_text(message)
    match = re.search(r"\b(\d{1,2})\b", normalized)

    if not match:
        return default

    return max(1, min(int(match.group(1)), 10))


class ConversationMemory:
    def __init__(self):
        self._sessions: dict[str, dict[str, Any]] = {}

    def get_context(self, session_id: str) -> dict[str, Any]:
        return dict(self._sessions.get(session_id, {}))

    def get_pending_clarification(self, session_id: str) -> dict[str, Any]:
        context = self._sessions.get(session_id, {})
        pending = context.get(PENDING_CLARIFICATION_KEY)

        return dict(pending) if isinstance(pending, dict) else {}

    def get_pending_task(self, session_id: str) -> dict[str, Any]:
        context = self._sessions.get(session_id, {})
        pending = context.get(PENDING_TASK_KEY)

        return dict(pending) if isinstance(pending, dict) else {}

    def set_pending_clarification(
        self,
        session_id: str,
        pending: dict[str, Any],
    ) -> dict[str, Any]:
        safe_pending = self._safe_pending_clarification(session_id, pending)

        if not safe_pending:
            return dict(self._sessions.get(session_id, {}))

        context = self._sessions.setdefault(session_id, {})
        context[PENDING_CLARIFICATION_KEY] = safe_pending
        context["updated_at"] = _utc_timestamp()

        return dict(context)

    def clear_pending_clarification(self, session_id: str) -> dict[str, Any]:
        context = self._sessions.get(session_id)

        if not context:
            return {}

        context.pop(PENDING_CLARIFICATION_KEY, None)
        context["updated_at"] = _utc_timestamp()

        return dict(context)

    def set_pending_task(
        self,
        session_id: str,
        pending: dict[str, Any],
    ) -> dict[str, Any]:
        safe_pending = self._safe_pending_task(session_id, pending)

        if not safe_pending:
            return dict(self._sessions.get(session_id, {}))

        context = self._sessions.setdefault(session_id, {})
        context[PENDING_TASK_KEY] = safe_pending
        context["updated_at"] = _utc_timestamp()

        return dict(context)

    def clear_pending_task(self, session_id: str) -> dict[str, Any]:
        context = self._sessions.get(session_id)

        if not context:
            return {}

        context.pop(PENDING_TASK_KEY, None)
        context["updated_at"] = _utc_timestamp()

        return dict(context)

    def get_safe_context(self, session_id: str) -> dict[str, Any]:
        context = self._sessions.get(session_id, {})
        return {
            key: context.get(key)
            for key in SAFE_MEMORY_FIELDS
            if key in context
        }

    def resolve_references(self, message: str, session_id: str) -> dict[str, Any]:
        context = self._sessions.get(session_id, {})
        normalized = _normalize_text(message)
        spaced_apostrophe_text = normalized.replace("'", " ")
        has_product_reference = any(
            _contains_term(normalized, term)
            or _contains_term(spaced_apostrophe_text, term)
            for term in PRODUCT_REFERENCE_TERMS
        )
        has_document_reference = any(
            _contains_term(normalized, term)
            or _contains_term(spaced_apostrophe_text, term)
            for term in DOCUMENT_REFERENCE_TERMS
        )

        if has_document_reference:
            resolved_document: dict[str, Any] = {}

            if context.get("last_document_name"):
                resolved_document["document_name"] = context["last_document_name"]

            if context.get("last_document_id") is not None:
                resolved_document["document_id"] = context["last_document_id"]

            if context.get("last_document_model"):
                resolved_document["document_model"] = context["last_document_model"]

            if context.get("last_document_type"):
                resolved_document["document_type"] = context["last_document_type"]

            if context.get("last_partner_name"):
                resolved_document["partner_name"] = context["last_partner_name"]

            if resolved_document:
                resolved_document["reference_type"] = "document"
                return resolved_document

        if not has_product_reference:
            return {}

        resolved: dict[str, Any] = {}

        if context.get("last_product_name"):
            resolved["product_name"] = context["last_product_name"]

        if context.get("last_product_id") is not None:
            resolved["product_id"] = context["last_product_id"]

        if resolved:
            resolved["reference_type"] = "product"

        return resolved

    def resolve_odoo_result_reference(self, message: str, session_id: str) -> dict[str, Any]:
        context = self._sessions.get(session_id, {})

        if _normalize_agent(context.get("last_agent")) != "odoo":
            return {}

        last_model = _clean_product_name(context.get("last_model"))

        if not last_model:
            return {}

        normalized = _normalize_text(message)
        tokens = set(normalized.replace("-", " ").split())
        business_object = _clean_product_name(context.get("last_business_object")) or MODEL_BUSINESS_OBJECTS.get(last_model)
        business_tokens = set(_normalize_text(business_object or "").split())
        reference_terms = {
            "eux",
            "parmi",
            "memes",
            "meme",
            "ceux",
            "celles",
            "ceux-la",
            "ceux",
            "quelques",
            "uns",
            "unes",
        }
        list_terms = {
            "cite",
            "citer",
            "donne",
            "liste",
            "lister",
            "montre",
            "affiche",
            "show",
            "list",
            "give",
        }

        has_reference = bool(tokens & reference_terms) or "parmi eux" in normalized or "les memes" in normalized
        has_list_intent = bool(tokens & list_terms)
        has_business_object = bool(business_tokens and tokens & business_tokens)
        short_business_reply = len(tokens) <= 3 and has_business_object

        if not ((has_reference and has_list_intent) or short_business_reply or (has_list_intent and has_business_object)):
            return {}

        safe_fields = context.get("last_safe_fields")

        if not isinstance(safe_fields, list) or not safe_fields:
            safe_fields = MODEL_SAFE_FOLLOWUP_FIELDS.get(last_model, [])

        if not safe_fields:
            return {}

        return {
            "reference_type": "odoo_result",
            "model": last_model,
            "business_object": business_object or MODEL_BUSINESS_OBJECTS.get(last_model) or last_model,
            "action": "list",
            "limit": _extract_followup_limit(message),
            "safe_fields": [
                str(field)
                for field in safe_fields
                if isinstance(field, str) and not _is_sensitive_key(field)
            ],
            "last_count": context.get("last_count"),
            "original_request": context.get("last_original_request"),
        }

    def resolve_document_candidate(self, session_id: str, document_id: Any) -> dict[str, Any]:
        context = self._sessions.get(session_id, {})
        candidates = context.get("recent_document_candidates")

        if not isinstance(candidates, list):
            return {}

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue

            if str(candidate.get("document_id")) == str(document_id):
                return dict(candidate)

        return {}

    def _safe_pending_clarification(
        self,
        session_id: str,
        pending: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(pending, dict):
            return {}

        classification = (
            pending.get("classification")
            if isinstance(pending.get("classification"), dict)
            else {}
        )
        result = (
            pending.get("result")
            if isinstance(pending.get("result"), dict)
            else {}
        )
        entities = (
            classification.get("entities")
            if isinstance(classification.get("entities"), dict)
            else {}
        )
        parameters = (
            classification.get("parameters")
            if isinstance(classification.get("parameters"), dict)
            else {}
        )
        missing_parameters = (
            pending.get("missing_parameters")
            or classification.get("missing_parameters")
            or result.get("missing_parameters")
        )

        if not isinstance(missing_parameters, list):
            missing_parameters = []

        original_request = _clean_product_name(pending.get("original_request"))
        resolved_request = _clean_product_name(pending.get("resolved_request"))

        if not original_request and not resolved_request:
            return {}

        return {
            "session_id": session_id,
            "original_request": original_request or resolved_request,
            "resolved_request": resolved_request or original_request,
            "selected_agent": (
                classification.get("selected_agent")
                or classification.get("agent")
                or result.get("selected_agent")
                or result.get("agent")
            ),
            "capability": classification.get("capability") or result.get("capability"),
            "target_system": (
                classification.get("target_system")
                or result.get("target_system")
            ),
            "domain": classification.get("domain") or result.get("domain"),
            "action": (
                classification.get("action")
                or result.get("parsed_action")
                or result.get("action")
            ),
            "intent": classification.get("intent") or result.get("intent"),
            "missing_parameters": [
                str(item)
                for item in missing_parameters
                if item not in {None, ""}
            ],
            "entities": {
                str(key): value
                for key, value in entities.items()
                if not _is_sensitive_key(str(key)) and _has_value(value)
            },
            "parameters": {
                str(key): value
                for key, value in parameters.items()
                if not _is_sensitive_key(str(key)) and _has_value(value)
            },
            "created_at": pending.get("created_at") or _utc_timestamp(),
            "updated_at": _utc_timestamp(),
        }

    def _safe_pending_task(
        self,
        session_id: str,
        pending: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(pending, dict):
            return {}

        classification = (
            pending.get("classification")
            if isinstance(pending.get("classification"), dict)
            else {}
        )
        result = (
            pending.get("result")
            if isinstance(pending.get("result"), dict)
            else {}
        )
        entities = (
            classification.get("entities")
            if isinstance(classification.get("entities"), dict)
            else {}
        )
        parameters = (
            classification.get("parameters")
            if isinstance(classification.get("parameters"), dict)
            else {}
        )

        original_request = _clean_product_name(pending.get("original_request"))
        resolved_request = _clean_product_name(pending.get("resolved_request"))

        if not original_request and not resolved_request:
            return {}

        return {
            "session_id": session_id,
            "context_type": pending.get("context_type") or "task_follow_up",
            "original_request": original_request or resolved_request,
            "resolved_request": resolved_request or original_request,
            "selected_agent": (
                classification.get("selected_agent")
                or classification.get("agent")
                or result.get("selected_agent")
                or result.get("agent")
            ),
            "capability": classification.get("capability") or result.get("capability"),
            "target_system": (
                classification.get("target_system")
                or result.get("target_system")
            ),
            "domain": classification.get("domain") or result.get("domain"),
            "action": (
                classification.get("action")
                or result.get("parsed_action")
                or result.get("action")
            ),
            "intent": classification.get("intent") or result.get("intent"),
            "reason": pending.get("reason") or result.get("status"),
            "suggested_next_action": pending.get("suggested_next_action"),
            "entities": {
                str(key): value
                for key, value in entities.items()
                if not _is_sensitive_key(str(key)) and _has_value(value)
            },
            "parameters": {
                str(key): value
                for key, value in parameters.items()
                if not _is_sensitive_key(str(key)) and _has_value(value)
            },
            "created_at": pending.get("created_at") or _utc_timestamp(),
            "updated_at": _utc_timestamp(),
        }

    def update_from_result(self, session_id: str, result: Any) -> dict[str, Any]:
        product_memory_worthy = self._is_memory_worthy_product_result(result)
        document_memory_worthy = self._is_memory_worthy_document_result(result)
        odoo_read_memory = self._extract_odoo_read_memory(result)
        recent_document_candidates = self._extract_recent_document_candidates(result)

        if (
            not product_memory_worthy
            and not document_memory_worthy
            and not odoo_read_memory
            and not recent_document_candidates
        ):
            return dict(self._sessions.get(session_id, {}))

        context = self._sessions.setdefault(session_id, {})

        extracted = {
            "last_agent": _normalize_agent(
                self._find_first(result, ["agent", "selected_agent"])
            ),
            "last_intent": self._find_first(result, ["intent"]),
        }

        if product_memory_worthy:
            extracted.update({
                "last_product_name": self._extract_product_name(result),
                "last_product_id": self._extract_product_id(result),
            })

        if document_memory_worthy:
            extracted.update({
                "last_document_name": self._extract_document_name(result),
                "last_document_id": self._extract_document_id(result),
                "last_document_model": self._extract_document_model(result),
                "last_document_type": self._extract_document_type(result),
                "last_partner_name": self._extract_partner_name(result),
            })

        if recent_document_candidates:
            extracted["recent_document_candidates"] = recent_document_candidates

        if odoo_read_memory:
            extracted.update(odoo_read_memory)

        for key, value in extracted.items():
            if _has_value(value):
                context[key] = value

        context["updated_at"] = _utc_timestamp()
        return dict(context)

    def _extract_odoo_read_memory(self, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}

        status = str(result.get("status") or "").lower()

        if status in {"not_found", "ambiguous", "failed", "needs_clarification", "blocked", "unsupported"}:
            return {}

        agent = _normalize_agent(self._find_first(result, ["agent", "selected_agent"]))
        target_system = self._find_first(result, ["target_system", "domain"])

        if agent != "odoo" and target_system != "odoo":
            return {}

        model = (
            self._extract_odoo_memory_model(result)
            or _clean_product_name(self._find_nested_read_plan_value(result, "model_hint"))
            or _clean_product_name(self._find_nested_read_plan_value(result, "model"))
        )

        if model not in MODEL_SAFE_FOLLOWUP_FIELDS:
            return {}

        action = (
            _clean_product_name(self._find_nested_read_plan_value(result, "operation"))
            or _clean_product_name(self._find_first(result, ["parsed_action", "action", "tool_used"]))
        )
        count = self._find_first(result, ["record_count", "count_returned"])
        business_object = (
            _clean_product_name(self._find_nested_read_plan_value(result, "business_object"))
            or MODEL_BUSINESS_OBJECTS.get(model)
        )
        safe_fields = self._find_first(result, ["fields_used", "fields"])

        if not isinstance(safe_fields, list) or not safe_fields:
            safe_fields = MODEL_SAFE_FOLLOWUP_FIELDS[model]

        return {
            "last_agent": "odoo",
            "last_model": model,
            "last_business_object": business_object,
            "last_action": action,
            "last_count": count,
            "last_safe_fields": [
                str(field)
                for field in safe_fields
                if isinstance(field, str) and not _is_sensitive_key(field)
            ],
            "last_original_request": _clean_product_name(self._find_first(result, ["user_message", "original_request"])),
        }

    def _extract_odoo_memory_model(self, result: dict) -> str | None:
        containers = self._candidate_containers(result)
        agent_result = result.get("agent_result")

        if isinstance(agent_result, dict):
            containers.append(agent_result)

        for container in containers:
            for key in ("odoo_model", "selected_model_name", "model"):
                model = _clean_product_name(container.get(key))

                if model and model in MODEL_SAFE_FOLLOWUP_FIELDS:
                    return model

        return None

    def _find_nested_read_plan_value(self, value: Any, key: str) -> Any:
        if isinstance(value, dict):
            read_plan = value.get("read_plan")

            if isinstance(read_plan, dict) and _has_value(read_plan.get(key)):
                return read_plan.get(key)

            for entry_key, entry in value.items():
                if _is_sensitive_key(str(entry_key)):
                    continue

                found = self._find_nested_read_plan_value(entry, key)

                if _has_value(found):
                    return found

        if isinstance(value, list):
            for entry in value:
                found = self._find_nested_read_plan_value(entry, key)

                if _has_value(found):
                    return found

        return None

    def _is_memory_worthy_product_result(self, result: Any) -> bool:
        if not isinstance(result, dict):
            return False

        status = str(result.get("status") or "").lower()

        if status in {"not_found", "ambiguous", "failed", "needs_clarification"}:
            return False

        if result.get("ambiguous") is True or result.get("found") is False:
            return False

        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        metadata = (
            result.get("metadata")
            if isinstance(result.get("metadata"), dict)
            else {}
        )
        nested_result = (
            result.get("result")
            if isinstance(result.get("result"), dict)
            else {}
        )

        for container in (metadata, result, data, nested_result):
            if container.get("ambiguous") is True or container.get("found") is False:
                return False

        product_name = (
            _clean_product_name(metadata.get("product_name"))
            or _clean_product_name(result.get("product_name"))
            or _clean_product_name(data.get("product_name"))
            or _clean_product_name(data.get("product"))
            or _clean_product_name(nested_result.get("product_name"))
            or _clean_product_name(nested_result.get("product"))
        )
        product_id = (
            metadata.get("product_id")
            or result.get("product_id")
            or data.get("product_id")
            or nested_result.get("product_id")
        )

        return bool(product_name and _has_value(product_id))

    def _is_memory_worthy_document_result(self, result: Any) -> bool:
        if not isinstance(result, dict):
            return False

        status = str(result.get("status") or "").lower()

        if status in {"not_found", "ambiguous", "failed", "needs_clarification"}:
            return False

        for container in self._candidate_containers(result):
            container_status = str(container.get("status") or "").lower()
            candidates = container.get("candidates")

            if container_status in {"not_found", "ambiguous", "failed", "needs_clarification"}:
                return False

            if container.get("ambiguous") is True or container.get("found") is False:
                return False

            if isinstance(candidates, list) and len(candidates) > 1:
                return False

        document_id = self._extract_explicit_document_id(result)
        document_name = self._extract_document_name(result)

        return _has_value(document_id) and bool(document_name)

    def _extract_recent_document_candidates(self, result: Any) -> list[dict[str, Any]]:
        if not isinstance(result, dict):
            return []

        safe_candidates: list[dict[str, Any]] = []

        for container in self._candidate_containers(result):
            if container.get("ambiguous") is not True:
                continue

            candidates = container.get("candidates")

            if not isinstance(candidates, list) or len(candidates) <= 1:
                continue

            for candidate in candidates:
                safe_candidate = self._safe_document_candidate(candidate)

                if safe_candidate:
                    safe_candidates.append(safe_candidate)

        deduped = []
        seen = set()

        for candidate in safe_candidates:
            key = (
                str(candidate.get("document_id")),
                candidate.get("document_model"),
            )

            if key in seen:
                continue

            seen.add(key)
            deduped.append(candidate)

        return deduped

    def _safe_document_candidate(self, candidate: Any) -> dict[str, Any]:
        if not isinstance(candidate, dict):
            return {}

        document_id = (
            candidate.get("document_id")
            or candidate.get("record_id")
            or candidate.get("id")
        )
        document_name = (
            _clean_product_name(candidate.get("document_name"))
            or _clean_product_name(candidate.get("name"))
        )
        document_model = (
            _clean_product_name(candidate.get("document_model"))
            or _clean_product_name(candidate.get("model"))
        )

        if not _has_value(document_id) or not document_name or not document_model:
            return {}

        safe_candidate = {
            "document_id": document_id,
            "document_name": document_name,
            "document_model": document_model,
        }

        document_type = (
            _clean_product_name(candidate.get("document_type"))
            or DOCUMENT_MODEL_TO_TYPE.get(document_model)
        )
        partner_name = (
            _clean_product_name(candidate.get("partner_name"))
            or _clean_product_name(candidate.get("partner"))
        )

        if document_type:
            safe_candidate["document_type"] = document_type

        if partner_name:
            safe_candidate["partner_name"] = partner_name

        return safe_candidate

    def _candidate_containers(self, result: dict) -> list[dict]:
        containers = []

        for key in ("metadata", "data", "result"):
            value = result.get(key)
            if isinstance(value, dict):
                containers.append(value)

                nested_metadata = value.get("metadata")
                if isinstance(nested_metadata, dict):
                    containers.append(nested_metadata)

        containers.append(result)
        return containers

    def _extract_product_name(self, result: dict) -> str | None:
        for container in self._candidate_containers(result):
            product_name = (
                _clean_product_name(container.get("product_name"))
                or _clean_product_name(container.get("product"))
                or _clean_product_name(container.get("record_query"))
                or _clean_product_name(container.get("product_query"))
            )

            if product_name:
                return product_name

        return None

    def _extract_product_id(self, result: dict) -> Any:
        for container in self._candidate_containers(result):
            product_id = container.get("product_id")

            if _has_value(product_id):
                return product_id

        return None

    def _extract_document_name(self, result: dict) -> str | None:
        for container in self._candidate_containers(result):
            document = container.get("document")
            document_name = (
                _clean_product_name(container.get("document_name"))
                or _clean_product_name(container.get("name"))
                or (
                    _clean_product_name(document.get("name"))
                    if isinstance(document, dict)
                    else None
                )
            )

            if document_name:
                return document_name

        return None

    def _extract_document_id(self, result: dict) -> Any:
        explicit_id = self._extract_explicit_document_id(result)

        if _has_value(explicit_id):
            return explicit_id

        for container in self._candidate_containers(result):
            document = container.get("document")
            document_id = (
                container.get("record_id")
                or container.get("id")
                or (
                    document.get("record_id") or document.get("id")
                    if isinstance(document, dict)
                    else None
                )
            )

            if _has_value(document_id):
                return document_id

        return None

    def _extract_explicit_document_id(self, result: dict) -> Any:
        for container in self._candidate_containers(result):
            document_id = container.get("document_id")

            if _has_value(document_id):
                return document_id

        return None

    def _extract_document_model(self, result: dict) -> str | None:
        for container in self._candidate_containers(result):
            document = container.get("document")
            model = (
                _clean_product_name(container.get("document_model"))
                or _clean_product_name(container.get("model"))
                or (
                    _clean_product_name(document.get("model"))
                    if isinstance(document, dict)
                    else None
                )
            )

            if model:
                return model

        return None

    def _extract_document_type(self, result: dict) -> str | None:
        for container in self._candidate_containers(result):
            document_type = _clean_product_name(container.get("document_type"))

            if document_type:
                return document_type

        model = self._extract_document_model(result)

        return DOCUMENT_MODEL_TO_TYPE.get(model or "")

    def _extract_partner_name(self, result: dict) -> str | None:
        for container in self._candidate_containers(result):
            document = container.get("document")
            partner_name = (
                _clean_product_name(container.get("partner_name"))
                or _clean_product_name(container.get("partner"))
                or (
                    _clean_product_name(document.get("partner"))
                    if isinstance(document, dict)
                    else None
                )
            )

            if partner_name:
                return partner_name

        return None

    def _find_first(self, value: Any, keys: list[str]) -> Any:
        if isinstance(value, dict):
            for key, entry in value.items():
                if _is_sensitive_key(str(key)):
                    continue

                if key in keys and _has_value(entry):
                    return entry

            for key, entry in value.items():
                if _is_sensitive_key(str(key)):
                    continue

                found = self._find_first(entry, keys)

                if _has_value(found):
                    return found

        if isinstance(value, list):
            for entry in value:
                found = self._find_first(entry, keys)

                if _has_value(found):
                    return found

        return None


conversation_memory = ConversationMemory()
