from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

DEFAULT_EXCLUDES = frozenset(
    {
        ".git",
        ".next",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "target",
        "__pycache__",
        ".infrastructure-data",
    }
)


def resolve_target_root(locator: str) -> Path:
    root = Path(locator).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Scan target does not exist: {root}")
    return root


def iter_files(
    root: Path,
    *,
    suffixes: frozenset[str] | None = None,
    names: frozenset[str] | None = None,
    max_file_bytes: int = 2_000_000,
    excludes: frozenset[str] = DEFAULT_EXCLUDES,
) -> Iterable[Path]:
    if root.is_file():
        candidates = (root,)
    else:
        candidates = root.rglob("*")

    for path in candidates:
        if not path.is_file():
            continue
        if any(part in excludes for part in path.parts):
            continue
        if suffixes is not None and path.suffix.lower() not in suffixes:
            if names is None or path.name not in names:
                continue
        elif names is not None and suffixes is None and path.name not in names:
            continue
        try:
            if path.stat().st_size > max_file_bytes:
                continue
        except OSError:
            continue
        yield path


def relative_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root if root.is_dir() else root.parent))
    except ValueError:
        return str(path)
