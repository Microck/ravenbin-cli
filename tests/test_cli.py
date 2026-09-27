"""Check the command-line contract without contacting Raven Bin."""

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "ravenbin.cli", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_help_lists_commands(self) -> None:
        run = run_cli("--help")
        self.assertEqual(run.returncode, 0)
        self.assertIn("upload", run.stdout)
        self.assertIn("fetch", run.stdout)
        self.assertIn("download", run.stdout)

    def test_version(self) -> None:
        run = run_cli("--version")
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.stdout.strip(), "ravenbin 0.2.0")

    def test_missing_command_is_usage_error(self) -> None:
        run = run_cli()
        self.assertEqual(run.returncode, 2)
        self.assertIn("required: command", run.stderr)

    def test_upload_missing_file_is_usage_error(self) -> None:
        run = run_cli("upload", "missing-file")
        self.assertEqual(run.returncode, 2)
        self.assertIn("file does not exist", run.stderr)

    def test_download_alias_validates_share_url(self) -> None:
        run = run_cli("download", "https://example.com/")
        self.assertEqual(run.returncode, 1)
        self.assertIn("https://ravenbin.com/", run.stderr)


if __name__ == "__main__":
    unittest.main()
