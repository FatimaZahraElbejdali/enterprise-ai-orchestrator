import json

from fastapi.testclient import TestClient

import app as app_module
from app import app
from tests.auth_helpers import auth_headers


client = TestClient(app)


def _write_audit_log(path, entries):
    path.write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries),
        encoding="utf-8",
    )


def test_logs_default_to_important_events(monkeypatch, tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(app_module, "AUDIT_LOG_PATH", log_path)
    _write_audit_log(
        log_path,
        [
            {
                "id": "normal-chat",
                "timestamp": "2026-07-27T10:00:00+00:00",
                "event_type": "knowledge_request",
                "title": "Knowledge response generated",
                "status": "completed",
                "risk": "low",
                "approval_status": "not_required",
            },
            {
                "id": "low-risk-read",
                "timestamp": "2026-07-27T10:01:00+00:00",
                "event_type": "odoo_read",
                "title": "Lecture Odoo",
                "system": "odoo",
                "status": "completed",
                "risk": "low",
                "approval_status": "not_required",
            },
            {
                "id": "successful-ingestion",
                "timestamp": "2026-07-27T10:01:30+00:00",
                "event_type": "official_web_ingestion",
                "title": "Ingestion site officiel Jamain Baco",
                "status": "completed",
                "risk": "low",
                "approval_status": "not_required",
            },
            {
                "id": "approval-required",
                "timestamp": "2026-07-27T10:02:00+00:00",
                "event_type": "approval_required",
                "title": "Validation requise",
                "status": "pending_approval",
                "risk": "medium",
                "approval_status": "pending",
            },
            {
                "id": "access-denied",
                "timestamp": "2026-07-27T10:03:00+00:00",
                "event_type": "permission_denied",
                "title": "Accès refusé",
                "status": "denied",
                "risk": "low",
                "approval_status": "not_required",
            },
        ],
    )

    response = client.get("/logs", headers=auth_headers("admin@company.local"))

    assert response.status_code == 200
    ids = [entry["id"] for entry in response.json()]
    assert ids == ["access-denied", "approval-required"]


def test_logs_can_show_all_events(monkeypatch, tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(app_module, "AUDIT_LOG_PATH", log_path)
    _write_audit_log(
        log_path,
        [
            {
                "id": "normal-chat",
                "timestamp": "2026-07-27T10:00:00+00:00",
                "event_type": "knowledge_request",
                "status": "completed",
                "risk": "low",
                "approval_status": "not_required",
            },
            {
                "id": "unsupported",
                "timestamp": "2026-07-27T10:01:00+00:00",
                "event_type": "unsupported_action",
                "status": "unsupported",
                "risk": "low",
                "approval_status": "not_required",
            },
        ],
    )

    response = client.get(
        "/logs?view=all",
        headers=auth_headers("admin@company.local"),
    )

    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()] == ["unsupported", "normal-chat"]


def test_failed_odoo_reads_remain_important(monkeypatch, tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(app_module, "AUDIT_LOG_PATH", log_path)
    _write_audit_log(
        log_path,
        [
            {
                "id": "failed-odoo",
                "timestamp": "2026-07-27T10:00:00+00:00",
                "event_type": "odoo_read",
                "system": "odoo",
                "status": "failed",
                "risk": "low",
                "approval_status": "not_required",
            },
        ],
    )

    response = client.get("/logs", headers=auth_headers("admin@company.local"))

    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()] == ["failed-odoo"]


def test_failed_official_web_ingestion_remains_important(monkeypatch, tmp_path):
    log_path = tmp_path / "audit_log.jsonl"
    monkeypatch.setattr(app_module, "AUDIT_LOG_PATH", log_path)
    _write_audit_log(
        log_path,
        [
            {
                "id": "failed-ingestion",
                "timestamp": "2026-07-27T10:00:00+00:00",
                "event_type": "official_web_ingestion",
                "status": "failed",
                "risk": "low",
                "approval_status": "not_required",
            },
        ],
    )

    response = client.get("/logs", headers=auth_headers("admin@company.local"))

    assert response.status_code == 200
    assert [entry["id"] for entry in response.json()] == ["failed-ingestion"]
