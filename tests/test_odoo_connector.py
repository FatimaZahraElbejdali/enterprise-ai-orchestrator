from integrations.odoo_connector import OdooConnector


def test_odoo_connector_mock_mode():
    connector = OdooConnector()

    result = connector.test_connection()

    assert "connected" in result
    assert "mode" in result


def test_odoo_check_stock_mock():
    connector = OdooConnector()

    result = connector.check_stock("Product X")

    assert "product" in result
    assert result["product"] == "Product X"


def test_odoo_create_purchase_request_mock():
    connector = OdooConnector()

    result = connector.create_purchase_request("10 laptops")

    assert result["action"] == "create_purchase_request"