import ipaddress
import re
from collections import Counter, deque
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from requests import RequestException

from orchestrator.knowledge_repository import (
    SOURCE_TYPE_OFFICIAL_WEB,
    KnowledgeRepository,
)


ALLOWED_OFFICIAL_DOMAINS = {
    "jamainbaco.com",
    "www.jamainbaco.com",
}
PRIMARY_OFFICIAL_DOMAIN = "jamainbaco.com"

FORBIDDEN_HOSTS = {
    "localhost",
    "metadata.google.internal",
}

FORBIDDEN_PATH_PARTS = {
    "admin",
    "login",
    "logout",
    "wp-admin",
}

BINARY_EXTENSIONS = {
    ".7z",
    ".avi",
    ".css",
    ".doc",
    ".docx",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".svg",
    ".tar",
    ".webm",
    ".xls",
    ".xlsx",
    ".zip",
}

DEFAULT_TIMEOUT_SECONDS = 8
DEFAULT_MAX_RESPONSE_BYTES = 1_000_000
DEFAULT_MAX_PAGES = 20
DEFAULT_MAX_DEPTH = 2
DEFAULT_REDIRECT_LIMIT = 5
MAX_ALLOWED_PAGES = 50
MAX_ALLOWED_DEPTH = 3
MIN_TEXT_LENGTH = 80


class OfficialWebIngestionError(ValueError):
    pass


@dataclass
class FetchedPage:
    canonical_url: str
    title: str
    text: str
    links: list[str]
    source_domain: str


def _host_is_private_or_forbidden(host: str) -> bool:
    normalized = (host or "").strip().lower().rstrip(".")

    if not normalized or normalized in FORBIDDEN_HOSTS:
        return True

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False

    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_official_url(url: str) -> str:
    parsed = urlparse((url or "").strip())

    if parsed.scheme != "https":
        raise OfficialWebIngestionError("Only HTTPS official website URLs are allowed.")

    if parsed.username or parsed.password:
        raise OfficialWebIngestionError("URL credentials are not allowed.")

    host = (parsed.hostname or "").lower().rstrip(".")

    if _host_is_private_or_forbidden(host):
        raise OfficialWebIngestionError("Forbidden private or local target.")

    if host not in ALLOWED_OFFICIAL_DOMAINS:
        raise OfficialWebIngestionError("Domain is not in the official website allowlist.")

    if parsed.port not in {None, 443}:
        raise OfficialWebIngestionError("Only the default HTTPS port is allowed.")

    return canonicalize_url(url)


def canonicalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    scheme = "https"
    host = (parsed.hostname or "").lower().rstrip(".")
    if host in ALLOWED_OFFICIAL_DOMAINS:
        host = PRIMARY_OFFICIAL_DOMAIN

    path = parsed.path or "/"
    path = re.sub(r"/{2,}", "/", path)

    netloc = host
    if parsed.port and parsed.port != 443:
        netloc = f"{host}:{parsed.port}"

    return urlunparse((scheme, netloc, path, "", "", ""))


def _looks_like_binary_asset(path: str) -> bool:
    normalized = (path or "").lower()
    return any(normalized.endswith(extension) for extension in BINARY_EXTENSIONS)


def normalize_crawl_link(base_url: str, href: str | None) -> str | None:
    href = (href or "").strip()

    if not href:
        return None

    lowered = href.lower()

    if lowered.startswith(("mailto:", "tel:", "javascript:")):
        return None

    candidate = urljoin(base_url, href)
    parsed = urlparse(candidate)

    if parsed.query:
        return None

    if _looks_like_binary_asset(parsed.path):
        return None

    path_parts = {
        part.lower()
        for part in parsed.path.split("/")
        if part
    }

    if path_parts & FORBIDDEN_PATH_PARTS:
        return None

    try:
        return validate_official_url(candidate)
    except OfficialWebIngestionError:
        return None


class VisibleHtmlExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._current_tag = ""
        self._text_blocks = []
        self._links = []
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self._current_tag = tag

        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}:
            self._skip_depth += 1

        if tag == "title":
            self._in_title = True

        if tag == "a":
            href = dict(attrs).get("href")

            if href:
                self._links.append(href)

        if tag in {"h1", "h2", "h3", "h4", "p", "li", "section", "article", "br"}:
            self._flush_text()

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in {"h1", "h2", "h3", "h4", "p", "li", "section", "article", "br"}:
            self._flush_text()

        if tag == "title":
            self._in_title = False

        if tag in {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}:
            self._skip_depth = max(0, self._skip_depth - 1)

        self._current_tag = ""

    def handle_data(self, data):
        text = re.sub(r"\s+", " ", data or "").strip()

        if not text:
            return

        if self._in_title:
            self.title = f"{self.title} {text}".strip()
            return

        if self._skip_depth:
            return

        self._current_text.append(text)

    def _flush_text(self):
        if not self._current_text:
            return

        block = re.sub(r"\s+", " ", " ".join(self._current_text)).strip()
        self._current_text = []

        if block:
            self._text_blocks.append(block)

    def result(self) -> tuple[str, str, list[str]]:
        self._flush_text()
        counts = Counter(self._text_blocks)
        deduped_blocks = []
        seen = set()

        for block in self._text_blocks:
            if counts[block] > 1 and block in seen:
                continue

            seen.add(block)
            deduped_blocks.append(block)

        return (
            self.title.strip(),
            "\n\n".join(deduped_blocks).strip(),
            list(self._links),
        )


def extract_visible_text(html: str) -> tuple[str, str, list[str]]:
    extractor = VisibleHtmlExtractor()
    extractor.feed(html or "")
    return extractor.result()


class OfficialWebsiteIngestionService:
    def __init__(
        self,
        *,
        repository: KnowledgeRepository | None = None,
        http_client=None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ):
        self.repository = repository or KnowledgeRepository()
        self.http_client = http_client or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    def fetch_page(self, url: str, redirect_limit: int = DEFAULT_REDIRECT_LIMIT) -> FetchedPage:
        current_url = validate_official_url(url)
        redirect_chain = {current_url}

        for redirect_count in range(redirect_limit + 1):
            try:
                response = self.http_client.get(
                    current_url,
                    allow_redirects=False,
                    stream=True,
                    timeout=self.timeout_seconds,
                    headers={"User-Agent": "EnterpriseAIOrchestrator/official-web-ingest"},
                )
            except RequestException as error:
                raise OfficialWebIngestionError("Official website page could not be fetched.") from error

            status_code = getattr(response, "status_code", 200)

            if 300 <= status_code < 400:
                if redirect_count >= redirect_limit:
                    raise OfficialWebIngestionError("Too many redirects while fetching official website page.")

                location = response.headers.get("Location") if hasattr(response, "headers") else None

                if not location:
                    raise OfficialWebIngestionError("Redirect response did not include a Location header.")

                next_url = validate_official_url(urljoin(current_url, location))

                if next_url in redirect_chain:
                    raise OfficialWebIngestionError("Redirect loop detected while fetching official website page.")

                redirect_chain.add(next_url)
                current_url = next_url
                continue

            if status_code >= 400:
                raise OfficialWebIngestionError(f"Official website returned HTTP {status_code}.")

            content_type = (response.headers.get("Content-Type", "") if hasattr(response, "headers") else "").lower()

            if not (
                "text/html" in content_type
                or "text/plain" in content_type
                or content_type == ""
            ):
                raise OfficialWebIngestionError("Unsupported content type for official website ingestion.")

            body = self._read_limited_response(response)
            encoding = getattr(response, "encoding", None) or "utf-8"
            decoded = body.decode(encoding, errors="replace")
            canonical_url = canonicalize_url(current_url)

            if "text/plain" in content_type:
                title = canonical_url
                text = re.sub(r"\s+", " ", decoded).strip()
                links = []
            else:
                title, text, raw_links = extract_visible_text(decoded)
                links = [
                    link
                    for link in (
                        normalize_crawl_link(canonical_url, raw_link)
                        for raw_link in raw_links
                    )
                    if link
                ]

            if len(text) < MIN_TEXT_LENGTH:
                raise OfficialWebIngestionError("Official website page does not contain enough visible text.")

            host = urlparse(canonical_url).hostname or ""

            return FetchedPage(
                canonical_url=canonical_url,
                title=title or canonical_url,
                text=text,
                links=links,
                source_domain=host.lower(),
            )

        raise OfficialWebIngestionError("Too many redirects while fetching official website page.")

    def _read_limited_response(self, response) -> bytes:
        chunks = []
        total = 0

        if hasattr(response, "iter_content"):
            iterator = response.iter_content(chunk_size=8192)
        else:
            iterator = [getattr(response, "content", b"")]

        for chunk in iterator:
            if not chunk:
                continue

            total += len(chunk)

            if total > self.max_response_bytes:
                raise OfficialWebIngestionError("Official website response exceeded the maximum allowed size.")

            chunks.append(chunk)

        return b"".join(chunks)

    def ingest(
        self,
        *,
        url: str,
        scope: str = "company_common",
        crawl: bool = True,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_depth: int = DEFAULT_MAX_DEPTH,
    ) -> dict:
        if scope != "company_common":
            raise OfficialWebIngestionError("Official website pages may only be ingested as company_common knowledge.")

        if max_pages < 1 or max_pages > MAX_ALLOWED_PAGES:
            raise OfficialWebIngestionError(f"max_pages must be between 1 and {MAX_ALLOWED_PAGES}.")

        if max_depth < 0 or max_depth > MAX_ALLOWED_DEPTH:
            raise OfficialWebIngestionError(f"max_depth must be between 0 and {MAX_ALLOWED_DEPTH}.")

        start_url = validate_official_url(url)
        queue = deque([(start_url, 0)])
        queued = {start_url}
        fetched = set()
        pages_ingested = 0
        pages_unchanged = 0
        failures = []
        documents = []

        while queue and len(fetched) < max_pages:
            current_url, depth = queue.popleft()

            if current_url in fetched:
                continue

            fetched.add(current_url)

            try:
                page = self.fetch_page(current_url)
                result = self.repository.upsert_document(
                    title=page.title,
                    canonical_url=page.canonical_url,
                    text=page.text,
                    source_type=SOURCE_TYPE_OFFICIAL_WEB,
                    source_domain=page.source_domain,
                    department_scope=scope,
                )
                documents.append(result["document"])

                if result["status"] == "unchanged":
                    pages_unchanged += 1
                else:
                    pages_ingested += 1

                if crawl and depth < max_depth:
                    for link in page.links:
                        if link in queued or link in fetched:
                            continue

                        if len(queued) >= max_pages:
                            break

                        queued.add(link)
                        queue.append((link, depth + 1))

            except OfficialWebIngestionError as error:
                failures.append({
                    "url": current_url,
                    "error": str(error),
                })

        return {
            "status": "completed",
            "source_type": SOURCE_TYPE_OFFICIAL_WEB,
            "scope": scope,
            "pages_discovered": len(queued),
            "pages_fetched": len(fetched),
            "pages_ingested": pages_ingested,
            "pages_unchanged": pages_unchanged,
            "pages_failed": len(failures),
            "failures": failures,
            "documents": [
                {
                    "document_id": document.get("document_id"),
                    "title": document.get("title"),
                    "canonical_url": document.get("canonical_url"),
                    "source_type": document.get("source_type"),
                    "source_domain": document.get("source_domain"),
                    "department_scope": document.get("department_scope"),
                    "checksum": document.get("checksum"),
                    "ingested_at": document.get("ingested_at"),
                    "last_fetched_at": document.get("last_fetched_at"),
                    "status": document.get("status"),
                }
                for document in documents
            ],
        }


def ingest_official_website(**kwargs) -> dict:
    return OfficialWebsiteIngestionService().ingest(**kwargs)
