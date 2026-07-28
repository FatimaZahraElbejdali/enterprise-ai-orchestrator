from pathlib import Path
import re


FRONTEND_ROOT = Path("frontend")


def _read_frontend_file(path: str) -> str:
    return (FRONTEND_ROOT / path).read_text(encoding="utf-8")


def test_frontend_never_clears_all_local_storage():
    for path in (FRONTEND_ROOT / "app").rglob("*"):
        if path.is_file() and path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            assert "localStorage.clear(" not in path.read_text(encoding="utf-8")

    for path in (FRONTEND_ROOT / "lib").rglob("*"):
        if path.is_file() and path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
            assert "localStorage.clear(" not in path.read_text(encoding="utf-8")


def test_logout_removes_auth_storage_without_removing_chat_history():
    api_source = _read_frontend_file("lib/api.ts")

    clear_auth_body = re.search(
        r"export function clearAuth\(\) \{(?P<body>.*?)\n\}",
        api_source,
        flags=re.S,
    )

    assert clear_auth_body is not None
    body = clear_auth_body.group("body")
    assert 'removeItem("auth_token")' in body
    assert 'removeItem("auth_user")' in body
    assert "CHAT_HISTORY" not in body
    assert "chat_history" not in body


def test_chat_page_persists_history_independently_from_auth_token():
    api_source = _read_frontend_file("lib/api.ts")
    chat_source = _read_frontend_file("app/chat/page.tsx")

    assert "orchestrator_chat_history" in api_source
    assert "getChatHistoryStorageKey" in api_source
    assert "loadStoredChatHistory" in chat_source
    assert "saveStoredChatHistory" in chat_source
    assert "auth_token" not in re.search(
        r"getChatHistoryStorageKey.*?\n\}",
        api_source,
        flags=re.S,
    ).group(0)


def test_chat_history_storage_sanitizes_transient_loading_messages():
    api_source = _read_frontend_file("lib/api.ts")

    assert "sanitizeStoredChatHistory" in api_source
    assert ".loading !== true" in api_source
    assert "saveStoredChatHistory(sanitized, user)" in api_source


def test_new_conversation_clears_only_current_chat_history():
    api_source = _read_frontend_file("lib/api.ts")
    chat_source = _read_frontend_file("app/chat/page.tsx")

    clear_history_body = re.search(
        r"export function clearStoredChatHistory.*?\{(?P<body>.*?)\n\}",
        api_source,
        flags=re.S,
    )
    assert clear_history_body is not None
    assert "removeItem(getChatHistoryStorageKey(user))" in clear_history_body.group("body")
    assert "auth_token" not in clear_history_body.group("body")
    assert "auth_user" not in clear_history_body.group("body")

    assert "Nouvelle conversation" in chat_source
    assert "window.confirm" in chat_source
    assert "clearStoredChatHistory(currentUser)" in chat_source


def test_chat_request_has_abort_controller_and_timeout():
    chat_source = _read_frontend_file("app/chat/page.tsx")
    api_source = _read_frontend_file("lib/api.ts")

    assert "CHAT_REQUEST_TIMEOUT_MS" in chat_source
    assert "AbortController" in chat_source
    assert "controller.abort()" in chat_source
    assert "CHAT_TIMEOUT_MESSAGE" in chat_source
    assert "La réponse a pris trop de temps. Veuillez réessayer." in chat_source
    assert "signal?: AbortSignal" in api_source
    assert "signal," in api_source


def test_chat_requests_use_central_auth_headers_and_401_only_session_expiry():
    api_source = _read_frontend_file("lib/api.ts")

    assert "export function authHeaders()" in api_source
    assert "const headers = new Headers(authHeaders())" in api_source
    assert "postChatMessage" in api_source
    assert "`${API_BASE_URL}/chat`" in api_source
    assert "if (response.status === 401)" in api_source
    assert "readApiErrorDetail(response)" in api_source
    assert "isAuthSessionError(detail)" in api_source
    assert "handleSessionExpired(options)" in api_source
    assert "if (response.status === 403)" in api_source


def test_cancel_button_stops_active_request_without_disabling_textarea():
    chat_source = _read_frontend_file("app/chat/page.tsx")

    assert "Arrêter" in chat_source
    assert "cancelActiveRequest" in chat_source
    assert "manualAbortRef.current = true" in chat_source
    assert "Demande annulée. Vous pouvez réessayer." in chat_source


def test_chat_textarea_remains_editable_while_loading():
    chat_source = _read_frontend_file("app/chat/page.tsx")
    textarea_block = re.search(r"<textarea(?P<body>.*?)\n\s*/>", chat_source, flags=re.S)
    send_button_block = re.search(
        r"<button\s+aria-label=\"Envoyer le message\"(?P<body>.*?)>",
        chat_source,
        flags=re.S,
    )

    assert textarea_block is not None
    assert "disabled=" not in textarea_block.group("body")
    assert send_button_block is not None
    assert "disabled={loading || !message.trim()}" in send_button_block.group("body")
