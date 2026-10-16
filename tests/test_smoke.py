from pathlib import Path

import pytest
from click.testing import CliRunner

from kubefix.main import cli
#import traceback

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
EXAMPLE_FILES = sorted(EXAMPLES_DIR.glob("*.yaml")) + sorted(EXAMPLES_DIR.glob("*.yml"))


def test_examples_found():
    assert EXAMPLE_FILES, f"no example manifests found in {EXAMPLES_DIR}"


@pytest.mark.parametrize("example", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_runs(example, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            str(example),
            "-o", str(tmp_path / "out.yaml"),
            "-s", str(tmp_path / "stats.md"),
            "-c", str(tmp_path / "stats.csv"),
        ],
    )
    assert result.exit_code == 0, result.output
    #assert result.exit_code == 0, result.output + "".join(traceback.format_exception(*result.exc_info))
    assert result.exception is None
