# Knowledge RAG

The Enterprise AI Orchestrator uses a scoped knowledge repository so retrieved
context stays inside the authenticated user's allowed knowledge scopes.

## Source Types

Supported source types:

- `internal_document`: approved internal company documents.
- `official_web`: approved pages from the official Jamain Baco website.

Prepared future source type:

- `external_web`: reserved for a later milestone. General web search and
  arbitrary external crawling are not implemented.

Trust order when relevance is comparable:

`internal_document` -> `official_web` -> future `external_web`

## Official Website Ingestion

Administrators may ingest approved official company website pages as
`company_common` knowledge.

Flow:

Approved official website URL -> safe HTTP fetch -> domain validation -> HTML
extraction -> visible text cleaning -> same-domain link discovery -> page
normalization -> chunking -> local pilot embeddings -> knowledge repository.

Official website pages are stored with:

- `document_id`
- `title`
- `canonical_url`
- `source_type = official_web`
- `source_domain`
- `department_scope = company_common`
- `checksum`
- `ingested_at`
- `last_fetched_at`
- `status`

The repository does not expose local storage paths through API responses.

## Domain Allowlist And SSRF Protection

Allowed official domains:

- `jamainbaco.com`
- `www.jamainbaco.com`

The backend validates the submitted URL and every redirect target. It rejects:

- arbitrary external domains
- `localhost`
- `127.0.0.1`
- private, loopback, link-local, multicast, reserved, and unspecified IP ranges
- cloud metadata-style local targets
- `file://`, `ftp://`, `javascript:`, `mailto:`, `tel:`, and other unsupported schemes
- non-default HTTPS ports

Only HTTPS official website pages are fetched. JavaScript is not executed and no
headless browser is used.

## Crawl Limits

Official website discovery is bounded and same-domain only.

Default pilot limits:

- `max_pages = 20`
- `max_depth = 2`

Hard safety caps:

- `max_pages <= 50`
- `max_depth <= 3`

The crawler ignores URL fragments, query-parameter links, obvious binary assets,
and login/logout/admin paths. It never performs unlimited crawling.

## Refresh And Deduplication

Each official page is keyed by canonical URL, source type, and scope. The
repository computes a content checksum.

Refresh behavior:

- unchanged checksum: update `last_fetched_at`, mark `status = unchanged`, and
  do not duplicate chunks
- changed checksum: update metadata and replace chunks for the same document id

The pilot repository does not keep version history.

## Answer Grounding

Official website chunks participate in normal retrieval for users whose
knowledge scopes include `company_common`.

When official web context is used, the Knowledge Agent:

- answers in French
- uses only retrieved context
- treats retrieved page text as untrusted content, not system instructions
- returns safe source metadata such as source type, title, and official URL

The agent should identify official web context as a Jamain Baco official website
source when that helps the user understand the grounding.
