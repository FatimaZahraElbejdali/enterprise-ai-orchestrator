from fastapi.testclient import TestClient

import app as app_module
from tests.auth_helpers import auth_headers


def test_document_routes_are_in_openapi_schema():
    client = TestClient(app_module.app)

    schema = client.get("/openapi.json").json()

    assert "/odoo/document/search" in schema["paths"]
    assert "/odoo/document/details" in schema["paths"]


def test_document_search_endpoint_dispatches_and_normalizes(monkeypatch):
    monkeypatch.setattr(
        app_module.odoo,
        "search_invoice",
        lambda query: {
            "success": True,
            "found": True,
            "ambiguous": False,
            "model": "account.move",
            "record_id": 10,
            "name": query,
            "partner": "Client A",
            "state": "draft",
            "date": "2026-06-18",
            "candidates": [
                {
                    "id": 10,
                    "name": query,
                    "partner": "Client A",
                    "state": "draft",
                    "date": "2026-06-18",
                },
            ],
            "message": "Document resolved.",
        },
    )

    client = TestClient(app_module.app)
    response = client.get(
        "/odoo/document/search",
        params={
            "type": "invoice",
            "query": "INV/2026/001",
        },
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "success": True,
        "type": "invoice",
        "model": "account.move",
        "query": "INV/2026/001",
        "found": True,
        "ambiguous": False,
        "candidates": [
            {
                "id": 10,
                "name": "INV/2026/001",
                "partner": "Client A",
                "state": "draft",
                "date": "2026-06-18",
            },
        ],
        "message": "Document resolved.",
    }


def test_document_details_endpoint_includes_lines(monkeypatch):
    monkeypatch.setattr(
        app_module.odoo,
        "get_sale_order_details",
        lambda query: {
            "success": True,
            "found": True,
            "ambiguous": False,
            "model": "sale.order",
            "record_id": 20,
            "document": {
                "id": 20,
                "name": query,
                "partner": "Client B",
                "state": "sale",
                "date": "2026-06-18",
            },
            "lines": [
                {
                    "line_id": 5,
                    "product": "BACO CLEAN",
                    "quantity": 2,
                    "price_unit": 7,
                },
            ],
            "candidates": [],
            "message": "Document details read from Odoo.",
        },
    )

    client = TestClient(app_module.app)
    response = client.get(
        "/odoo/document/details",
        params={
            "type": "sale_order",
            "query": "S00045",
        },
        headers=auth_headers("odoo.manager@company.local"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["type"] == "sale_order"
    assert data["model"] == "sale.order"
    assert data["record"]["name"] == "S00045"
    assert data["record"]["lines"][0]["product"] == "BACO CLEAN"
