from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CORE_PATHS = (
    ROOT / "docmirror" / "models",
    ROOT / "docmirror" / "input",
    ROOT / "docmirror" / "layout",
    ROOT / "docmirror" / "runtime",
    ROOT / "docmirror" / "structure" / "analysis",
)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def test_core_paths_do_not_import_output_layer() -> None:
    offenders: list[str] = []
    for base in CORE_PATHS:
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            for module in _imports(path):
                if module == "docmirror.output" or module.startswith("docmirror.output."):
                    offenders.append(f"{path.relative_to(ROOT)} imports {module}")

    assert offenders == []
