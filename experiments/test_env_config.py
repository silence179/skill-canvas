"""Credential configuration behavior: precedence, literal values, and safe errors."""

from pathlib import Path
from contextlib import redirect_stderr
from io import StringIO
import sys
import tempfile
import unittest
from unittest.mock import patch

from env_config import load_env
import run as launcher


class EnvConfigTests(unittest.TestCase):
    def load(self, text, initial=None):
        environment = dict(initial or {})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(text, encoding="utf-8")
            load_env(path, environment)
        return environment

    def test_quotes_comments_empty_values_and_shell_precedence(self):
        actual = self.load(
            '# comment\nexport EXP_AGENT=opencode\n'
            'DEEPSEEK_API_KEY="example # value" # trailing comment\n'
            'DEEPSEEK_BASE_URL=https://api.deepseek.com/v1\n'
            'EXP_EFFORT=\nEXP_MODEL=file-model\n',
            {"EXP_MODEL": "shell-model"},
        )
        self.assertEqual(actual["EXP_MODEL"], "shell-model")
        self.assertEqual(actual["DEEPSEEK_API_KEY"], "example # value")
        self.assertEqual(actual["EXP_EFFORT"], "")
        self.assertEqual(actual["EXP_AGENT"], "opencode")
        self.assertEqual(actual["DEEPSEEK_BASE_URL"], "https://api.deepseek.com/v1")

    def test_values_are_not_executed_or_expanded(self):
        actual = self.load(
            "DEEPSEEK_API_KEY='$(echo example) $" "{OTHER} \x60echo example\x60'\n",
            {"OTHER": "replacement"},
        )
        self.assertEqual(
            actual["DEEPSEEK_API_KEY"],
            "$(echo example) $" "{OTHER} \x60echo example\x60",
        )

    def test_invalid_file_does_not_partially_change_environment_or_echo_values(self):
        environment = {"EXISTING": "unchanged"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("EXP_AGENT=opencode\nDEEPSEEK_API_KEY='example-secret\n")
            with self.assertRaises(ValueError) as error:
                load_env(path, environment)
        self.assertEqual(environment, {"EXISTING": "unchanged"})
        self.assertNotIn("example-secret", str(error.exception))
        self.assertIn(".env:2", str(error.exception))

    def test_missing_file_is_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            environment = {}
            load_env(Path(directory) / ".env", environment)
        self.assertEqual(environment, {})

    def test_missing_deepseek_key_stops_before_launching_any_process(self):
        arguments = [
            "run.py", "curated", "--agent", "opencode",
            "--model", "deepseek/deepseek-flash",
        ]
        output = StringIO()
        with (
            patch.object(launcher, "load_env"),
            patch.dict(launcher.os.environ, {}, clear=True),
            patch.object(sys, "argv", arguments),
            patch.object(launcher.subprocess, "call") as launch,
            redirect_stderr(output),
        ):
            with self.assertRaises(SystemExit) as error:
                launcher.main()
        self.assertEqual(error.exception.code, 2)
        self.assertIn("DEEPSEEK_API_KEY is empty", output.getvalue())
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
