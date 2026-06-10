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
            with patch("orchestrator.graph.log_request"):
                result = process_request("printer not working")

        self.assertEqual(result["intent"], "classification_failed")
        self.assertEqual(result["selected_agent"], "general_agent")
        self.assertEqual(result["classifier_source"], "gemini_failed")
        self.assertEqual(result["classifier_error"], "quota exceeded")
        self.assertFalse(result["approval_required"])
        self.assertIn("response", result)


if __name__ == "__main__":
    unittest.main()
