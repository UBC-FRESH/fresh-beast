"""Rbeast integration tests (skipped when Rbeast is unavailable)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fresh_beast.beast import (
    BeastConfig,
    annual_negative_probability,
    rbeast_version,
    run_rbeast,
    write_annual_probability_csv,
    write_beast_pixels_csv,
)
from fresh_beast.io import CompositeStack


@pytest.fixture(scope="module")
def available_rbeast() -> str:
    """Skip if the reference Rbeast installation is not present."""
    try:
        return rbeast_version()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"Rbeast unavailable: {exc}")


def test_run_rbeast_and_annual_probability(
    tmp_path: Path, synthetic_stack: CompositeStack, available_rbeast: str
) -> None:
    """BEAST returns finite probabilities and a detectable 2018 step."""
    output = run_rbeast(synthetic_stack, BeastConfig(threshold=0.5))
    assert output.rbeast_version == available_rbeast
    assert output.negative_probability.shape == synthetic_stack.shape
    assert len(output.summaries) == 16
    years, probability, peak = annual_negative_probability(output)
    assert years[0] == 2013
    assert years[-1] == 2018
    assert probability.shape == (len(years), 4, 4)
    assert peak.shape == probability.shape
    assert float(probability[:, 0, 0].max()) >= 0.5
    assert int(years[int(np.argmax(probability[:, 0, 0]))]) >= 2017

    csv_path = tmp_path / "annual.csv"
    write_annual_probability_csv(output, csv_path)
    assert csv_path.exists()
    assert "negative_cp_probability" in csv_path.read_text()

    pixels_path = tmp_path / "beast_pixels.csv"
    write_beast_pixels_csv(output, pixels_path)
    assert pixels_path.exists()
    assert "neg_cp_occ_pr" in pixels_path.read_text()
