"""Tests for exhume module."""
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gravedigger.exhume import Death, Grave, find_deaths, enrich, NotARepositoryError, GitNotFoundError


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


class TestEnrich:
    """Tests for enrich function."""

    def test_plain_file_born_died_lifespan_correct(self, git_repo: Path):
        """(a) Born/died dates and lifespan_days correct for a plain file."""
        _commit(git_repo, "Add file", "2024-01-10T12:00:00+00:00", ("plain.txt", "content"))
        _commit_delete(git_repo, "Delete file", "2024-01-20T12:00:00+00:00", "plain.txt")

        deaths = find_deaths(git_repo)
        graves, skipped = enrich(git_repo, deaths)

        assert skipped == 0
        assert len(graves) == 1
        g = graves[0]
        assert g.path == "plain.txt"
        assert g.born_date == datetime(2024, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
        assert g.death_date == datetime(2024, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert g.lifespan_days == 10

    def test_deleted_recreated_deleted_second_birth(self, git_repo: Path):
        """(b) File deleted, recreated, deleted again has the SECOND birth."""
        _commit(git_repo, "Add v1", "2024-01-10T12:00:00+00:00", ("cycle.txt", "v1"))
        _commit_delete(git_repo, "First delete", "2024-01-15T12:00:00+00:00", "cycle.txt")
        _commit(git_repo, "Recreate v2", "2024-01-16T12:00:00+00:00", ("cycle.txt", "v2"))
        _commit_delete(git_repo, "Final delete", "2024-01-20T12:00:00+00:00", "cycle.txt")

        deaths = find_deaths(git_repo)
        graves, skipped = enrich(git_repo, deaths)

        assert skipped == 0
        assert len(graves) == 1
        g = graves[0]
        assert g.path == "cycle.txt"
        # Birth should be the recreate commit (2024-01-16), not the original (2024-01-10)
        assert g.born_date == datetime(2024, 1, 16, 12, 0, 0, tzinfo=timezone.utc)
        assert g.lifespan_days == 4

    def test_born_by_rename(self, git_repo: Path):
        """(c) File born by rename has the rename commit as its birth."""
        _commit(git_repo, "Add old", "2024-01-10T12:00:00+00:00", ("old.txt", "content"))
        # Rename via git mv (delete old + add new in same commit)
        env = os.environ.copy()
        env["GIT_AUTHOR_DATE"] = "2024-01-15T12:00:00+00:00"
        env["GIT_COMMITTER_DATE"] = "2024-01-15T12:00:00+00:00"
        (git_repo / "old.txt").unlink()
        (git_repo / "new.txt").write_text("content")
        subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "Rename old to new"], cwd=git_repo, check=True, capture_output=True, env=env)
        _commit_delete(git_repo, "Delete new", "2024-01-20T12:00:00+00:00", "new.txt")

        deaths = find_deaths(git_repo)
        graves, skipped = enrich(git_repo, deaths)

        assert skipped == 0
        assert len(graves) == 1
        g = graves[0]
        assert g.path == "new.txt"
        # Birth should be the rename commit (2024-01-15), not the original add (2024-01-10)
        assert g.born_date == datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert g.born_message == "Rename old to new"

    def test_last_snippet_before_deletion(self, git_repo: Path):
        """(d) last_snippet is content before deletion, not empty and not from deleting commit."""
        _commit(git_repo, "Add file", "2024-01-10T12:00:00+00:00", ("snippet.txt", "line1\nline2\nline3"))
        _commit_delete(git_repo, "Delete file", "2024-01-20T12:00:00+00:00", "snippet.txt")

        deaths = find_deaths(git_repo)
        graves, skipped = enrich(git_repo, deaths)

        assert skipped == 0
        assert len(graves) == 1
        g = graves[0]
        assert g.lines_at_death == 3
        assert "line1" in g.last_snippet
        assert "line2" in g.last_snippet
        assert "line3" in g.last_snippet
        assert g.last_snippet != ""

    def test_binary_file_skipped(self, git_repo: Path):
        """(e) Binary file is skipped and counted."""
        # Create a file with NUL byte
        _commit(git_repo, "Add binary", "2024-01-10T12:00:00+00:00", ("binary.dat", "hello\x00world"))
        _commit_delete(git_repo, "Delete binary", "2024-01-20T12:00:00+00:00", "binary.dat")

        deaths = find_deaths(git_repo)
        graves, skipped = enrich(git_repo, deaths)

        assert skipped == 1
        assert len(graves) == 0

    def test_older_bigger_outranks_younger_smaller(self, git_repo: Path):
        """(f) Older, bigger file outranks younger, smaller one by notability."""
        # Old file, many lines, long lifespan
        _commit(git_repo, "Add big", "2024-01-01T12:00:00+00:00", ("big.txt", "\n".join([f"line{i}" for i in range(100)])))
        _commit_delete(git_repo, "Delete big", "2024-01-30T12:00:00+00:00", "big.txt")
        # Young file, few lines, short lifespan
        _commit(git_repo, "Add small", "2024-01-28T12:00:00+00:00", ("small.txt", "only one line"))
        _commit_delete(git_repo, "Delete small", "2024-01-29T12:00:00+00:00", "small.txt")

        deaths = find_deaths(git_repo)
        graves, skipped = enrich(git_repo, deaths)

        assert skipped == 0
        assert len(graves) == 2
        # big.txt should have higher notability (29 days * log1p(100) ≈ 29*4.6 ≈ 133)
        # vs small.txt (1 day * log1p(1) ≈ 0.7)
        assert graves[0].path == "big.txt"
        assert graves[0].notability > graves[1].notability

    def test_same_timestamp_birth_death(self, git_repo: Path):
        """(g) File whose birth and death have same timestamp still finds correct birth."""
        # Same timestamp for birth and death
        _commit(git_repo, "Add and delete same day", "2024-01-15T12:00:00+00:00", ("same_day.txt", "content"))
        _commit_delete(git_repo, "Delete same day", "2024-01-15T12:00:00+00:00", "same_day.txt")

        deaths = find_deaths(git_repo)
        graves, skipped = enrich(git_repo, deaths)

        assert skipped == 0
        assert len(graves) == 1
        g = graves[0]
        assert g.path == "same_day.txt"
        assert g.born_date == g.death_date
        assert g.lifespan_days == 0