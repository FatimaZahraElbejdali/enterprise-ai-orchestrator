import sqlite3
from pathlib import Path

DB_PATH = Path("database/orchestrator.db")


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            status TEXT,
            user_message TEXT,
            intent TEXT,
            selected_agent TEXT,
            selected_model TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            user_message TEXT,
            intent TEXT,
            risk_level TEXT,
            classification_confidence REAL,
            selected_agent TEXT,
            selected_model TEXT,
            classifier_source TEXT,
            classifier_error TEXT,
            approval_required INTEGER,
            approval_status TEXT,
            approval_id TEXT,
            agent_result TEXT,
            execution_plan TEXT
        )
    """)

    conn.commit()
    conn.close()