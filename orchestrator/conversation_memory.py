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

DOCUMENT_MODEL_TO_TYPE = {
    "purchase.order": "purchase_order",
    "sale.order": "sale_order",
    "account.move": "invoice",
    "stock.picking": "delivery",
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


class ConversationMemory:
    def __init__(self):
        self._sessions: dict[str, dict[str, Any]] = {}

    def get_context(self, session_id: str) -> dict[str, Any]:
        return dict(self._sessions.get(session_id, {}))

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

    def update_from_result(self, session_id: str, result: Any) -> dict[str, Any]:
        product_memory_worthy = self._is_memory_worthy_product_result(result)
        document_memory_worthy = self._is_memory_worthy_document_result(result)
        recent_document_candidates = self._extract_recent_document_candidates(result)

        if (
            not product_memory_worthy
            and not document_memory_worthy
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

        for key, value in extracted.items():
            if _has_value(value):
                context[key] = value

        context["updated_at"] = _utc_timestamp()
        return dict(context)

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
