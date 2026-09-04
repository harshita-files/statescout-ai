"""Structural invariants of the monorepo.

The layout is a team contract, not a convention: each directory has exactly one
owning track, and the dependency direction between them is one-way. These tests
fail loudly when a rename or a stray import quietly changes that.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every Python module of the agent, with its owning track. Renaming one of these
# is a cross-track decision; this list is what makes that decision visible.
AGENT_MODULES = {
    "crawler": "A",
    "orchestrator": "B",
    "perception": "C",
    "negation": "C",
    "graph": "D",
}

TOP_LEVEL_DIRS = [
    "apps/agent",
    "apps/vscode-extension",
    "services/api",
    "packages/shared-types",
    "research/finetune",
    "research/benchmark",
    "infra",
    "test-apps",
    "tests/unit",
    "tests/integration",
    "tests/e2e",
    ".github/workflows",
]

REQUIRED_ROOT_FILES = [
    ".env.example",
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "infra/docker-compose.yml",
]


@pytest.mark.parametrize("relative_path", TOP_LEVEL_DIRS)
def test_declared_directory_exists(relative_path: str) -> None:
    assert (REPO_ROOT / relative_path).is_dir(), f"missing directory: {relative_path}"


@pytest.mark.parametrize("relative_path", REQUIRED_ROOT_FILES)
def test_required_file_exists(relative_path: str) -> None:
    assert (REPO_ROOT / relative_path).is_file(), f"missing file: {relative_path}"


@pytest.mark.parametrize("module", sorted(AGENT_MODULES))
def test_agent_module_is_a_package(module: str) -> None:
    """Importable as `apps.agent.<module>` — tests depend on this path shape."""
    assert (REPO_ROOT / "apps" / "agent" / module / "__init__.py").is_file()


@pytest.mark.parametrize("module", sorted(AGENT_MODULES))
def test_agent_module_documents_its_owner(module: str) -> None:
    """Ownership lives next to the code, so nobody has to ask who to bother."""
    readme = REPO_ROOT / "apps" / "agent" / module / "README.md"
    assert readme.is_file(), f"{module}/README.md is missing"
    assert f"Track {AGENT_MODULES[module]}" in readme.read_text(encoding="utf-8")


def _imported_roots(source: Path) -> set[str]:
    """Top-level package name of every absolute import in a file."""
    tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_product_code_never_imports_research() -> None:
    """`research/` is a cuttable bet. Nothing shippable may depend on it."""
    offenders = [
        path.relative_to(REPO_ROOT)
        for directory in ("apps", "services")
        for path in (REPO_ROOT / directory).rglob("*.py")
        if "research" in _imported_roots(path)
    ]
    assert not offenders, f"product code imports research/: {offenders}"
