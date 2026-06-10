import json
import os
import sys
import types
import unittest
from unittest.mock import patch

from models import gemini_classifier


class GeminiClassifierTests(unittest.TestCase):
    def test_missing_api_key_returns_explicit_failure(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            result = gemini_classifier.classify_intent("printer not working")

        self.assertEqual(result["intent"], "classification_failed")
        self.assertEqual(result["selected_agent"], "general_agent")
        self.assertEqual(result["confidence"], 0.0)
        self.assertFalse(result["requires_approval"])
        self.assertEqual(result["classifier_source"], "gemini_failed")
        self.assertEqual(result["classifier_error"], "GEMINI_API_KEY is not set")

    def test_successful_gemini_response_is_normalized(self):
        fake_response = types.SimpleNamespace(text=json.dumps({
            "intent": "support",
            "selected_agent": "support_agent",
            "confidence": 0.95,
            "requires_approval": False,
            "classifier_source": "gemini",
            "classifier_error": None,
        }))

        fake_model = unittest.mock.Mock()
        fake_model.generate_content.return_value = fake_response

        fake_genai = types.SimpleNamespace(
            configure=unittest.mock.Mock(),
            GenerativeModel=unittest.mock.Mock(return_value=fake_model),
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch.dict(sys.modules, {"google.generativeai": fake_genai}):
                result = gemini_classifier.classify_intent("printer not working")

        self.assertEqual(result, {
            "intent": "support",
            "selected_agent": "support_agent",
            "confidence": 0.95,
            "requires_approval": False,
            "classifier_source": "gemini",
            "classifier_error": None,
        })
        fake_genai.configure.assert_called_once_with(api_key="test-key")
        fake_genai.GenerativeModel.assert_called_once_with(
            gemini_classifier.GEMINI_MODEL
        )

    def test_gemini_exception_returns_explicit_failure(self):
        fake_model = unittest.mock.Mock()
        fake_model.generate_content.side_effect = RuntimeError("quota exceeded")

        fake_genai = types.SimpleNamespace(
            configure=unittest.mock.Mock(),
            GenerativeModel=unittest.mock.Mock(return_value=fake_model),
        )

        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch.dict(sys.modules, {"google.generativeai": fake_genai}):
                result = gemini_classifier.classify_intent(
                    "create purchase request for 10 laptops"
                )

        self.assertEqual(result["intent"], "classification_failed")
        self.assertEqual(result["selected_agent"], "general_agent")
        self.assertEqual(result["classifier_source"], "gemini_failed")
        self.assertEqual(result["classifier_error"], "quota exceeded")


if __name__ == "__main__":
    unittest.main()
