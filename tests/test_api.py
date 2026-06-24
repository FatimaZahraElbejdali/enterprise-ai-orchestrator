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

    assert "intent" in data
    assert "selected_agent" in data
    assert "selected_model" in data
    assert "agent_result" in data


def test_chat_odoo_request():
    response = client.post(
        "/chat",
        json={"message": "check stock in Odoo for product X"},
        headers=auth_headers("viewer@company.local"),
    )

    assert response.status_code == 200
    data = response.json()

    assert "intent" in data
    assert "selected_agent" in data
    assert "agent_result" in data
