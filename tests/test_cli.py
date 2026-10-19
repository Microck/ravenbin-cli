"""Check the command-line contract without contacting Raven Bin."""

import os
import subprocess
import sys
import unittest

from ravenbin import cli
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
    def test_browser_options_without_posix_geteuid(self) -> None:
        original = getattr(os, "geteuid", None)
        if original is not None:
            del os.geteuid
        try:
            self.assertTrue(cli.browser_options()["headless"])
            self.assertNotIn("args", cli.browser_options())
        finally:
            if original is not None:
                os.geteuid = original

    def test_timeout_requires_finite_positive_seconds(self) -> None:
        for value in ("0", "-1", "nan", "inf", "-inf", "1e308", str((cli.MAX_TIMEOUT_MS + 1) / 1000)):
            run = run_cli("fetch", "https://example.com/", "--timeout=" + value)
            self.assertEqual(run.returncode, 2)
            self.assertIn("timeout must be finite positive seconds", run.stderr)
        self.assertEqual(cli.parse_args(["fetch", "https://example.com/", "--timeout=0.5"]).timeout, 0.5)
        maximum = cli.MAX_TIMEOUT_MS / 1000
        self.assertEqual(cli.positive_timeout(str(maximum)) * 1000, cli.MAX_TIMEOUT_MS)

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
