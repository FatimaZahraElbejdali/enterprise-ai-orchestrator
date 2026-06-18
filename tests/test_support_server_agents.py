from agents import support_agent
from agents import server_agent
from integrations.internal_server_connector import InternalServerConnector


def test_support_odoo_access_returns_structured_steps(monkeypatch):
    monkeypatch.setattr("agents.support_agent.is_openai_configured", lambda: False)

    result = support_agent.run(
        "Je n’arrive pas à accéder à Odoo, quelles étapes dois-je vérifier ?"
    )

    assert result["intent"] == "support"
    assert result["agent"] == "support_agent"
    assert result["action"] == "troubleshoot_issue"
    assert result["requires_approval"] is False
    assert result["status"] == "completed"
    assert "Vérifier la connexion internet." in result["result"]["steps"]
    assert "administrateur IT" in result["result"]["escalation"]


def test_internal_server_connector_list_create_read_and_block(tmp_path):
    connector = InternalServerConnector(str(tmp_path))

    empty = connector.list_files()
    assert empty["success"] is True
    assert empty["files"] == []

    created = connector.store_text_file(
        "test-note.txt",
        "Ceci est un test de l’orchestrateur.",
    )
    assert created["success"] is True
    assert created["filename"] == "test-note.txt"

    listed = connector.list_files()
    assert listed["files"] == ["test-note.txt"]

    read = connector.read_text_file("test-note.txt")
    assert read["success"] is True
    assert read["content"] == "Ceci est un test de l’orchestrateur."

    blocked = connector.read_text_file("../.env")
    assert blocked["success"] is False
    assert blocked["blocked"] is True
    assert blocked["action"] == "blocked_sensitive_path"


def test_server_agent_blocks_env_path(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.server_agent.connector",
        InternalServerConnector(str(tmp_path)),
    )

    result = server_agent.run("Lis le fichier serveur ../.env")

    assert result["intent"] == "server"
    assert result["agent"] == "server_agent"
    assert result["parsed_action"] == "blocked_sensitive_path"
    assert result["approval_required"] is False
    assert result["result"]["blocked"] is True


def test_server_agent_create_and_read_file(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.server_agent.connector",
        InternalServerConnector(str(tmp_path)),
    )

    created = server_agent.run(
        "Crée un fichier serveur nommé test-note.txt avec le contenu: Ceci est un test"
    )
    assert created["parsed_action"] == "create_internal_file"
    assert created["result"]["success"] is True

    read = server_agent.run("Lis le fichier serveur test-note.txt")
    assert read["parsed_action"] == "read_internal_file"
    assert read["result"]["content"] == "Ceci est un test"
