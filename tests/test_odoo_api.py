from fastapi.testclient import TestClient
from app import app
from tests.auth_helpers import auth_headers

client = TestClient(app)


def test_odoo_status_endpoint():
    response = client.get(
        "/odoo/status",
        headers=auth_headers("viewer@company.local"),
    )

    assert response.status_code == 200

    data = response.json()

    assert "connected" in data
    assert "mode" in data
    assert "message" in data


def test_odoo_stock_endpoint():
    response = client.get(
        "/odoo/stock/BACO%20CLEAN",
        headers=auth_headers("viewer@company.local"),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["found"] is True
    assert data["product"] == "BACO CLEAN"
    assert "stock_quantity" in data
    assert "forecast_quantity" in data
    assert "sale_price" in data
