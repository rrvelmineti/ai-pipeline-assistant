import io
import json
import os
import unittest
from unittest.mock import patch
from orders_assistant.explain import gemini_settings, gemini_explain, ExplanationError


class GeminiSettingsTests(unittest.TestCase):
    def test_secrets_work_without_environment_and_normalize_model(self):
        for model in (" test-model ", " models/test-model "):
            with self.subTest(model=model), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(gemini_settings({"GEMINI_API_KEY": " test-key ", "GEMINI_MODEL": model}),
                                 ("test-key", "test-model"))

    def test_explicit_secrets_override_environment(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "old-key", "GEMINI_MODEL": "bad model"}):
            self.assertEqual(gemini_settings({"GEMINI_API_KEY": "new-key", "GEMINI_MODEL": "new-model"}),
                             ("new-key", "new-model"))

    def test_environment_fallback_without_secrets_file(self):
        class MissingSecrets:
            def get(self, name):
                raise FileNotFoundError()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "test-model"}):
            self.assertEqual(gemini_settings(MissingSecrets()), ("test-key", "test-model"))

    def test_missing_settings_name_the_problem_without_key_value(self):
        for settings, missing in [({}, "GEMINI_API_KEY and GEMINI_MODEL"),
                                  ({"GEMINI_API_KEY": "SECRET"}, "Missing GEMINI_MODEL"),
                                  ({"GEMINI_MODEL": "test-model"}, "Missing GEMINI_API_KEY")]:
            with self.subTest(missing=missing), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ExplanationError) as error:
                    gemini_settings(settings)
                self.assertIn(missing, str(error.exception))
                self.assertNotIn("SECRET", str(error.exception))

    def test_invalid_model_has_specific_safe_error(self):
        for model in ("GEMINI DISPLAY NAME", "models/", "models/models/test", "../test"):
            with self.subTest(model=model), patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ExplanationError) as error:
                    gemini_settings({"GEMINI_API_KEY": "SECRET", "GEMINI_MODEL": model})
                self.assertIn("API model ID", str(error.exception))
                self.assertNotIn("SECRET", str(error.exception))

    def test_wrong_types_and_header_control_characters(self):
        for settings in [{"GEMINI_API_KEY": 123, "GEMINI_MODEL": "test"},
                         {"GEMINI_API_KEY": "SECRET", "GEMINI_MODEL": 123},
                         {"GEMINI_API_KEY": "SECRET\nKEY", "GEMINI_MODEL": "test"}]:
            with self.subTest(settings=tuple(settings)), self.assertRaises(ExplanationError):
                gemini_settings(settings)

    def test_normalized_request_uses_exactly_one_models_prefix(self):
        record = {"schema_version": 1, "status": "error", "stage": "validation",
                  "error": {"code": "invalid_quantity"}}
        response = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(
            {"code": "invalid_quantity", "stage": "validation", "underlying_cause": None})}]}}]}
        def opener(request, timeout):
            self.assertEqual(request.full_url,
                             "https://generativelanguage.googleapis.com/v1beta/models/test-model:generateContent")
            return io.BytesIO(json.dumps(response).encode())
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(gemini_explain(record, opener, secrets={
                "GEMINI_API_KEY": "test-key", "GEMINI_MODEL": "models/test-model"})["source"],
                "gemini-verified classification")
