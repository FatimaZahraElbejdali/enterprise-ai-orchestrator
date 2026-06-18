import unittest
from unittest.mock import patch

from orchestrator.graph import process_request


class GraphTests(unittest.TestCase):

    def test_chat_does_not_crash_when_gemini_classifier_fails(self):
        failed_classification = {
            "intent": "classification_failed",
            "selected_agent": "general_agent",
            "confidence": 0.0,
            "requires_approval": False,
            "classifier_source": "gemini_failed",
            "classifier_error": "quota exceeded",
        }

        with patch(
            "orchestrator.graph.classify_message",
            return_value=failed_classification,
        ):
            with patch("orchestrator.model_router.is_openai_configured", return_value=False):
                with patch("orchestrator.graph.log_request"):
                    result = process_request("printer not working")

        self.assertEqual(result["intent"], "classification_failed")
        self.assertEqual(result["selected_agent"], "general_agent")
        self.assertEqual(result["classifier_source"], "gemini_failed")
        self.assertEqual(result["classifier_error"], "quota exceeded")
        self.assertFalse(result["approval_required"])
        self.assertIn("risk_level", result)
        self.assertIn("response", result)

    def test_graph_returns_low_risk_level(self):
        classification = {
            "intent": "server",
            "selected_agent": "server_agent",
            "confidence": 0.9,
            "requires_approval": False,
            "classifier_source": "mock",
            "classifier_error": None,
        }

        with patch("orchestrator.graph.classify_message", return_value=classification):
            with patch("orchestrator.model_router.is_openai_configured", return_value=False):
                with patch("orchestrator.graph.log_request"):
                    result = process_request("What is the server status?")

        self.assertEqual(result["risk_level"], "low")
        self.assertFalse(result["approval_required"])
        self.assertEqual(result["approval_status"], "not_required")

    def test_graph_medium_risk_requires_approval(self):
        classification = {
            "intent": "odoo",
            "selected_agent": "odoo_agent",
            "confidence": 0.9,
            "requires_approval": False,
            "classifier_source": "mock",
            "classifier_error": None,
        }

        with patch("orchestrator.graph.classify_message", return_value=classification):
            with patch("orchestrator.model_router.is_openai_configured", return_value=False):
                with patch("orchestrator.graph.log_request"):
                    result = process_request("Update the stock quantity")

        self.assertEqual(result["risk_level"], "medium")
        self.assertTrue(result["approval_required"])
        self.assertEqual(result["approval_status"], "pending")

    def test_graph_high_risk_keeps_odoo_on_policy_engine_and_requires_approval(self):
        classification = {
            "intent": "odoo",
            "selected_agent": "odoo_agent",
            "confidence": 0.9,
            "requires_approval": False,
            "classifier_source": "mock",
            "classifier_error": None,
        }

        with patch("orchestrator.graph.classify_message", return_value=classification):
            with patch("orchestrator.model_router.is_openai_configured", return_value=True):
                with patch("orchestrator.graph.log_request"):
                    result = process_request("Delete this invoice")

        self.assertEqual(result["risk_level"], "high")
        self.assertEqual(result["selected_model"]["provider"], "mock")
        self.assertEqual(result["selected_model"]["model"], "policy_engine")
        self.assertTrue(result["approval_required"])
        self.assertEqual(result["approval_status"], "pending")

    def test_graph_low_risk_does_not_require_approval(self):
        classification = {
            "intent": "knowledge",
            "selected_agent": "knowledge_agent",
            "confidence": 0.9,
            "requires_approval": False,
            "classifier_source": "mock",
            "classifier_error": None,
        }

        with patch("orchestrator.graph.classify_message", return_value=classification):
            with patch("orchestrator.model_router.is_openai_configured", return_value=True):
                with patch("orchestrator.graph.generate_response") as mock_generate:
                    mock_generate.return_value = {
                        "provider": "openai",
                        "model": "gpt-4.1-mini",
                        "success": True,
                        "content": "Mock knowledge response",
                        "error": None,
                    }

                    with patch("orchestrator.graph.log_request"):
                        result = process_request("Show me product information")

        self.assertEqual(result["risk_level"], "low")
        self.assertFalse(result["approval_required"])
        self.assertEqual(result["approval_status"], "not_required")
        self.assertEqual(result["selected_model"]["provider"], "openai")
        self.assertEqual(result["selected_model"]["model"], "gpt-4.1-mini")


if __name__ == "__main__":
    unittest.main()
