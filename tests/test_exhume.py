"""Tests for exhume module."""
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from gravedigger.exhume import Death, Grave, find_deaths, enrich, exhume, _merge_mass_graves, _apply_diversity_cap, NotARepositoryError, GitNotFoundError, MAX_PER_DIRECTORY, MASS_GRAVE_MIN, FOUNDER_WINDOW_DAYS, FOUNDER_BONUS


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


class TestMassGraves:
    """Tests for mass grave merging."""

    def test_five_deaths_same_commit_become_mass_grave(self, git_repo: Path):
        """(a) 5 deaths in one commit become one mass grave with 5 members."""
        # Create 5 files
        files = [(f"file{i}.txt", f"content{i}") for i in range(5)]
        _commit(git_repo, "Add 5 files", "2024-01-10T12:00:00+00:00", *files)
        # Delete all 5 in one commit
        _commit_delete(git_repo, "Delete all 5", "2024-01-20T12:00:00+00:00", *[f"file{i}.txt" for i in range(5)])

        deaths = find_deaths(git_repo)
        graves, _ = enrich(git_repo, deaths)
        # After enrich, we have 5 graves with same death_commit
        # Now test merge
        from gravedigger.exhume import _merge_mass_graves
        merged = _merge_mass_graves(graves)

        assert len(merged) == 1
        g = merged[0]
        assert g.is_mass is True
        assert len(g.members) == 5
        assert "file0.txt" in g.members
        assert "file4.txt" in g.members
        # Top-level files (no common directory) get "N files killed by: ..." name
        assert g.path.startswith("5 files killed by: Delete all 5")

    def test_four_deaths_same_commit_not_merged(self, git_repo: Path):
        """4 deaths in one commit do NOT become a mass grave."""
        files = [(f"file{i}.txt", f"content{i}") for i in range(4)]
        _commit(git_repo, "Add 4 files", "2024-01-10T12:00:00+00:00", *files)
        _commit_delete(git_repo, "Delete all 4", "2024-01-20T12:00:00+00:00", *[f"file{i}.txt" for i in range(4)])

        deaths = find_deaths(git_repo)
        graves, _ = enrich(git_repo, deaths)
        from gravedigger.exhume import _merge_mass_graves
        merged = _merge_mass_graves(graves)

        assert len(merged) == 4
        for g in merged:
            assert g.is_mass is False

    def test_mass_grave_common_directory(self, git_repo: Path):
        """Mass grave with files in same subdirectory gets common dir in path."""
        files = [(f"src/module{i}.py", f"content{i}") for i in range(5)]
        _commit(git_repo, "Add 5 files", "2024-01-10T12:00:00+00:00", *files)
        _commit_delete(git_repo, "Delete all 5", "2024-01-20T12:00:00+00:00", *[f"src/module{i}.py" for i in range(5)])

        deaths = find_deaths(git_repo)
        graves, _ = enrich(git_repo, deaths)
        from gravedigger.exhume import _merge_mass_graves
        merged = _merge_mass_graves(graves)

        assert len(merged) == 1
        g = merged[0]
        assert g.path == "src/ (5 files)"


class TestDiversityCap:
    """Tests for per-directory diversity cap."""

    def test_cap_limits_folder_to_max(self, git_repo: Path):
        """(b) Cap limits a folder to MAX_PER_DIRECTORY graves."""
        # Create 5 files in docs/
        files = [(f"docs/file{i}.txt", f"content{i}") for i in range(5)]
        _commit(git_repo, "Add 5 files", "2024-01-10T12:00:00+00:00", *files)
        _commit_delete(git_repo, "Delete all 5", "2024-01-20T12:00:00+00:00", *[f"docs/file{i}.txt" for i in range(5)])

        deaths = find_deaths(git_repo)
        graves, _ = enrich(git_repo, deaths)
        from gravedigger.exhume import _apply_diversity_cap
        kept, removed = _apply_diversity_cap(graves)

        assert len(kept) == MAX_PER_DIRECTORY
        assert len(removed) == 2
        # All kept should be from docs/
        for g in kept:
            assert g.path.startswith("docs/")

    def test_top_level_files_separate_groups(self, git_repo: Path):
        """(c) Top-level files are not capped by each other (each is own group)."""
        # Create 5 top-level files
        files = [(f"file{i}.txt", f"content{i}") for i in range(5)]
        _commit(git_repo, "Add 5 files", "2024-01-10T12:00:00+00:00", *files)
        _commit_delete(git_repo, "Delete all 5", "2024-01-20T12:00:00+00:00", *[f"file{i}.txt" for i in range(5)])

        deaths = find_deaths(git_repo)
        graves, _ = enrich(git_repo, deaths)
        from gravedigger.exhume import _apply_diversity_cap
        kept, removed = _apply_diversity_cap(graves)

        # Each top-level file is its own group, so all 5 should be kept
        assert len(kept) == 5
        assert len(removed) == 0


class TestExhume:
    """Tests for full exhume pipeline."""

    def test_backfill_when_cap_removes_too_many(self, git_repo: Path):
        """(d) Backfill: when cap leaves fewer than limit, fill from removed."""
        # Create 5 files in docs/ deleted in DIFFERENT commits (no mass grave)
        # and 2 top-level files deleted in different commits
        for i in range(5):
            _commit(git_repo, f"Add docs/file{i}.txt", "2024-01-10T12:00:00+00:00", (f"docs/file{i}.txt", f"content{i}"))
            _commit_delete(git_repo, f"Delete docs/file{i}.txt", f"2024-01-{20+i}T12:00:00+00:00", f"docs/file{i}.txt")
        for i in range(2):
            _commit(git_repo, f"Add top{i}.txt", "2024-01-10T12:00:00+00:00", (f"top{i}.txt", f"content{i}"))
            _commit_delete(git_repo, f"Delete top{i}.txt", f"2024-01-{25+i}T12:00:00+00:00", f"top{i}.txt")

        # Use limit=10 to trigger backfill
        result = exhume(git_repo, limit=10)

        # Should get 3 from docs/ + 2 top-level = 5, but backfill adds 2 more from removed docs/
        # Total should be min(7, limit) = 7
        assert len(result) == 7

    def test_exhume_returns_limit(self, git_repo: Path):
        """(e) exhume returns at most limit graves."""
        # Create 10 files deleted in DIFFERENT commits (no mass grave)
        for i in range(10):
            _commit(git_repo, f"Add file{i}.txt", "2024-01-10T12:00:00+00:00", (f"file{i}.txt", f"content{i}"))
            _commit_delete(git_repo, f"Delete file{i}.txt", f"2024-01-{20+i}T12:00:00+00:00", f"file{i}.txt")

        result = exhume(git_repo, limit=5)
        assert len(result) == 5

        result = exhume(git_repo, limit=100)
        assert len(result) == 10  # only 10 exist

    def test_five_top_level_files_survive_cap(self, git_repo: Path):
        """(f) Five top-level files deleted in DIFFERENT commits all survive the cap (separate groups)."""
        for i in range(5):
            _commit(git_repo, f"Add file{i}.txt", "2024-01-10T12:00:00+00:00", (f"file{i}.txt", f"content{i}"))
            _commit_delete(git_repo, f"Delete file{i}.txt", f"2024-01-{20+i}T12:00:00+00:00", f"file{i}.txt")

        result = exhume(git_repo, limit=10)
        assert len(result) == 5
        # All should be top-level files (no '/')
        for g in result:
            assert '/' not in g.path


class TestExport:
    """Tests for JSON export."""

    def test_json_roundtrip(self, git_repo: Path):
        """(g) JSON round-trips: json.loads works and has expected keys and ISO dates."""
        _commit(git_repo, "Add file", "2024-01-10T12:00:00+00:00", ("test.py", "print('hello')"))
        _commit_delete(git_repo, "Delete file", "2024-01-20T12:00:00+00:00", "test.py")

        from gravedigger.exhume import exhume
        from gravedigger.export import graves_to_json
        import json

        graves = exhume(git_repo, limit=10)
        json_str = graves_to_json(graves)
        data = json.loads(json_str)

        assert len(data) == 1
        g = data[0]
        assert g["path"] == "test.py"
        assert "death_date" in g
        assert "born_date" in g
        # Dates should be ISO strings
        assert "T" in g["death_date"]
        assert "T" in g["born_date"]
        # Members should be list
        assert isinstance(g["members"], list)
        # is_mass should be bool
        assert isinstance(g["is_mass"], bool)


class TestFounderBonus:
    """Tests for founder bonus."""

    def test_founder_bonus_applied_within_window(self, git_repo: Path):
        """(a) Grave born within 30 days of root commit gets FOUNDER_BONUS."""
        # Root commit is 2024-01-15 (from fixture)
        # Add file 10 days later (within 30 days)
        _commit(git_repo, "Add founder file", "2024-01-20T12:00:00+00:00", ("founder.py", "print('founder')"))
        _commit_delete(git_repo, "Delete founder", "2024-02-01T12:00:00+00:00", "founder.py")

        # Also add a non-founder file born later
        _commit(git_repo, "Add late file", "2024-02-20T12:00:00+00:00", ("late.py", "print('late')"))
        _commit_delete(git_repo, "Delete late", "2024-03-01T12:00:00+00:00", "late.py")

        result = exhume(git_repo, limit=10)

        # Find both graves
        founder_grave = next(g for g in result if g.path == "founder.py")
        late_grave = next(g for g in result if g.path == "late.py")

        # Founder: born 2024-01-20, died 2024-02-01 = 12 days
        # Late: born 2024-02-20, died 2024-03-01 = 10 days
        expected_founder_notability = 12 * math.log1p(1) * 1.5 * FOUNDER_BONUS  # Python + founder
        expected_late_notability = 10 * math.log1p(1) * 1.5  # Python only

        assert abs(founder_grave.notability - expected_founder_notability) < 0.1
        assert abs(late_grave.notability - expected_late_notability) < 0.1
        # Founder should rank higher
        assert founder_grave.notability > late_grave.notability

    def test_founder_bonus_not_applied_outside_window(self, git_repo: Path):
        """File born after FOUNDER_WINDOW_DAYS does not get bonus."""
        # Root is 2024-01-15, this is born 60 days later (outside 30-day window)
        _commit(git_repo, "Add late file", "2024-03-15T12:00:00+00:00", ("late2.py", "print('late')"))
        _commit_delete(git_repo, "Delete late2", "2024-04-01T12:00:00+00:00", "late2.py")

        result = exhume(git_repo, limit=10)

        late_grave = next(g for g in result if g.path == "late2.py")
        # Should not have founder bonus
        expected_notability = 17 * math.log1p(1) * 1.5  # lifespan 17 days
        assert abs(late_grave.notability - expected_notability) < 0.1


class TestMassGraveNaming:
    """Tests for mass grave naming."""

    def test_mass_grave_common_directory_keeps_dir_name(self, git_repo: Path):
        """(b) Mass grave in one directory keeps 'dir/ (N files)'."""
        files = [(f"src/module{i}.py", f"content{i}") for i in range(5)]
        _commit(git_repo, "Add 5 files", "2024-01-10T12:00:00+00:00", *files)
        _commit_delete(git_repo, "Delete all 5", "2024-01-20T12:00:00+00:00", *[f"src/module{i}.py" for i in range(5)])

        deaths = find_deaths(git_repo)
        graves, _ = enrich(git_repo, deaths)
        from gravedigger.exhume import _merge_mass_graves
        merged = _merge_mass_graves(graves)

        assert len(merged) == 1
        g = merged[0]
        assert g.path == "src/ (5 files)"

    def test_mass_grave_across_directories_gets_killed_by_name(self, git_repo: Path):
        """(c) Mass grave across two top-level directories gets 'N files killed by: ...' name."""
        # Files in two different top-level directories
        files = [(f"src/a{i}.py", f"content{i}") for i in range(3)]
        files += [(f"docs/b{i}.py", f"content{i}") for i in range(2)]
        _commit(git_repo, "Add files", "2024-01-10T12:00:00+00:00", *files)
        _commit_delete(git_repo, "Mass deletion event", "2024-01-20T12:00:00+00:00", *[f"src/a{i}.py" for i in range(3)], *[f"docs/b{i}.py" for i in range(2)])

        deaths = find_deaths(git_repo)
        graves, _ = enrich(git_repo, deaths)
        from gravedigger.exhume import _merge_mass_graves
        merged = _merge_mass_graves(graves)

        assert len(merged) == 1
        g = merged[0]
        assert g.is_mass is True
        assert g.path.startswith("5 files killed by: Mass deletion")
        assert "src" not in g.path and "docs" not in g.path


import math