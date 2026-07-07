import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path


SOURCE_TYPE_INTERNAL_DOCUMENT = "internal_document"
SOURCE_TYPE_OFFICIAL_WEB = "official_web"
SOURCE_TYPE_EXTERNAL_WEB = "external_web"

SUPPORTED_SOURCE_TYPES = {
    SOURCE_TYPE_INTERNAL_DOCUMENT,
    SOURCE_TYPE_OFFICIAL_WEB,
}

FUTURE_SOURCE_TYPES = {
    SOURCE_TYPE_EXTERNAL_WEB,
}

SOURCE_TRUST_RANK = {
    SOURCE_TYPE_INTERNAL_DOCUMENT: 0,
    SOURCE_TYPE_OFFICIAL_WEB: 1,
    SOURCE_TYPE_EXTERNAL_WEB: 2,
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPOSITORY_PATH = Path(
    os.getenv(
        "KNOWLEDGE_REPOSITORY_PATH",
        PROJECT_ROOT / "storage" / "knowledge" / "repository.json",
    )
)
LEGACY_REPOSITORY_PATH = PROJECT_ROOT / "storage" / "knowledge_repository.json"

DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 160
EMBEDDING_DIMENSIONS = 64

ENTITY_ONLY_TOKENS = {
    "baco",
    "company",
    "entreprise",
    "jamain",
}

QUERY_QUESTION_TOKENS = {
    "about",
    "comment",
    "dans",
    "des",
    "does",
    "est",
    "for",
    "how",
    "les",
    "quoi",
    "que",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "qui",
    "sur",
    "the",
    "what",
    "who",
    "why",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def tokenize(value: str) -> list[str]:
    return re.findall(r"[a-z0-9À-ÿ]{3,}", (value or "").lower())


def content_checksum(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def stable_document_id(source_type: str, canonical_url: str, scope: str) -> str:
    raw = f"{source_type}:{scope}:{canonical_url}".encode("utf-8")
    return f"doc_{hashlib.sha256(raw).hexdigest()[:24]}"


def build_local_embedding(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSIONS

    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % EMBEDDING_DIMENSIONS
        vector[index] += 1.0

    norm = math.sqrt(sum(value * value for value in vector))

    if not norm:
        return vector

    return [round(value / norm, 8) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0

    return sum(a * b for a, b in zip(left, right))


def chunk_text(text: str, max_chars: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    text = normalize_whitespace(text)

    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + max_chars, len(text))

        if end < len(text):
            split_at = max(
                text.rfind(". ", start, end),
                text.rfind("\n", start, end),
                text.rfind(" ", start, end),
            )

            if split_at > start + max_chars // 2:
                end = split_at + 1

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - DEFAULT_CHUNK_OVERLAP, start + 1)

    return chunks


class KnowledgeRepository:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or DEFAULT_REPOSITORY_PATH)

    def _load_from_path(self, path: Path) -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return self._empty_store()

        if not isinstance(data, dict):
            return self._empty_store()

        data.setdefault("version", 1)
        data.setdefault("documents", [])
        data.setdefault("chunks", [])
        return data

    def _empty_store(self) -> dict:
        return {
            "version": 1,
            "documents": [],
            "chunks": [],
        }

    def load(self) -> dict:
        if self.path.exists():
            return self._load_from_path(self.path)

        if self.path == DEFAULT_REPOSITORY_PATH and LEGACY_REPOSITORY_PATH.exists():
            data = self._load_from_path(LEGACY_REPOSITORY_PATH)

            if data.get("documents") or data.get("chunks"):
                self.save(data)
                return data

        return self._empty_store()

    def save(self, data: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def upsert_document(
        self,
        *,
        title: str,
        canonical_url: str,
        text: str,
        source_type: str,
        source_domain: str,
        department_scope: str,
    ) -> dict:
        if source_type not in SUPPORTED_SOURCE_TYPES:
            raise ValueError(f"Unsupported knowledge source type: {source_type}")

        text = normalize_whitespace(text)
        checksum = content_checksum(text)
        now = utc_now_iso()
        data = self.load()
        documents = data["documents"]
        chunks = data["chunks"]
        existing = next(
            (
                document
                for document in documents
                if document.get("canonical_url") == canonical_url
                and document.get("source_type") == source_type
                and document.get("department_scope") == department_scope
            ),
            None,
        )

        if existing and existing.get("checksum") == checksum:
            existing["last_fetched_at"] = now
            existing["status"] = "unchanged"
            self.save(data)
            return {
                "status": "unchanged",
                "document": dict(existing),
                "chunks_indexed": 0,
            }

        document_id = (
            existing.get("document_id")
            if existing
            else stable_document_id(source_type, canonical_url, department_scope)
        )
        status = "updated" if existing else "indexed"
        document = {
            "document_id": document_id,
            "title": title or canonical_url,
            "canonical_url": canonical_url,
            "source_type": source_type,
            "source_domain": source_domain,
            "department_scope": department_scope,
            "checksum": checksum,
            "ingested_at": existing.get("ingested_at") if existing else now,
            "last_fetched_at": now,
            "status": status,
        }

        if existing:
            existing.clear()
            existing.update(document)
            chunks[:] = [
                chunk
                for chunk in chunks
                if chunk.get("document_id") != document_id
            ]
        else:
            documents.append(document)

        new_chunks = []

        for index, chunk in enumerate(chunk_text(text)):
            chunk_id = f"{document_id}_chunk_{index + 1}"
            new_chunks.append({
                "chunk_id": chunk_id,
                "document_id": document_id,
                "chunk_index": index,
                "text": chunk,
                "embedding": build_local_embedding(chunk),
                "tokens": sorted(set(tokenize(chunk))),
                "source_type": source_type,
                "department_scope": department_scope,
                "title": document["title"],
                "canonical_url": canonical_url,
                "source_domain": source_domain,
            })

        chunks.extend(new_chunks)
        self.save(data)

        return {
            "status": status,
            "document": dict(document),
            "chunks_indexed": len(new_chunks),
        }

    def search(
        self,
        query: str,
        *,
        allowed_scopes: tuple[str, ...] | list[str],
        source_types: set[str] | None = None,
        limit: int = 4,
    ) -> list[dict]:
        query_tokens = set(tokenize(query))

        if not query_tokens:
            return []

        requested_topic_tokens = query_tokens - ENTITY_ONLY_TOKENS - QUERY_QUESTION_TOKENS
        allowed_scope_set = set(allowed_scopes or [])
        source_types = source_types or SUPPORTED_SOURCE_TYPES
        query_embedding = build_local_embedding(query)
        data = self.load()
        scored = []

        for chunk in data.get("chunks", []):
            if chunk.get("department_scope") not in allowed_scope_set:
                continue

            if chunk.get("source_type") not in source_types:
                continue

            chunk_tokens = set(chunk.get("tokens") or tokenize(chunk.get("text", "")))
            overlap = query_tokens & chunk_tokens
            topic_overlap = requested_topic_tokens & chunk_tokens

            if requested_topic_tokens and not topic_overlap:
                continue

            embedding_score = cosine_similarity(
                query_embedding,
                chunk.get("embedding") or [],
            )
            score = (len(overlap) * 2.0) + embedding_score

            if score <= 0:
                continue

            scored.append((score, SOURCE_TRUST_RANK.get(chunk.get("source_type"), 99), chunk))

        scored.sort(key=lambda item: (-item[0], item[1], item[2].get("title", "")))
        results = []

        for score, _, chunk in scored[:limit]:
            results.append({
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "text": chunk.get("text", ""),
                "score": score,
                "source_type": chunk.get("source_type"),
                "department_scope": chunk.get("department_scope"),
                "title": chunk.get("title"),
                "canonical_url": chunk.get("canonical_url"),
                "source_domain": chunk.get("source_domain"),
            })

        return results

    def stats(self) -> dict:
        data = self.load()
        source_type_counts = {}
        scope_counts = {}

        for document in data.get("documents", []):
            source_type = document.get("source_type") or "unknown"
            scope = document.get("department_scope") or "unknown"
            source_type_counts[source_type] = source_type_counts.get(source_type, 0) + 1
            scope_counts[scope] = scope_counts.get(scope, 0) + 1

        return {
            "documents": len(data.get("documents", [])),
            "chunks": len(data.get("chunks", [])),
            "source_types": source_type_counts,
            "scopes": scope_counts,
            "document_summaries": [
                {
                    "title": document.get("title"),
                    "source_type": document.get("source_type"),
                    "department_scope": document.get("department_scope"),
                    "canonical_url": document.get("canonical_url"),
                    "status": document.get("status"),
                }
                for document in data.get("documents", [])
            ],
        }


def get_default_repository() -> KnowledgeRepository:
    return KnowledgeRepository()


def search_knowledge(
    query: str,
    *,
    allowed_scopes: tuple[str, ...] | list[str],
    limit: int = 4,
) -> list[dict]:
    return get_default_repository().search(
        query,
        allowed_scopes=allowed_scopes,
        limit=limit,
    )
