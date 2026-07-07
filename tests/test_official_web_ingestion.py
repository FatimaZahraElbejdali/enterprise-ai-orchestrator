import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from orchestrator.knowledge_repository import (
    SOURCE_TYPE_OFFICIAL_WEB,
    KnowledgeRepository,
)
from orchestrator.official_web_ingestion import (
    OfficialWebIngestionError,
    OfficialWebsiteIngestionService,
    canonicalize_url,
    extract_visible_text,
    validate_official_url,
)
from tests.auth_helpers import auth_headers


client = TestClient(app)


def html_page(title="Jamain Baco", body="", links=""):
    body = body or (
        "<h1>Jamain Baco</h1>"
        "<p>Jamain Baco est une entreprise officielle avec une histoire, "
        "des activités et des équipes présentées publiquement sur son site.</p>"
    )
    return (
        "<html><head>"
        f"<title>{title}</title>"
        "<style>.hidden { display: none; }</style>"
        "<script>window.secret = 'ignore me';</script>"
        "</head><body>"
        "<nav>Accueil Produits Contact</nav>"
        f"{links}{body}"
        "<footer>Accueil Produits Contact</footer>"
        "</body></html>"
    )


class FakeResponse:
    def __init__(
        self,
        body="",
        *,
        status_code=200,
        content_type="text/html; charset=utf-8",
        url="https://jamainbaco.com",
        headers=None,
    ):
        self.status_code = status_code
        self.url = url
        self.headers = {"Content-Type": content_type}
        self.headers.update(headers or {})
        self.encoding = "utf-8"
        self.content = body.encode("utf-8") if isinstance(body, str) else body

    def iter_content(self, chunk_size=8192):
        del chunk_size
        yield self.content


class FakeHttpClient:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []
        self.request_kwargs = []

    def get(self, url, **kwargs):
        self.requests.append(url)
        self.request_kwargs.append(kwargs)
        response = self.responses[url]

        if callable(response):
            return response(url)

        return response


def service_for(tmp_path, responses, **kwargs):
    repository = KnowledgeRepository(tmp_path / "knowledge_repository.json")
    return OfficialWebsiteIngestionService(
        repository=repository,
        http_client=FakeHttpClient(responses),
        **kwargs,
    )


def test_official_domain_variants_are_accepted():
    assert validate_official_url("https://jamainbaco.com") == "https://jamainbaco.com/"
    assert validate_official_url("https://www.jamainbaco.com/a-propos#top") == (
        "https://jamainbaco.com/a-propos"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://localhost",
        "https://127.0.0.1",
        "https://10.0.0.5",
        "https://172.16.0.5",
        "https://192.168.1.1",
        "https://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
        "ftp://jamainbaco.com/file",
        "http://jamainbaco.com",
    ],
)
def test_forbidden_urls_are_rejected(url):
    with pytest.raises(OfficialWebIngestionError):
        validate_official_url(url)


def test_redirect_to_forbidden_domain_is_rejected(tmp_path):
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/": FakeResponse(
                "",
                status_code=302,
                headers={"Location": "https://example.com"},
            ),
        },
    )

    with pytest.raises(OfficialWebIngestionError):
        service.fetch_page("https://jamainbaco.com")


@pytest.mark.parametrize(
    "location",
    [
        "https://localhost/admin",
        "https://127.0.0.1/private",
        "https://10.0.0.9",
        "https://169.254.169.254/latest/meta-data",
    ],
)
def test_redirect_to_private_or_local_target_is_rejected(tmp_path, location):
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/": FakeResponse(
                "",
                status_code=302,
                headers={"Location": location},
            ),
        },
    )

    with pytest.raises(OfficialWebIngestionError):
        service.fetch_page("https://jamainbaco.com")


def test_legitimate_same_domain_redirect_is_accepted(tmp_path):
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/ancienne-page": FakeResponse(
                "",
                status_code=301,
                headers={"Location": "https://jamainbaco.com/nouvelle-page/"},
            ),
            "https://jamainbaco.com/nouvelle-page/": FakeResponse(
                html_page(title="Nouvelle page"),
            ),
        },
    )

    page = service.fetch_page("https://jamainbaco.com/ancienne-page")

    assert page.canonical_url == "https://jamainbaco.com/nouvelle-page/"
    assert service.http_client.requests == [
        "https://jamainbaco.com/ancienne-page",
        "https://jamainbaco.com/nouvelle-page/",
    ]


def test_www_redirect_to_non_www_is_accepted(tmp_path):
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/page-www/": FakeResponse(
                html_page(title="Page officielle"),
            ),
        },
    )

    page = service.fetch_page("https://www.jamainbaco.com/page-www/")

    assert page.canonical_url == "https://jamainbaco.com/page-www/"
    assert service.http_client.requests == ["https://jamainbaco.com/page-www/"]


def test_non_www_redirect_to_www_is_accepted_and_canonicalized(tmp_path):
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/page": FakeResponse(
                "",
                status_code=301,
                headers={"Location": "https://www.jamainbaco.com/page/"},
            ),
            "https://jamainbaco.com/page/": FakeResponse(
                html_page(title="Page canonique"),
            ),
        },
    )

    page = service.fetch_page("https://jamainbaco.com/page")

    assert page.canonical_url == "https://jamainbaco.com/page/"
    assert service.http_client.requests == [
        "https://jamainbaco.com/page",
        "https://jamainbaco.com/page/",
    ]


def test_repeated_normalized_redirect_url_is_detected_as_loop(tmp_path):
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/boucle/": FakeResponse(
                "",
                status_code=301,
                headers={"Location": "https://www.jamainbaco.com/boucle/"},
            ),
        },
    )

    with pytest.raises(OfficialWebIngestionError, match="Redirect loop detected"):
        service.fetch_page("https://jamainbaco.com/boucle/")


def test_redirect_maximum_is_enforced(tmp_path):
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/a": FakeResponse(
                "",
                status_code=302,
                headers={"Location": "https://jamainbaco.com/b"},
            ),
            "https://jamainbaco.com/b": FakeResponse(
                "",
                status_code=302,
                headers={"Location": "https://jamainbaco.com/c"},
            ),
        },
    )

    with pytest.raises(OfficialWebIngestionError, match="Too many redirects"):
        service.fetch_page("https://jamainbaco.com/a", redirect_limit=1)


def test_http_client_does_not_auto_follow_redirects(tmp_path):
    service = service_for(
        tmp_path,
        {"https://jamainbaco.com/": FakeResponse(html_page(title="Accueil"))},
    )

    service.fetch_page("https://jamainbaco.com")

    assert service.http_client.request_kwargs[0]["allow_redirects"] is False


def test_oversized_response_is_rejected(tmp_path):
    service = service_for(
        tmp_path,
        {"https://jamainbaco.com/": FakeResponse("x" * 200)},
        max_response_bytes=100,
    )

    with pytest.raises(OfficialWebIngestionError):
        service.fetch_page("https://jamainbaco.com")


def test_unsupported_content_type_is_rejected(tmp_path):
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/": FakeResponse(
                b"%PDF-1.7",
                content_type="application/pdf",
            ),
        },
    )

    with pytest.raises(OfficialWebIngestionError):
        service.fetch_page("https://jamainbaco.com")


def test_html_extraction_keeps_title_headings_paragraphs_and_ignores_noise():
    title, text, links = extract_visible_text(
        html_page(
            title="Histoire du groupe",
            links="<a href='/histoire'>Histoire</a>",
            body=(
                "<h1>Histoire du groupe</h1>"
                "<p>Jamain Baco présente son histoire officielle.</p>"
                "<p>Jamain Baco présente son histoire officielle.</p>"
                "<script>Ignore script text</script>"
                "<style>Ignore style text</style>"
            ),
        )
    )

    assert title == "Histoire du groupe"
    assert "Histoire du groupe" in text
    assert text.count("Jamain Baco présente son histoire officielle.") == 1
    assert "Ignore script text" not in text
    assert "Ignore style text" not in text
    assert "/histoire" in links


def test_canonical_url_normalization_ignores_fragments_and_trailing_slashes():
    assert canonicalize_url("https://www.jamainbaco.com/a-propos/#team") == (
        "https://jamainbaco.com/a-propos/"
    )

    assert canonicalize_url("https://JAMAINBACO.com/a//b///#top") == (
        "https://jamainbaco.com/a/b/"
    )


def test_crawl_remains_same_domain_and_ignores_bad_links(tmp_path):
    home = html_page(
        links=(
            "<a href='/histoire'>Histoire</a>"
            "<a href='https://example.com/out'>External</a>"
            "<a href='mailto:contact@jamainbaco.com'>Mail</a>"
            "<a href='/brochure.pdf'>PDF</a>"
            "<a href='/search?q=x'>Query</a>"
        )
    )
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/": FakeResponse(home, url="https://jamainbaco.com/"),
            "https://jamainbaco.com/histoire": FakeResponse(
                html_page(title="Histoire"),
                url="https://jamainbaco.com/histoire",
            ),
        },
    )

    result = service.ingest(url="https://jamainbaco.com", max_pages=20, max_depth=2)

    assert result["pages_discovered"] == 2
    assert result["pages_fetched"] == 2
    assert service.http_client.requests == [
        "https://jamainbaco.com/",
        "https://jamainbaco.com/histoire",
    ]


def test_crawler_ingests_multiple_linked_same_domain_pages(tmp_path):
    home = html_page(
        links=(
            "<a href='/histoire/'>Histoire</a>"
            "<a href='/activites/'>Activités</a>"
        )
    )
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/": FakeResponse(home),
            "https://jamainbaco.com/histoire/": FakeResponse(
                html_page(title="Histoire du groupe"),
            ),
            "https://jamainbaco.com/activites/": FakeResponse(
                html_page(title="Activités"),
            ),
        },
    )

    result = service.ingest(url="https://jamainbaco.com", max_pages=10, max_depth=1)
    titles = {document["title"] for document in result["documents"]}

    assert result["pages_discovered"] == 3
    assert result["pages_ingested"] == 3
    assert {"Jamain Baco", "Histoire du groupe", "Activités"} <= titles


def test_canonical_host_variants_are_deduplicated_during_crawl(tmp_path):
    home = html_page(
        links=(
            "<a href='https://jamainbaco.com/histoire/'>Histoire</a>"
            "<a href='https://www.jamainbaco.com/histoire/'>Histoire www</a>"
        )
    )
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/": FakeResponse(home),
            "https://jamainbaco.com/histoire/": FakeResponse(
                html_page(title="Histoire du groupe"),
            ),
        },
    )

    result = service.ingest(url="https://www.jamainbaco.com", max_pages=10, max_depth=1)

    assert result["pages_discovered"] == 2
    assert service.http_client.requests == [
        "https://jamainbaco.com/",
        "https://jamainbaco.com/histoire/",
    ]


def test_redirected_final_canonical_url_is_stored_once(tmp_path):
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/ancienne": FakeResponse(
                "",
                status_code=301,
                headers={"Location": "https://jamainbaco.com/nouvelle/"},
            ),
            "https://jamainbaco.com/nouvelle/": FakeResponse(
                html_page(title="Nouvelle page"),
            ),
        },
    )

    first = service.ingest(url="https://jamainbaco.com/ancienne", crawl=False)
    second = service.ingest(url="https://www.jamainbaco.com/nouvelle/", crawl=False)
    stats = service.repository.stats()

    assert first["pages_ingested"] == 1
    assert second["pages_unchanged"] == 1
    assert stats["documents"] == 1
    assert stats["document_summaries"][0]["canonical_url"] == "https://jamainbaco.com/nouvelle/"


def test_max_pages_is_enforced(tmp_path):
    home = html_page(
        links=(
            "<a href='/one'>One</a>"
            "<a href='/two'>Two</a>"
            "<a href='/three'>Three</a>"
        )
    )
    responses = {
        "https://jamainbaco.com/": FakeResponse(home),
        "https://jamainbaco.com/one": FakeResponse(html_page(title="One")),
        "https://jamainbaco.com/two": FakeResponse(html_page(title="Two")),
    }
    service = service_for(tmp_path, responses)

    result = service.ingest(url="https://jamainbaco.com", max_pages=2, max_depth=2)

    assert result["pages_discovered"] == 2
    assert result["pages_fetched"] == 2
    assert "https://jamainbaco.com/three" not in service.http_client.requests


def test_max_depth_is_enforced(tmp_path):
    home = html_page(links="<a href='/level-one'>One</a>")
    level_one = html_page(links="<a href='/level-two'>Two</a>")
    service = service_for(
        tmp_path,
        {
            "https://jamainbaco.com/": FakeResponse(home),
            "https://jamainbaco.com/level-one": FakeResponse(level_one),
            "https://jamainbaco.com/level-two": FakeResponse(html_page(title="Two")),
        },
    )

    result = service.ingest(url="https://jamainbaco.com", max_pages=20, max_depth=1)

    assert result["pages_fetched"] == 2
    assert "https://jamainbaco.com/level-two" not in service.http_client.requests


def test_duplicate_page_checksum_is_unchanged(tmp_path):
    page = html_page(title="Accueil")
    service = service_for(
        tmp_path,
        {"https://jamainbaco.com/": FakeResponse(page)},
    )

    first = service.ingest(url="https://jamainbaco.com", crawl=False)
    second = service.ingest(url="https://jamainbaco.com", crawl=False)

    assert first["pages_ingested"] == 1
    assert second["pages_unchanged"] == 1
    assert second["pages_ingested"] == 0


def test_changed_page_refresh_replaces_chunks(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge_repository.json")
    first = repository.upsert_document(
        title="Accueil",
        canonical_url="https://jamainbaco.com/",
        text="Jamain Baco ancien contenu officiel avec suffisamment de texte public.",
        source_type=SOURCE_TYPE_OFFICIAL_WEB,
        source_domain="jamainbaco.com",
        department_scope="company_common",
    )
    second = repository.upsert_document(
        title="Accueil",
        canonical_url="https://jamainbaco.com/",
        text="Jamain Baco nouveau contenu officiel avec suffisamment de texte public.",
        source_type=SOURCE_TYPE_OFFICIAL_WEB,
        source_domain="jamainbaco.com",
        department_scope="company_common",
    )
    data = repository.load()
    chunks = [
        chunk
        for chunk in data["chunks"]
        if chunk["document_id"] == first["document"]["document_id"]
    ]

    assert second["status"] == "updated"
    assert len(chunks) == second["chunks_indexed"]
    assert all("ancien contenu" not in chunk["text"] for chunk in chunks)


def test_official_web_metadata_and_company_common_scope_are_stored(tmp_path):
    service = service_for(
        tmp_path,
        {"https://jamainbaco.com/": FakeResponse(html_page(title="Accueil"))},
    )

    result = service.ingest(url="https://jamainbaco.com", crawl=False)
    document = result["documents"][0]

    assert document["source_type"] == "official_web"
    assert document["source_domain"] == "jamainbaco.com"
    assert document["department_scope"] == "company_common"
    assert document["canonical_url"] == "https://jamainbaco.com/"
    assert document["checksum"]
    assert document["ingested_at"]
    assert document["last_fetched_at"]
    assert "path" not in document


def test_repository_persists_documents_chunks_and_retrieval_after_reload(tmp_path):
    repository_path = tmp_path / "knowledge" / "repository.json"
    first_repository = KnowledgeRepository(repository_path)
    first_repository.upsert_document(
        title="Histoire du groupe Jamain Baco",
        canonical_url="https://jamainbaco.com/histoire",
        text=(
            "L'histoire du groupe Jamain Baco est présentée sur le site officiel. "
            "Le groupe Jamain Baco décrit son évolution et ses activités."
        ),
        source_type=SOURCE_TYPE_OFFICIAL_WEB,
        source_domain="jamainbaco.com",
        department_scope="company_common",
    )

    reloaded_repository = KnowledgeRepository(repository_path)
    stats = reloaded_repository.stats()
    results = reloaded_repository.search(
        "histoire du groupe Jamain Baco",
        allowed_scopes=("company_common",),
    )

    assert stats["documents"] == 1
    assert stats["chunks"] == 1
    assert stats["source_types"] == {"official_web": 1}
    assert results
    assert results[0]["title"] == "Histoire du groupe Jamain Baco"


def test_retrieval_accepts_relevant_history_and_rejects_unrelated_context(tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge_repository.json")
    repository.upsert_document(
        title="Histoire du groupe",
        canonical_url="https://jamainbaco.com/histoire",
        text="Histoire officielle du groupe Jamain Baco et évolution de ses activités.",
        source_type=SOURCE_TYPE_OFFICIAL_WEB,
        source_domain="jamainbaco.com",
        department_scope="company_common",
    )
    repository.upsert_document(
        title="Contexte sans sujet demandé",
        canonical_url="https://jamainbaco.com/autre",
        text="Jamain Baco présente une page de contact sans détail sur le sujet demandé.",
        source_type=SOURCE_TYPE_OFFICIAL_WEB,
        source_domain="jamainbaco.com",
        department_scope="company_common",
    )

    relevant = repository.search(
        "histoire du groupe Jamain Baco",
        allowed_scopes=("company_common",),
    )
    unrelated = repository.search(
        "directeur financier Jamain Baco",
        allowed_scopes=("company_common",),
    )

    assert relevant
    assert relevant[0]["title"] == "Histoire du groupe"
    assert unrelated == []


def test_official_web_ingestion_endpoint_requires_admin_permission():
    response = client.post(
        "/knowledge/web/ingest",
        json={"url": "https://jamainbaco.com"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 403


def test_official_web_ingestion_endpoint_returns_safe_counts(monkeypatch):
    class FakeIngestionService:
        def ingest(self, **kwargs):
            assert kwargs["scope"] == "company_common"
            return {
                "status": "completed",
                "source_type": "official_web",
                "scope": "company_common",
                "pages_discovered": 1,
                "pages_fetched": 1,
                "pages_ingested": 1,
                "pages_unchanged": 0,
                "pages_failed": 0,
                "documents": [
                    {
                        "document_id": "doc_1",
                        "title": "Accueil",
                        "canonical_url": "https://jamainbaco.com/",
                        "source_type": "official_web",
                        "source_domain": "jamainbaco.com",
                        "department_scope": "company_common",
                        "checksum": "abc",
                        "ingested_at": "2026-01-01T00:00:00+00:00",
                        "last_fetched_at": "2026-01-01T00:00:00+00:00",
                        "status": "indexed",
                    }
                ],
            }

    monkeypatch.setattr(
        app_module,
        "OfficialWebsiteIngestionService",
        lambda: FakeIngestionService(),
    )

    response = client.post(
        "/knowledge/web/ingest",
        json={"url": "https://jamainbaco.com", "scope": "company_common"},
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["source_type"] == "official_web"
    assert data["pages_ingested"] == 1
    assert "content" not in data


def test_api_ingestion_then_chat_retrieval_uses_same_repository_backend(monkeypatch, tmp_path):
    repository = KnowledgeRepository(tmp_path / "knowledge_repository.json")

    class FakeIngestionService:
        def ingest(self, **kwargs):
            repository.upsert_document(
                title="Histoire du groupe Jamain Baco",
                canonical_url="https://jamainbaco.com/histoire",
                text=(
                    "Histoire officielle du groupe Jamain Baco. "
                    "Le groupe Jamain Baco présente son évolution sur son site officiel."
                ),
                source_type=SOURCE_TYPE_OFFICIAL_WEB,
                source_domain="jamainbaco.com",
                department_scope=kwargs["scope"],
            )
            return {
                "status": "completed",
                "source_type": "official_web",
                "scope": kwargs["scope"],
                "pages_discovered": 1,
                "pages_fetched": 1,
                "pages_ingested": 1,
                "pages_unchanged": 0,
                "pages_failed": 0,
                "documents": repository.stats()["document_summaries"],
            }

    monkeypatch.setattr(
        app_module,
        "OfficialWebsiteIngestionService",
        lambda: FakeIngestionService(),
    )
    monkeypatch.setattr(
        "agents.knowledge_agent.search_knowledge",
        lambda query, allowed_scopes, limit=4: repository.search(
            query,
            allowed_scopes=allowed_scopes,
            limit=limit,
        ),
    )

    ingest_response = client.post(
        "/knowledge/web/ingest",
        json={"url": "https://jamainbaco.com", "scope": "company_common"},
        headers=auth_headers("admin@company.local"),
    )
    chat_response = client.post(
        "/chat",
        json={"message": "c quoi l'histoire du groupe jamain baco"},
        headers=auth_headers("employee@company.local"),
    )

    assert ingest_response.status_code == 200
    assert chat_response.status_code == 200
    data = chat_response.json()
    assert data["technical"]["tool_used"] == "knowledge_rag_retrieval"
    assert data["sources"][0]["source_type"] == "official_web"
    assert data["sources"][0]["title"] == "Histoire du groupe Jamain Baco"
