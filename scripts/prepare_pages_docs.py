"""Stage the repository's Markdown and linked sandbox files for MkDocs."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / ".pages-docs"
SANDBOX_DIR = ROOT / "agentic-ai-sandbox"
ALLOWED_SANDBOX_SUFFIXES = {".md", ".py", ".json", ".txt"}
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__"}


def copy_sandbox_sources() -> int:
    copied = 0
    for current, directories, filenames in os.walk(SANDBOX_DIR):
        directories[:] = sorted(
            name
            for name in directories
            if name not in EXCLUDED_DIRS and not name.startswith(".")
        )
        source_dir = Path(current)
        for filename in sorted(filenames):
            source = source_dir / filename
            if filename.startswith(".") or source.suffix.lower() not in ALLOWED_SANDBOX_SUFFIXES:
                continue
            if filename.startswith(("eval-results", "rag-eval")):
                continue
            relative = source.relative_to(SANDBOX_DIR)
            target = DOCS_DIR / "agentic-ai-sandbox" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied += 1
    return copied


def main() -> None:
    if DOCS_DIR.is_symlink():
        raise RuntimeError(f"Refusing to replace symlink: {DOCS_DIR}")
    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True)

    root_markdown = sorted(ROOT.glob("*.md"))
    for source in root_markdown:
        shutil.copy2(source, DOCS_DIR / source.name)

    license_file = ROOT / "LICENSE"
    if license_file.is_file():
        shutil.copy2(license_file, DOCS_DIR / license_file.name)

    sandbox_files = copy_sandbox_sources()
    print(
        f"Prepared {len(root_markdown)} top-level Markdown files and "
        f"{sandbox_files} sandbox source/data files in {DOCS_DIR.name}/"
    )


if __name__ == "__main__":
    main()
