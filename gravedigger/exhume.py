"""Exhume deleted files from git history.

Finds files that were deleted and never resurrected, returning their
death metadata for tombstone rendering.
"""
from __future__ import annotations

import math
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

# Notability multiplier for code/documentation files
NOTABILITY_CODE_BONUS = 1.5


@dataclass(frozen=True)
class Death:
    """A file's death record."""
    path: str
    death_commit: str
    death_date: datetime
    killer: str
    death_message: str


@dataclass(frozen=True)
class Grave:
    """A file's complete life record."""
    path: str
    death_commit: str
    death_date: datetime
    killer: str
    death_message: str
    born_commit: str
    born_date: datetime
    born_message: str
    born_by: str
    lifespan_days: int
    lines_at_death: int
    last_snippet: str
    notability: float


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


def _run_git_bytes(args: list[str], repo_path: Path) -> bytes:
    """Run a git command in repo_path, return stdout as bytes."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_path,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise GitNotFoundError("git executable not found") from e

    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
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


def calculate_notability(lifespan_days: int, lines_at_death: int, is_code: bool) -> float:
    """Calculate notability score.

    Uses log1p(lines) so that a huge file doesn't dominate purely by size.
    A 1000-line file gets ~6.9x the base, a 100-line file gets ~4.6x,
    a 10-line file gets ~2.4x. The log compresses the range while still
    rewarding larger files. Code files (.py, .rst, .md) get a 1.5x bonus.
    """
    score = lifespan_days * math.log1p(lines_at_death)
    if is_code:
        score *= NOTABILITY_CODE_BONUS
    return score


def enrich(repo_path: Path, deaths: list[Death]) -> tuple[list[Grave], int]:
    """Enrich Death records into Graves with birth info and last content.

    Returns (graves, skipped_count) where skipped includes:
    - deaths with no findable birth
    - binary files (NUL in content)
    """
    repo_path = Path(repo_path).resolve()

    # Build death lookup by path
    deaths_by_path = {d.path: d for d in deaths}

    # 1. Single bulk log: HEAD history, oldest-first, with name-status and rename detection
    # Format: COMMIT<sep>hash<sep>author<sep>author-date-iso<sep>subject
    # Then name-status lines: A\tpath, M\tpath, D\tpath, R<score>\told\tnew
    sep = "\x1f"
    log_out = _run_git([
        "-c", "core.quotepath=off",
        "log", "HEAD",
        "-M", "--name-status",
        "--reverse",
        f"--pretty=COMMIT{sep}%H{sep}%an{sep}%aI{sep}%s",
    ], repo_path)

    # Parse the entire history, tracking events by line index
    # events: list of (index, commit, author, date, subject, status, path, new_path_for_rename)
    events: list[tuple[int, str, str, datetime, str, str, str, str | None]] = []
    current_commit: str | None = None
    current_author: str | None = None
    current_date: datetime | None = None
    current_subject: str | None = None

    for idx, line in enumerate(log_out.splitlines()):
        if line.startswith("COMMIT" + sep):
            parts = line.split(sep)
            if len(parts) != 5:
                continue
            _, current_commit, current_author, date_str, current_subject = parts
            try:
                current_date = datetime.fromisoformat(date_str)
            except ValueError:
                current_date = None
        elif line.strip() and current_commit and current_date:
            # name-status line
            parts = line.split("\t")
            if not parts:
                continue
            status = parts[0][0]  # First char: A, M, D, R, C
            if status == "A" and len(parts) >= 2:
                path = parts[1]
                events.append((idx, current_commit, current_author, current_date, current_subject, "A", path, None))
            elif status == "D" and len(parts) >= 2:
                path = parts[1]
                events.append((idx, current_commit, current_author, current_date, current_subject, "D", path, None))
            elif status == "R" and len(parts) >= 3:
                old_path = parts[1]
                new_path = parts[2]
                # Treat as death of old, birth of new
                events.append((idx, current_commit, current_author, current_date, current_subject, "D", old_path, None))
                events.append((idx, current_commit, current_author, current_date, current_subject, "A", new_path, None))
            # Ignore M (modify) and C (copy) and others

    # 2. For each death, find the LAST birth (A event for that path) BEFORE the death's D event
    # Build death positions
    death_positions: dict[str, int] = {}
    for idx, (_, commit, _, _, _, status, path, _) in enumerate(events):
        if status == "D" and path in deaths_by_path:
            death_positions[path] = idx

    # Find births
    births: dict[str, tuple[str, datetime, str, str]] = {}  # path -> (born_commit, born_date, born_message, born_by)
    for idx, (_, commit, author, date, subject, status, path, _) in enumerate(events):
        if status == "A" and path in deaths_by_path:
            death_idx = death_positions.get(path)
            if death_idx is not None and idx < death_idx:
                # This birth is before the death, record it (will overwrite with later ones)
                births[path] = (commit, date, subject, author)

    # 3. For each death, read content at parent of death commit
    graves: list[Grave] = []
    skipped = 0

    for death in deaths:
        path = death.path

        # Check if we found a birth
        birth_info = births.get(path)
        if not birth_info:
            skipped += 1
            continue

        born_commit, born_date, born_message, born_by = birth_info

        # Read file content at death_commit^:path
        try:
            content_bytes = _run_git_bytes(["show", f"{death.death_commit}^:{path}"], repo_path)
        except RuntimeError:
            skipped += 1
            continue

        # Binary check: NUL byte
        if b"\x00" in content_bytes:
            skipped += 1
            continue

        content = content_bytes.decode("utf-8", errors="replace")
        lines = content.splitlines()
        lines_at_death = len(lines)
        snippet = "\n".join(lines[:40])
        if len(snippet) > 1500:
            snippet = snippet[:1500]

        lifespan_days = (death.death_date - born_date).days
        if lifespan_days < 0:
            lifespan_days = 0

        is_code = path.endswith((".py", ".rst", ".md"))
        notability = calculate_notability(lifespan_days, lines_at_death, is_code)

        graves.append(Grave(
            path=path,
            death_commit=death.death_commit,
            death_date=death.death_date,
            killer=death.killer,
            death_message=death.death_message,
            born_commit=born_commit,
            born_date=born_date,
            born_message=born_message,
            born_by=born_by,
            lifespan_days=lifespan_days,
            lines_at_death=lines_at_death,
            last_snippet=snippet,
            notability=notability,
        ))

    # 4. Sort by notability, highest first
    graves.sort(key=lambda g: g.notability, reverse=True)
    return graves, skipped


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