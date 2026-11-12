"""Regression tests for the installed Frank Energie MCP package metadata."""

from importlib.metadata import metadata


def test_distribution_exposes_mit_spdx_license() -> None:
    """Ensure the build backend publishes the SPDX license and LICENSE file."""
    package_metadata = metadata("frank-energie-mcp")

    assert package_metadata["License-Expression"] == "MIT"
    assert "LICENSE" in package_metadata.get_all("License-File", [])
    assert not package_metadata.get_all("License")
    assert "License :: OSI Approved :: MIT License" not in package_metadata.get_all(
        "Classifier", []
    )
