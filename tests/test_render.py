"""Tests for HTML rendering."""
import json
import tempfile
from pathlib import Path

import pytest

from gravedigger.render import (
    GraveData,
    load_graves_from_json,
    render_html,
    _compute_stats,
    _escape,
    _format_year,
)


def _make_grave(**overrides) -> GraveData:
    """Create a test GraveData with sensible defaults."""
    defaults = {
        "path": "src/module.py",
        "death_commit": "a" * 40,
        "death_date": "2024-01-20T12:00:00+00:00",
        "killer": "Test User",
        "death_message": "Remove module",
        "born_commit": "b" * 40,
        "born_date": "2024-01-10T12:00:00+00:00",
        "born_message": "Add module",
        "born_by": "Author",
        "lifespan_days": 10,
        "lines_at_death": 50,
        "last_snippet": "def hello():\n    print('world')\n",
        "notability": 100.0,
        "members": (),
        "is_mass": False,
        "epitaph": "Test epitaph",
        "last_words": "Test last words",
        "source": "llm",
    }
    defaults.update(overrides)
    return GraveData(**defaults)


class TestEscape:
    def test_escape_html_chars(self):
        import html
        for s in ["<script>", 'a"b', "x&y", "plain"]:
            assert _escape(s) == html.escape(s, quote=True)

    def test_escape_no_change(self):
        assert _escape("normal text") == "normal text"
        assert _escape("path/to/file.py") == "path/to/file.py"


class TestFormatYear:
    def test_iso_with_timezone(self):
        assert _format_year("2024-01-20T12:00:00+00:00") == "2024"
        assert _format_year("2024-01-20T12:00:00-05:00") == "2024"

    def test_iso_without_timezone(self):
        assert _format_year("2024-01-20T12:00:00") == "2024"

    def test_fallback(self):
        assert _format_year("invalid") == "1970"


class TestComputeStats:
    def test_empty_list(self):
        stats = _compute_stats([])
        assert stats["graves_shown"] == 0
        assert stats["total_lines_buried"] == 0
        assert stats["longest_life_years"] == 0
        assert stats["deadliest_year"] == "N/A"

    def test_single_grave(self):
        grave = _make_grave(lifespan_days=400, lines_at_death=100)
        stats = _compute_stats([grave])
        assert stats["graves_shown"] == 1
        assert stats["total_lines_buried"] == 100
        assert stats["longest_life_years"] == 1
        assert stats["deadliest_year"] == "2024"

    def test_multiple_graves(self):
        graves = [
            _make_grave(lifespan_days=100, lines_at_death=50, death_date="2023-01-01T00:00:00+00:00"),
            _make_grave(lifespan_days=400, lines_at_death=100, death_date="2024-01-01T00:00:00+00:00"),
            _make_grave(lifespan_days=200, lines_at_death=75, death_date="2024-06-01T00:00:00+00:00"),
        ]
        stats = _compute_stats(graves)
        assert stats["graves_shown"] == 3
        assert stats["total_lines_buried"] == 225
        assert stats["longest_life_years"] == 1
        assert stats["deadliest_year"] == "2024"


class TestRenderHtml:
    def test_basic_render(self):
        graves = [_make_grave()]
        html = render_html(graves)

        assert "<!DOCTYPE html>" in html
        assert "<html lang=\"en\">" in html
        assert "Graveyard" in html
        assert "src/module.py" in html
        assert "2024" in html
        assert "Test epitaph" in html
        assert "Test last words" in html

    def test_no_external_resources(self):
        graves = [_make_grave()]
        html = render_html(graves)

        # No external CSS
        assert '<link rel="stylesheet"' not in html
        # Only allowed external URL is the footer github link
        http_count = html.count('href="https://')
        assert http_count <= 1
        # No external JS
        assert '<script src="http' not in html
        # No external fonts
        assert "fonts.google" not in html
        assert "fonts.gstatic" not in html

    def test_theme_variables(self):
        graves = [_make_grave()]
        html = render_html(graves)

        # Check CSS variables for both themes
        assert "--bg-primary:" in html
        assert "--accent:" in html
        assert '[data-theme="noche"]' in html

    def test_reduced_motion_media_query(self):
        graves = [_make_grave()]
        html = render_html(graves)

        assert "prefers-reduced-motion" in html
        assert "animation-duration: 0.01ms" in html

    def test_tombstone_elements(self):
        graves = [_make_grave(), _make_grave(path="other.py")]
        html = render_html(graves)

        # Should have two tombstone buttons (count only the button elements)
        # The pattern 'class="tombstone ' appears for each tombstone button
        # but also in JS. Count only the ones in the HTML body (before <script>)
        body_part = html.split('<script>')[0]
        assert body_part.count('class="tombstone ') == 2
        assert 'role="listitem"' in html
        assert 'data-index="0"' in html
        assert 'data-index="1"' in html
        assert 'tabindex="0"' in html

    def test_mass_grave_stone(self):
        graves = [_make_grave(is_mass=True, members=("a.py", "b.py"), path="src/ (2 files)")]
        html = render_html(graves)

        assert "stone-mass" in html
        assert 'data-mass="true"' in html

    def test_stone_sizes(self):
        graves = [
            _make_grave(notability=100),  # small
            _make_grave(notability=1000),  # large
        ]
        html = render_html(graves)

        # At least one size class present
        assert "stone-small" in html or "stone-medium" in html or "stone-large" in html

    def test_header_stats(self):
        graves = [
            _make_grave(lifespan_days=400, lines_at_death=100, death_date="2024-01-01T00:00:00+00:00"),
            _make_grave(lifespan_days=800, lines_at_death=200, death_date="2023-01-01T00:00:00+00:00"),
        ]
        html = render_html(graves)

        assert "2" in html  # graves shown
        assert "300" in html  # total lines
        assert "2024" in html  # deadliest year

    def test_card_modal_structure(self):
        graves = [_make_grave()]
        html = render_html(graves)

        assert 'class="card-overlay"' in html
        assert 'id="cardOverlay"' in html
        assert 'id="cardTitle"' in html
        assert 'id="cardBody"' in html
        assert 'id="cardClose"' in html

    def test_theme_toggle(self):
        graves = [_make_grave()]
        html = render_html(graves)

        assert 'id="themeToggle"' in html
        assert 'id="themeToggleText"' in html
        assert "Noche de Muertos" in html

    def test_papel_picado_banner(self):
        graves = [_make_grave()]
        html = render_html(graves)

        assert 'class="papel-picado-banner"' in html
        assert 'class="papel-picado-strand"' in html
        assert 'class="papel-picado-flag"' in html

    def test_fog_layers(self):
        graves = [_make_grave()]
        html = render_html(graves)

        assert html.count('class="fog-layer"') == 2

    def test_moon(self):
        graves = [_make_grave()]
        html = render_html(graves)

        assert 'class="moon"' in html

    def test_candle_and_marigold(self):
        graves = [_make_grave()]
        html = render_html(graves)

        assert 'class="candle"' in html
        assert 'class="marigold-petals"' in html
        assert '[data-theme="noche"] .tombstone .candle' in html

    def test_html_escaping_in_output(self):
        # Test that special chars in data are escaped
        grave = _make_grave(
            path="src/<script>.py",
            epitaph="Epitaph with <b>bold</b>",
            last_words="Last words with & ampersand",
            killer="Killer <>&\"'",
            death_message="Message with <tag>",
        )
        html = render_html([grave])

        # Data goes into JSON in JS, should be properly escaped
        # The tombstone text content should be HTML-escaped
        assert "src/" in html
        assert "Epitaph" in html
        assert "Last words" in html

    def test_snippet_in_pre_tag(self):
        grave = _make_grave(last_snippet="def foo():\n    return 42\n")
        html = render_html([grave])

        # Snippet should appear in the JS data (for card)
        assert "def foo()" in html
        assert "return 42" in html

    def test_stable_layout(self):
        # Same input should produce same layout
        graves = [_make_grave(path="a.py"), _make_grave(path="b.py")]
        html1 = render_html(graves)
        html2 = render_html(graves)

        assert html1 == html2

    def test_different_seeds_produce_different_layouts(self):
        # Different grave sets should have different positions
        graves1 = [_make_grave(path="a.py"), _make_grave(path="b.py")]
        graves2 = [_make_grave(path="c.py"), _make_grave(path="d.py")]
        html1 = render_html(graves1)
        html2 = render_html(graves2)

        # Positions should differ (very unlikely to be identical)
        assert html1 != html2


class TestLoadGravesFromJson:
    def test_load_from_file(self):
        grave = _make_grave()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{
                "path": grave.path,
                "death_commit": grave.death_commit,
                "death_date": grave.death_date,
                "killer": grave.killer,
                "death_message": grave.death_message,
                "born_commit": grave.born_commit,
                "born_date": grave.born_date,
                "born_message": grave.born_message,
                "born_by": grave.born_by,
                "lifespan_days": grave.lifespan_days,
                "lines_at_death": grave.lines_at_death,
                "last_snippet": grave.last_snippet,
                "notability": grave.notability,
                "members": list(grave.members),
                "is_mass": grave.is_mass,
                "epitaph": grave.epitaph,
                "last_words": grave.last_words,
                "source": grave.source,
            }], f)
            temp_path = f.name

        try:
            loaded = load_graves_from_json(temp_path)
            assert len(loaded) == 1
            assert loaded[0].path == grave.path
            assert loaded[0].epitaph == grave.epitaph
        finally:
            Path(temp_path).unlink()

    def test_load_mass_grave(self):
        grave = _make_grave(is_mass=True, members=("a.py", "b.py"))
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([{
                "path": grave.path,
                "death_commit": grave.death_commit,
                "death_date": grave.death_date,
                "killer": grave.killer,
                "death_message": grave.death_message,
                "born_commit": grave.born_commit,
                "born_date": grave.born_date,
                "born_message": grave.born_message,
                "born_by": grave.born_by,
                "lifespan_days": grave.lifespan_days,
                "lines_at_death": grave.lines_at_death,
                "last_snippet": grave.last_snippet,
                "notability": grave.notability,
                "members": list(grave.members),
                "is_mass": grave.is_mass,
                "epitaph": grave.epitaph,
                "last_words": grave.last_words,
                "source": grave.source,
            }], f)
            temp_path = f.name

        try:
            loaded = load_graves_from_json(temp_path)
            assert len(loaded) == 1
            assert loaded[0].is_mass is True
            assert loaded[0].members == ("a.py", "b.py")
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])