from orchestrator.auth import authenticate_demo_user


DEMO_PASSWORDS = {
    "admin@company.local": "admin123",
    "odoo.manager@company.local": "manager123",
    "it.manager@company.local": "it123",
    "support@company.local": "support123",
    "employee@company.local": "employee123",
    "viewer@company.local": "viewer123",
}


def auth_headers(email: str = "admin@company.local") -> dict:
    result = authenticate_demo_user(email, DEMO_PASSWORDS[email])

    assert result is not None

    return {
        "Authorization": f"Bearer {result['access_token']}",
    }
