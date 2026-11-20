import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import download_sra_data


class SraDownloadValidationTests(unittest.TestCase):
    def test_rejects_option_and_shell_injection_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "not-created"
            for accession in ("--help", "SRR123456;whoami", "PRJNA123456"):
                with self.subTest(accession=accession):
                    with patch("server.subprocess.run") as run:
                        result = download_sra_data(accession, str(output_dir))

                    self.assertIn("Validation Error", result)
                    run.assert_not_called()
                    self.assertFalse(output_dir.exists())

    def test_runs_only_a_validated_accession_without_a_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir) / "sra"
            with patch(
                "server.subprocess.run",
                return_value=type("Result", (), {"stdout": "downloaded"})(),
            ) as run:
                result = download_sra_data("srr123456", str(output_dir))

        self.assertIn("SRR123456", result)
        run.assert_called_once_with(
            [
                "fasterq-dump",
                "--outdir",
                str(output_dir),
                "--split-files",
                "--progress",
                "SRR123456",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
