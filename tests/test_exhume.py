"""Tests for exhume module."""
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gravedigger.exhume import Death, find_deaths, NotARepositoryError, GitNotFoundError


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a throwaway git repo with deterministic config."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True, capture_output=True)

    # Set deterministic dates via env vars
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = "2024-01-15T12:00:00+00:00"
    env["GIT_COMMITTER_DATE"] = "2024-01-15T12:00:00+00:00"

    # Initial commit
    (repo / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo, check=True, capture_output=True, env=env)

    return repo


def _commit(repo: Path, message: str, date: str, *files: tuple[str, str]) -> str:
    """Create/update files and commit with given date. Returns commit hash."""
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = date
    env["GIT_COMMITTER_DATE"] = date

    for path, content in files:
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(content)

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True, env=env)
    hash_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo, check=True, capture_output=True, text=True, env=env
    )
    return hash_result.stdout.strip()


def _commit_delete(repo: Path, message: str, date: str, *paths: str) -> str:
    """Delete files and commit with given date. Returns commit hash."""
    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = date
    env["GIT_COMMITTER_DATE"] = date

    for path in paths:
        (repo / path).unlink(missing_ok=True)

    subprocess.run(["git", "add", "-u"], cwd=repo, check=True, capture_output=True, env=env)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True, env=env)
    hash_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo, check=True, capture_output=True, text=True, env=env
    )
    return hash_result.stdout.strip()


class TestFindDeaths:
    """Tests for find_deaths function."""

    def test_plain_deleted_file_found(self, git_repo: Path):
        """(a) A plainly deleted file is found with correct killer and message."""
        # Create and commit a file
        _commit(git_repo, "Add feature", "2024-01-16T12:00:00+00:00", ("feature.py", "print('hello')"))
        # Delete it
        _commit_delete(git_repo, "Remove feature", "2024-01-17T12:00:00+00:00", "feature.py")

        deaths = find_deaths(git_repo)

        assert len(deaths) == 1
        death = deaths[0]
        assert death.path == "feature.py"
        assert death.killer == "Test User"
        assert death.death_message == "Remove feature"
        assert death.death_date == datetime(2024, 1, 17, 12, 0, 0, tzinfo=timezone.utc)
        assert len(death.death_commit) == 40  # full SHA-1

    def test_renamed_file_not_reported(self, git_repo: Path):
        """(b) A renamed file is NOT reported as deleted."""
        _commit(git_repo, "Add old name", "2024-01-16T12:00:00+00:00", ("old_name.py", "x=1"))
        # Rename via git mv (simulated by delete + add in same commit)
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = "2024-01-17T12:00:00+00:00"
        env["GIT_COMMITTER_DATE"] = "2024-01-17T12:00:00+00:00"
        (git_repo / "old_name.py").unlink()
        (git_repo / "new_name.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "Rename file"], cwd=git_repo, check=True, capture_output=True, env=env)

        deaths = find_deaths(git_repo)

        # Should not report old_name.py as deleted (it was renamed)
        assert len(deaths) == 0

    def test_deleted_then_recreated_not_reported(self, git_repo: Path):
        """(c) A file deleted then recreated is NOT reported."""
        _commit(git_repo, "Add file", "2024-01-16T12:00:00+00:00", ("temp.txt", "temp"))
        _commit_delete(git_repo, "Delete file", "2024-01-17T12:00:00+00:00", "temp.txt")
        _commit(git_repo, "Recreate file", "2024-01-18T12:00:00+00:00", ("temp.txt", "temp again"))

        deaths = find_deaths(git_repo)

        assert len(deaths) == 0

    def test_deleted_recreated_deleted_again_reported_once_latest(self, git_repo: Path):
        """(d) File deleted, recreated, deleted again - reported once with LATEST death commit."""
        _commit(git_repo, "Add file", "2024-01-16T12:00:00+00:00", ("cycle.txt", "v1"))
        _commit_delete(git_repo, "First delete", "2024-01-17T12:00:00+00:00", "cycle.txt")
        _commit(git_repo, "Recreate", "2024-01-18T12:00:00+00:00", ("cycle.txt", "v2"))
        _commit_delete(git_repo, "Final delete", "2024-01-19T12:00:00+00:00", "cycle.txt")

        deaths = find_deaths(git_repo)

        assert len(deaths) == 1
        death = deaths[0]
        assert death.path == "cycle.txt"
        assert death.death_message == "Final delete"
        assert death.death_date == datetime(2024, 1, 19, 12, 0, 0, tzinfo=timezone.utc)

    def test_noise_files_skipped(self, git_repo: Path):
        """(e) Noise files (.png, lockfile, requirements/) are skipped."""
        _commit(git_repo, "Add noise", "2024-01-16T12:00:00+00:00",
                ("image.png", "binary"),
                ("package-lock.json", "{}"),
                ("requirements/dep.txt", "requests"))
        _commit_delete(git_repo, "Delete noise", "2024-01-17T12:00:00+00:00",
                       "image.png", "package-lock.json", "requirements/dep.txt")

        deaths = find_deaths(git_repo)

        assert len(deaths) == 0

    def test_non_ascii_filename_handled(self, git_repo: Path):
        """(f) Filename with non-ASCII characters is handled."""
        _commit(git_repo, "Add unicode", "2024-01-16T12:00:00+00:00", ("café.txt", "coffee"))
        _commit_delete(git_repo, "Delete unicode", "2024-01-17T12:00:00+00:00", "café.txt")

        deaths = find_deaths(git_repo)

        assert len(deaths) == 1
        assert deaths[0].path == "café.txt"

    def test_not_a_git_repo_raises_clear_error(self, tmp_path: Path):
        """(g) Non-git-repo folder raises NotARepositoryError."""
        not_a_repo = tmp_path / "not_a_repo"
        not_a_repo.mkdir()

        with pytest.raises(NotARepositoryError):
            find_deaths(not_a_repo)

    def test_sorted_newest_first(self, git_repo: Path):
        """Deaths sorted by death_date, newest first."""
        _commit(git_repo, "Add a", "2024-01-16T12:00:00+00:00", ("a.txt", "a"))
        _commit_delete(git_repo, "Delete a", "2024-01-17T12:00:00+00:00", "a.txt")
        _commit(git_repo, "Add b", "2024-01-18T12:00:00+00:00", ("b.txt", "b"))
        _commit_delete(git_repo, "Delete b", "2024-01-19T12:00:00+00:00", "b.txt")

        deaths = find_deaths(git_repo)

        assert len(deaths) == 2
        assert deaths[0].path == "b.txt"
        assert deaths[1].path == "a.txt"