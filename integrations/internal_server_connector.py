import os
from pathlib import Path


BLOCKED_FILENAMES = {".env"}

SAFE_SERVER_REGISTRY = {
    "local_orchestrator": {
        "display_name": "serveur local de l’orchestrateur",
        "aliases": {
            "local_orchestrator",
            "orchestrateur",
            "orchestrator",
            "serveur local",
            "local server",
            "serveur local de l'orchestrateur",
            "serveur local de l’orchestrateur",
            "orchestrator server",
        },
        "diagnostic_mode": "demo_local",
    },
}


def _normalize_server_reference(value: str):
    return " ".join((value or "").lower().replace("’", "'").split())


class InternalServerConnector:
    def __init__(self, storage_path: str | None = None):
        configured_path = storage_path or os.getenv(
            "INTERNAL_FILE_STORAGE_PATH",
            "./storage",
        )
        self.storage_path = Path(configured_path).resolve()
        self.server_registry = SAFE_SERVER_REGISTRY

    def get_server_registry(self):
        return self.server_registry

    def resolve_server_reference(self, reference: str):
        normalized = _normalize_server_reference(reference)

        for server_id, config in self.server_registry.items():
            aliases = {
                _normalize_server_reference(alias)
                for alias in config.get("aliases", set())
            }

            if normalized == server_id or normalized in aliases:
                return server_id, config

        return None, None

    def _ensure_storage(self):
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_filename(self, filename: str):
        clean_filename = (filename or "").strip()

        if not clean_filename:
            return None, "Nom de fichier manquant."

        if (
            Path(clean_filename).is_absolute()
            or ".." in clean_filename
            or "/" in clean_filename
            or "\\" in clean_filename
            or clean_filename in BLOCKED_FILENAMES
            or clean_filename.lower().endswith(".env")
        ):
            return None, "Chemin refusé: accès limité au stockage interne de démonstration."

        return self.storage_path / clean_filename, None

    def list_files(self):
        self._ensure_storage()
        files = sorted(
            item.name
            for item in self.storage_path.iterdir()
            if item.is_file()
        )

        return {
            "success": True,
            "action": "list_internal_files",
            "files": files,
            "message": (
                "Aucun fichier dans le stockage interne."
                if not files
                else "Fichiers du stockage interne listés."
            ),
        }

    def store_text_file(self, filename: str, content: str):
        path, error = self._resolve_safe_filename(filename)

        if error:
            return self._blocked_result(filename, error)

        self._ensure_storage()
        path.write_text(content or "", encoding="utf-8")

        return {
            "success": True,
            "action": "create_internal_file",
            "filename": path.name,
            "message": f"Fichier {path.name} créé dans le stockage interne.",
        }

    def read_text_file(self, filename: str):
        path, error = self._resolve_safe_filename(filename)

        if error:
            return self._blocked_result(filename, error)

        if not path.exists() or not path.is_file():
            return {
                "success": False,
                "action": "read_internal_file",
                "filename": path.name,
                "found": False,
                "message": "Fichier introuvable dans le stockage interne.",
            }

        return {
            "success": True,
            "action": "read_internal_file",
            "filename": path.name,
            "content": path.read_text(encoding="utf-8"),
            "message": f"Fichier {path.name} lu depuis le stockage interne.",
        }

    def demo_server_metrics(self):
        mode = "Mode démonstration — serveur local de l’orchestrateur"

        return {
            "success": True,
            "mode": mode,
            "cpu_usage": "34%",
            "ram_usage": "61%",
            "disk_usage": "72%",
            "uptime": "2 jours 4 heures",
            "backend_status": "accessible",
            "frontend_status": "accessible",
            "services": [
                {"name": "backend", "status": "actif"},
                {"name": "frontend", "status": "actif"},
                {"name": "orchestrator_api", "status": "actif"},
            ],
        }

    def check_ram_usage(self):
        metrics = self.demo_server_metrics()
        return {
            **metrics,
            "action": "check_ram_usage",
            "message": (
                f"{metrics['mode']} — utilisation RAM actuelle: "
                f"{metrics['ram_usage']}."
            ),
        }

    def check_cpu_usage(self):
        metrics = self.demo_server_metrics()
        return {
            **metrics,
            "action": "check_cpu_usage",
            "message": (
                f"{metrics['mode']} — utilisation CPU actuelle: "
                f"{metrics['cpu_usage']}."
            ),
        }

    def check_disk_usage(self):
        metrics = self.demo_server_metrics()
        return {
            **metrics,
            "action": "check_disk_usage",
            "message": (
                f"{metrics['mode']} — espace disque utilisé: "
                f"{metrics['disk_usage']}."
            ),
        }

    def check_server_status(self):
        metrics = self.demo_server_metrics()
        return {
            **metrics,
            "action": "check_server_status",
            "status": "healthy",
            "message": (
                f"{metrics['mode']} — serveur actif, backend accessible, "
                "frontend accessible."
            ),
        }

    def check_service_status(self):
        metrics = self.demo_server_metrics()
        active_services = ", ".join(
            service["name"]
            for service in metrics["services"]
            if service["status"] == "actif"
        )
        return {
            **metrics,
            "action": "check_service_status",
            "message": (
                f"{metrics['mode']} — services actifs: {active_services}."
            ),
        }

    def server_diagnostic_summary(self):
        metrics = self.demo_server_metrics()
        return {
            **metrics,
            "action": "server_diagnostic_summary",
            "status": "healthy",
            "message": (
                f"{metrics['mode']} — diagnostic OK: CPU {metrics['cpu_usage']}, "
                f"RAM {metrics['ram_usage']}, disque {metrics['disk_usage']}, "
                f"uptime {metrics['uptime']}."
            ),
        }

    def _blocked_result(self, filename: str, message: str):
        return {
            "success": False,
            "action": "blocked_sensitive_path",
            "filename": filename,
            "blocked": True,
            "message": message,
        }
