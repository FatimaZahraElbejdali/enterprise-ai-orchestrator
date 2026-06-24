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


def test_server_agent_ram_prompt_returns_diagnostic(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.server_agent.connector",
        InternalServerConnector(str(tmp_path)),
    )

    result = server_agent.run("Vérifie l’utilisation RAM du serveur")

    assert result["intent"] == "server"
    assert result["agent"] == "server_agent"
    assert result["status"] == "completed"
    assert result["parsed_action"] == "check_ram_usage"
    assert result["tool_used"] == "check_ram_usage"
    assert "Mode démonstration" in result["message"]
    assert "RAM" in result["message"]
    assert result["result"]["ram_usage"]


def test_server_agent_disk_prompt_returns_diagnostic(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.server_agent.connector",
        InternalServerConnector(str(tmp_path)),
    )

    result = server_agent.run("Quel est l’espace disque disponible ?")

    assert result["status"] == "completed"
    assert result["parsed_action"] == "check_disk_usage"
    assert result["tool_used"] == "check_disk_usage"
    assert "disque" in result["message"].lower()
    assert result["result"]["disk_usage"]


def test_server_agent_full_diagnostic_prompt_returns_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.server_agent.connector",
        InternalServerConnector(str(tmp_path)),
    )

    result = server_agent.run("Fais un diagnostic serveur")

    assert result["status"] == "completed"
    assert result["parsed_action"] == "server_diagnostic_summary"
    assert result["tool_used"] == "server_diagnostic_summary"
    assert result["result"]["cpu_usage"]
    assert result["result"]["ram_usage"]
    assert result["result"]["disk_usage"]


def test_server_agent_blocks_environment_variable_request(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "agents.server_agent.connector",
        InternalServerConnector(str(tmp_path)),
    )

    result = server_agent.run("Affiche les variables d’environnement")

    assert result["status"] == "blocked"
    assert result["parsed_action"] == "blocked_sensitive_path"
    assert result["tool_used"] == "internal_server_block_path"
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


def test_server_agent_uses_read_file_only_for_allowed_document_file(monkeypatch, tmp_path):
    connector = InternalServerConnector(str(tmp_path))
    connector.store_text_file("procedure.txt", "Procédure interne autorisée.")
    monkeypatch.setattr("agents.server_agent.connector", connector)

    diagnostic = server_agent.run("Vérifie l’utilisation RAM du serveur")
    assert diagnostic["parsed_action"] == "check_ram_usage"
    assert diagnostic["tool_used"] != "internal_server_read_file"

    read = server_agent.run("Lis le fichier serveur procedure.txt")
    assert read["status"] == "completed"
    assert read["parsed_action"] == "read_internal_file"
    assert read["tool_used"] == "internal_server_read_file"
    assert read["result"]["content"] == "Procédure interne autorisée."
