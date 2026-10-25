import copy
import getpass
import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from google.genai import types

import explain_calorie_error as app
from calorie_pipeline import calculate_calories


class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.record = calculate_calories("Test Food", 250, None)
        self.client = Mock()

    def test_success_does_not_call_api(self):
        result = app.explain_record(self.client, calculate_calories("Test Food", 250, 200))
        self.assertIn("succeeded", result)
        self.client.models.generate_content.assert_not_called()

    def test_error_sends_original_evidence_and_preserves_record(self):
        before = copy.deepcopy(self.record)
        self.client.models.generate_content.return_value = SimpleNamespace(
            candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
            text="  Nutrition information is missing. The cause is unknown.  ",
        )
        result = app.explain_record(self.client, self.record)
        self.assertEqual(result, "Nutrition information is missing. The cause is unknown.")
        self.assertEqual(self.record, before)
        self.client.models.generate_content.assert_called_once()
        request = self.client.models.generate_content.call_args.kwargs
        self.assertEqual(json.loads(request["contents"]), before)
        self.assertEqual(request["model"], app.MODEL)
        self.assertEqual(request["config"].system_instruction, app.INSTRUCTIONS)

    def test_incomplete_or_missing_candidate_rejected(self):
        for candidates in ([], [SimpleNamespace(finish_reason=types.FinishReason.MAX_TOKENS)]):
            with self.subTest(candidates=candidates):
                self.client.models.generate_content.return_value = SimpleNamespace(
                    candidates=candidates, text="Partial explanation"
                )
                with self.assertRaisesRegex(RuntimeError, "complete text explanation"):
                    app.explain_record(self.client, self.record)

    def test_empty_text_rejected(self):
        for text in (None, "", "   "):
            with self.subTest(text=text):
                self.client.models.generate_content.return_value = SimpleNamespace(
                    candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)],
                    text=text,
                )
                with self.assertRaisesRegex(RuntimeError, "no text explanation"):
                    app.explain_record(self.client, self.record)

    def test_invalid_json_numbers_never_reach_api(self):
        record = calculate_calories("Test Food", float("nan"), 200)
        with self.assertRaises(ValueError):
            app.explain_record(self.client, record)
        self.client.models.generate_content.assert_not_called()

    def test_api_status_reports_do_not_print_provider_details(self):
        for code in (400, 401, 403, 404, 429, 500, 418):
            with self.subTest(code=code):
                output = io.StringIO()
                with redirect_stdout(output):
                    app.describe_api_error(SimpleNamespace(code=code, message="PRIVATE_DETAIL"))
                self.assertIn(str(code), output.getvalue())
                self.assertNotIn("PRIVATE_DETAIL", output.getvalue())
                if code == 429:
                    self.assertIn("does not prove", output.getvalue())


class CommandLineTests(unittest.TestCase):
    def test_unconfirmed_free_tier_stops_without_client(self):
        with patch("builtins.input", return_value="no"), patch.object(app.genai, "Client") as client:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(app.main(), 1)
            client.assert_not_called()

    def test_empty_key_stops_without_client(self):
        with patch.dict(app.os.environ, {}, clear=True), patch("builtins.input", return_value="FREE"):
            with patch.object(app.getpass, "getpass", return_value=""), patch.object(app.genai, "Client") as client:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(app.main(), 1)
                client.assert_not_called()

    def test_hidden_input_failure_does_not_fall_back_to_visible_input(self):
        with patch.dict(app.os.environ, {}, clear=True), patch("builtins.input", return_value="FREE") as visible_input:
            with patch.object(app.getpass, "getpass", side_effect=getpass.GetPassWarning):
                with patch.object(app.genai, "Client") as client, redirect_stdout(io.StringIO()):
                    self.assertEqual(app.main(), 1)
                client.assert_not_called()
                visible_input.assert_called_once()

    def test_environment_key_and_sdk_configuration_with_mocked_generation(self):
        output = io.StringIO()
        with patch.dict(app.os.environ, {"GEMINI_API_KEY": "unit-test-placeholder"}, clear=True):
            with patch("builtins.input", return_value="FREE"), patch.object(app.getpass, "getpass") as key_prompt:
                with patch.object(app.genai, "Client") as client, patch.object(app, "explain_record", return_value="Unknown cause."):
                    with redirect_stdout(output):
                        self.assertEqual(app.main(), 0)
                    settings = client.call_args.kwargs["http_options"]
                    self.assertEqual(settings.retry_options.attempts, 1)
                    self.assertEqual(settings.timeout, 30000)
                    self.assertEqual(settings.base_url, "https://generativelanguage.googleapis.com")
                key_prompt.assert_not_called()
        self.assertNotIn("unit-test-placeholder", output.getvalue())
