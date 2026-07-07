from fastapi.testclient import TestClient
from app import app
from tests.auth_helpers import auth_headers

client = TestClient(app)


def test_status_endpoint():
    response = client.get("/status")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "online"
    assert data["service"] == "Enterprise AI Orchestrator"


def test_chat_support_request():
    response = client.post(
        "/chat",
        json={"message": "printer not working"},
        headers=auth_headers("employee@company.local"),
    )

    assert response.status_code == 200
    data = response.json()

    assert set(data) == {
        "status",
        "response",
        "requires_approval",
        "approval_id",
        "sources",
        "technical",
    }
    assert "response" in data
    assert "technical" in data
    assert "agent_result" not in data
    assert data["technical"]["agent"] == "support_agent"


def test_chat_odoo_request():
    response = client.post(
        "/chat",
        json={"message": "check stock in Odoo for product X"},
        headers=auth_headers("viewer@company.local"),
    )

    assert response.status_code == 200
    data = response.json()

    assert set(data) == {
        "status",
        "response",
        "requires_approval",
        "approval_id",
        "sources",
        "technical",
    }
    assert "response" in data
    assert "technical" in data
    assert "agent_result" not in data
    assert data["technical"]["agent"] == "odoo_agent"
