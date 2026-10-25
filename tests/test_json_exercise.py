import subprocess
import sys
import unittest
from pathlib import Path


class JsonExerciseTests(unittest.TestCase):
    def test_example_script_prints_expected_fields(self):
        script = Path(__file__).resolve().parents[1] / "check_response.py"
        result = subprocess.run(
            [sys.executable, str(script)], capture_output=True, text=True, check=True
        )
        self.assertEqual(
            result.stdout.splitlines(),
            ["validation", "Nutrition information is missing."],
        )
