from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*arguments: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    environment["NO_COLOR"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "scicalc", *arguments],
        cwd=ROOT,
        input=stdin,
        capture_output=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )


class CliTests(unittest.TestCase):
    def test_one_shot(self) -> None:
        result = run_cli("sin(pi / 2) + sqrt(16)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "5")

    def test_degree_flag(self) -> None:
        result = run_cli("--degrees", "sin(30) + asin(0.5)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "30.5")

    def test_precision_option(self) -> None:
        result = run_cli("-p", "5", "1 / 3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.33333")

    def test_attached_precision_option(self) -> None:
        result = run_cli("-p5", "1 / 3")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "0.33333")

    def test_expression_made_of_multiple_arguments(self) -> None:
        result = run_cli("2", "+", "3", "*", "4")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "14")

    def test_large_integer_result(self) -> None:
        result = run_cli("10^5000")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1e5000")

        result = run_cli("sqrt(10^600)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "1e300")

    def test_leading_minus_expression(self) -> None:
        result = run_cli("-2^2 + 10")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "6")

    def test_error_returns_nonzero(self) -> None:
        result = run_cli("1 / 0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("不能除以 0", result.stderr)
        self.assertIn("^", result.stderr)

    def test_pipeline_mode(self) -> None:
        result = run_cli(stdin="1+1\n2^10\nx = 5\nx * 2\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["2", "1024", "x = 5", "10"])

    def test_pipeline_continues_after_error(self) -> None:
        result = run_cli(stdin="1/0\n2+2\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("不能除以 0", result.stderr)
        self.assertEqual(result.stdout.strip(), "4")

    def test_commands_in_stream(self) -> None:
        result = run_cli(stdin=":deg\nsin(30)\n:vars\n:history\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("角度单位已切换为 DEG", result.stdout)
        self.assertIn("0.5", result.stdout)
        self.assertIn("ans = 0.5", result.stdout)

    def test_help(self) -> None:
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("科学计算器", result.stdout)
        self.assertIn("--degrees", result.stdout)

    def test_version(self) -> None:
        result = run_cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("scicalc 1.1.0", result.stdout)


if __name__ == "__main__":
    unittest.main()
