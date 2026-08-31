from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


def test_chroma_is_exactly_pinned_in_an_opt_in_dependency_group() -> None:
    pyproject = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text())

    assert "chromadb" not in "\n".join(pyproject["project"]["dependencies"]).lower()
    assert pyproject["dependency-groups"]["chroma-spike"] == ["chromadb==1.5.9"]
    assert importlib.metadata.version("chromadb") == "1.5.9"


def test_production_package_does_not_import_spike_or_chroma() -> None:
    production_files = (BACKEND_ROOT / "src" / "job_hunter").rglob("*.py")

    forbidden_imports = ("import chromadb", "from chromadb", "from spikes", "import spikes")
    violations = [
        str(path.relative_to(PROJECT_ROOT))
        for path in production_files
        if any(token in path.read_text() for token in forbidden_imports)
    ]

    assert violations == []
