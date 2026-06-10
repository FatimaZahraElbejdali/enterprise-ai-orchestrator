from orchestrator.approval import requires_approval


def test_requires_approval_for_create():
    assert requires_approval("Create purchase request for 10 laptops") is True


def test_requires_approval_for_french_create():
    assert requires_approval("Créer une demande achat") is True


def test_no_approval_for_read_only_request():
    assert requires_approval("Check stock in Odoo") is False