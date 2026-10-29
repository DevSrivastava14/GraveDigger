"""Exhume deleted files from git history.

Finds files that were deleted and never resurrected, returning their
death metadata for tombstone rendering.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


# Noise filters: easily editable constants at module top
NOISE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".woff", ".woff2", ".ttf", ".pdf", ".zip", ".lock", ".pyc",
}
NOISE_FILENAMES = {
    "package-lock.json", "yarn.lock", "poetry.lock", "uv.lock",
}
NOISE_PATH_PREFIXES = (
    "requirements/", "vendor/", "node_modules/",
    "dist/", "build/", ".github/",
)


@dataclass(frozen=True)
class Death:
    """A file's death record."""
    path: str
    death_commit: str
    death_date: datetime
    killer: str
    death_message: str


class NotARepositoryError(Exception):
    """Raised when the given path is not a git repository."""
    pass


class GitNotFoundError(Exception):
    """Raised when git executable is not found."""
    pass


def _run_git(args: list[str], repo_path: Path) -> str:
    """Run a git command in repo_path, return stdout as string."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as e:
        raise GitNotFoundError("git executable not found") from e

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr.lower() or "not a git repo" in stderr.lower():
            raise NotARepositoryError(f"{repo_path} is not a git repository")
        raise RuntimeError(f"git failed: {stderr}")

    return result.stdout


def find_deaths(repo_path: Path) -> list[Death]:
    """Find all deleted files that were never resurrected.

    Returns list of Death objects sorted by death_date, newest first.
    """
    repo_path = Path(repo_path).resolve()

    # 1. Files existing at HEAD
    head_files_out = _run_git(["ls-tree", "-r", "--name-only", "HEAD"], repo_path)
    head_files = set(line.strip() for line in head_files_out.splitlines() if line.strip())

    # 2. One git log call with custom format
    # COMMIT<sep>hash<sep>author<sep>author-date-iso<sep>subject
    # Then filenames (one per line) until next COMMIT marker
    sep = "\x1f"
    log_out = _run_git([
        "-c", "core.quotepath=off",
        "log", "--all",
        "-M", "--diff-filter=D", "--name-only",
        f"--pretty=COMMIT{sep}%H{sep}%an{sep}%aI{sep}%s",
    ], repo_path)

    deaths_by_path: dict[str, Death] = {}
    current_commit: str | None = None
    current_author: str | None = None
    current_date: datetime | None = None
    current_subject: str | None = None

    for line in log_out.splitlines():
        if line.startswith("COMMIT" + sep):
            # New commit header
            parts = line.split(sep)
            if len(parts) != 5:
                continue
            _, current_commit, current_author, date_str, current_subject = parts
            try:
                current_date = datetime.fromisoformat(date_str)
            except ValueError:
                current_date = None
        elif line.strip() and current_commit and current_date:
            # This is a deleted filename
            path = line.strip()
            if path in head_files:
                continue  # Resurrected, skip
            if path in deaths_by_path:
                continue  # Already recorded a more recent death
            if _is_noise(path):
                continue
            deaths_by_path[path] = Death(
                path=path,
                death_commit=current_commit,
                death_date=current_date,
                killer=current_author,
                death_message=current_subject,
            )

    # 6. Sort by death_date, newest first
    return sorted(deaths_by_path.values(), key=lambda d: d.death_date, reverse=True)


def _is_noise(path: str) -> bool:
    """Check if path matches any noise filter."""
    # Check extensions
    for ext in NOISE_EXTENSIONS:
        if path.endswith(ext):
            return True
    # Check exact filenames
    if path in NOISE_FILENAMES:
        return True
    # Check path prefixes/segments
    for prefix in NOISE_PATH_PREFIXES:
        if path.startswith(prefix) or f"/{prefix}" in path:
            return True
    return False