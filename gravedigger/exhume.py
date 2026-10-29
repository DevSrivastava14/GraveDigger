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
from typing import Iterable


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

# Notability multiplier for Python files only
NOTABILITY_CODE_BONUS = 1.5

# Diversity cap: max graves per top-level directory
MAX_PER_DIRECTORY = 3

# Mass grave threshold: merge N+ deaths in same commit
MASS_GRAVE_MIN = 5

# Founder bonus: files born within FOUNDER_WINDOW_DAYS of the repo's
# first commit get FOUNDER_BONUS multiplier. The first files of a
# repo are its ancestors, whatever their lifespan.
FOUNDER_WINDOW_DAYS = 30
FOUNDER_BONUS = 3.0


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
    members: tuple[str, ...] = ()
    is_mass: bool = False


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


def _get_root_commit_date(repo_path: Path) -> datetime:
    """Return the author date of the repo's earliest commit (root)."""
    out = _run_git([
        "log", "--max-parents=0", "--format=%aI",
    ], repo_path)
    # Take the earliest if multiple roots
    dates = [line.strip() for line in out.splitlines() if line.strip()]
    if not dates:
        raise RuntimeError("no root commit found")
    return min(datetime.fromisoformat(d) for d in dates)


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


def calculate_notability(lifespan_days: int, lines_at_death: int, is_python: bool, is_founder: bool = False) -> float:
    """Calculate notability score.

    Uses log1p(lines) so that a huge file doesn't dominate purely by size.
    A 1000-line file gets ~6.9x the base, a 100-line file gets ~4.6x,
    a 10-line file gets ~2.4x. The log compresses the range while still
    rewarding larger files. Python files (.py) get a 1.5x bonus.
    Founder files (born within FOUNDER_WINDOW_DAYS of the root commit)
    get a FOUNDER_BONUS multiplier because they are the repo's ancestors.
    """
    score = lifespan_days * math.log1p(lines_at_death)
    if is_python:
        score *= NOTABILITY_CODE_BONUS
    if is_founder:
        score *= FOUNDER_BONUS
    return score


def _top_level_group(path: str) -> str:
    """Return the cap group key for a path.

    - Paths containing '/' are grouped by their top-level directory (before first '/')
    - Top-level files (no '/') each get their own unique group (the full path)
    Git paths always use '/', even on Windows.
    """
    if '/' in path:
        return path.split('/')[0]
    return path  # unique group per top-level file


def _mass_grave_cap_group(path: str, members: tuple[str, ...]) -> str:
    """Return the cap group for a mass grave.

    If members share a common top-level directory, use that.
    Otherwise, the mass grave is its own group.
    """
    # Check if all members share the same top-level directory
    top_dirs = {m.split('/')[0] for m in members if '/' in m}
    if len(top_dirs) == 1:
        return top_dirs.pop()
    return path  # own group


def _deepest_common_dir(paths: Iterable[str]) -> str:
    """Return the deepest common directory of all paths, or '' if none."""
    paths_list = list(paths)
    if not paths_list:
        return ''
    # Split into components
    split_paths = [p.split('/') for p in paths_list]
    # Find common prefix
    common = []
    for components in zip(*split_paths):
        if len(set(components)) == 1:
            common.append(components[0])
        else:
            break
    if not common:
        return ''
    return '/'.join(common)


def _merge_mass_graves(graves: list[Grave]) -> list[Grave]:
    """Merge graves with same death_commit if count >= MASS_GRAVE_MIN.

    Returns new list with mass graves merged.
    """
    # Group by death_commit
    by_commit: dict[str, list[Grave]] = {}
    for g in graves:
        by_commit.setdefault(g.death_commit, []).append(g)

    result: list[Grave] = []
    for commit, group in by_commit.items():
        if len(group) >= MASS_GRAVE_MIN:
            # Create mass grave
            # Most notable member provides born_* and snippet
            best = max(group, key=lambda g: g.notability)
            members = tuple(sorted(g.path for g in group))
            common_dir = _deepest_common_dir(members)
            if common_dir:
                mass_path = f"{common_dir}/ ({len(members)} files)"
            else:
                # Truncate death message to 70 chars
                msg = best.death_message[:70]
                mass_path = f"{len(members)} files killed by: {msg}"
            # Cap group for mass grave
            cap_group = _mass_grave_cap_group(mass_path, members)
            # Use max lifespan, max notability
            max_lifespan = max(g.lifespan_days for g in group)
            max_notability = max(g.notability for g in group)

            result.append(Grave(
                path=mass_path,
                death_commit=commit,
                death_date=best.death_date,
                killer=best.killer,
                death_message=best.death_message,
                born_commit=best.born_commit,
                born_date=best.born_date,
                born_message=best.born_message,
                born_by=best.born_by,
                lifespan_days=max_lifespan,
                lines_at_death=best.lines_at_death,
                last_snippet=best.last_snippet,
                notability=max_notability,
                members=members,
                is_mass=True,
            ))
        else:
            result.extend(group)
    return result


def _apply_diversity_cap(graves: list[Grave]) -> list[Grave]:
    """Apply MAX_PER_DIRECTORY cap per top-level directory.

    Walks graves in notability order, keeps at most MAX_PER_DIRECTORY per group.
    Returns (kept, removed) where removed are the excess graves in notability order.
    """
    counts: dict[str, int] = {}
    kept: list[Grave] = []
    removed: list[Grave] = []

    for g in graves:
        if g.is_mass:
            group = _mass_grave_cap_group(g.path, g.members)
        else:
            group = _top_level_group(g.path)
        if counts.get(group, 0) < MAX_PER_DIRECTORY:
            kept.append(g)
            counts[group] = counts.get(group, 0) + 1
        else:
            removed.append(g)

    return kept, removed


def exhume(repo_path: Path, limit: int = 30) -> list[Grave]:
    """Full pipeline: find deaths -> enrich -> mass-grave merge -> cap -> backfill -> limit.

    Returns top `limit` graves.
    """
    repo_path = Path(repo_path).resolve()

    # Get root commit date for founder bonus
    root_date = _get_root_commit_date(repo_path)

    deaths = find_deaths(repo_path)
    graves, _ = enrich(repo_path, deaths, root_date)

    # Mass grave merge (before cap)
    graves = _merge_mass_graves(graves)
    # Sort by notability after merge
    graves.sort(key=lambda g: g.notability, reverse=True)

    # Apply diversity cap
    kept, removed = _apply_diversity_cap(graves)

    # Backfill: if fewer than limit kept, fill from removed (highest notability first)
    # This ensures we return `limit` graves whenever enough exist.
    if len(kept) < limit:
        need = limit - len(kept)
        kept.extend(removed[:need])

    return kept[:limit]


def enrich(repo_path: Path, deaths: list[Death], root_date: datetime | None = None) -> tuple[list[Grave], int]:
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

        is_python = path.endswith(".py")
        is_founder = root_date is not None and (born_date - root_date).days <= FOUNDER_WINDOW_DAYS
        notability = calculate_notability(lifespan_days, lines_at_death, is_python, is_founder)

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