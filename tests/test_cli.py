"""Tests for the final CLI integration phase."""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from wtp_autolayout.cli.main import main


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_JSON = ROOT / "sample_data" / "sample_wtp_input.json"
SAMPLE_XLSX = ROOT / "sample_data" / "sample_wtp_input.xlsx"


class TestCLI(unittest.TestCase):
    def test_cli_executes_using_sample_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code, stdout, stderr = self._run_cli(SAMPLE_JSON, temp_dir)

            self.assertEqual(code, 0, stderr)
            self.assertIn("Plant AutoLayout Engine", stdout)
            self.assertIn("Completed.", stdout)

    def test_output_directory_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "nested" / "outputs"
            code, _, stderr = self._run_cli(SAMPLE_JSON, output_dir, "--no-pdf", "--no-png", "--no-json")

            self.assertEqual(code, 0, stderr)
            self.assertTrue(output_dir.exists())

    def test_requested_export_files_created(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code, _, stderr = self._run_cli(SAMPLE_JSON, temp_dir)

            self.assertEqual(code, 0, stderr)
            self.assertGreater((Path(temp_dir) / "optimized_layout.png").stat().st_size, 0)
            self.assertGreater((Path(temp_dir) / "optimized_layout.pdf").stat().st_size, 0)
            self.assertGreater((Path(temp_dir) / "optimized_layout.json").stat().st_size, 0)
            self.assertGreater((Path(temp_dir) / "optimization_result.json").stat().st_size, 0)

    def test_no_pdf_works(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code, _, stderr = self._run_cli(SAMPLE_JSON, temp_dir, "--no-pdf")

            self.assertEqual(code, 0, stderr)
            self.assertFalse((Path(temp_dir) / "optimized_layout.pdf").exists())
            self.assertTrue((Path(temp_dir) / "optimized_layout.png").exists())

    def test_no_png_works(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code, _, stderr = self._run_cli(SAMPLE_JSON, temp_dir, "--no-png", "--no-pdf")

            self.assertEqual(code, 0, stderr)
            self.assertFalse((Path(temp_dir) / "optimized_layout.png").exists())
            self.assertTrue((Path(temp_dir) / "optimized_layout.json").exists())

    def test_no_json_works(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code, _, stderr = self._run_cli(SAMPLE_JSON, temp_dir, "--no-json", "--no-pdf")

            self.assertEqual(code, 0, stderr)
            self.assertFalse((Path(temp_dir) / "optimized_layout.json").exists())
            self.assertFalse((Path(temp_dir) / "optimization_result.json").exists())
            self.assertTrue((Path(temp_dir) / "optimized_layout.png").exists())

    def test_invalid_input_returns_non_zero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            code, _, stderr = self._run_cli(Path(temp_dir) / "missing.json", temp_dir)

            self.assertNotEqual(code, 0)
            self.assertIn("Input file not found", stderr)

    def test_json_and_xlsx_both_work(self) -> None:
        with tempfile.TemporaryDirectory() as json_dir, tempfile.TemporaryDirectory() as xlsx_dir:
            json_code, _, json_stderr = self._run_cli(SAMPLE_JSON, json_dir, "--no-pdf", "--no-png")
            xlsx_code, _, xlsx_stderr = self._run_cli(SAMPLE_XLSX, xlsx_dir, "--no-pdf", "--no-png")

            self.assertEqual(json_code, 0, json_stderr)
            self.assertEqual(xlsx_code, 0, xlsx_stderr)
            self.assertTrue((Path(json_dir) / "optimized_layout.json").exists())
            self.assertTrue((Path(xlsx_dir) / "optimized_layout.json").exists())

    def _run_cli(self, input_path, output_dir, *extra_args):
        args = [
            "--input",
            str(input_path),
            "--output",
            str(output_dir),
            "--algorithm",
            "ranked",
            "--candidate-count",
            "1",
            "--iterations",
            "0",
            "--seed",
            "1",
        ]
        args.extend(extra_args)

        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
