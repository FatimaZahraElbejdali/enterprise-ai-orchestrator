from orchestrator.risk import classify_risk, requires_approval_for_risk


def test_low_risk_message():
    assert classify_risk("What is the status of the server?") == "low"


def test_medium_risk_message():
    assert classify_risk("Update the stock quantity for this product") == "medium"


def test_high_risk_message():
    assert classify_risk("Delete this customer invoice") == "high"


def test_empty_message_is_low_risk():
    assert classify_risk("") == "low"


def test_medium_risk_requires_approval():
    assert requires_approval_for_risk("medium") is True


def test_high_risk_requires_approval():
    assert requires_approval_for_risk("high") is True


def test_low_risk_does_not_require_approval():
    assert requires_approval_for_risk("low") is False