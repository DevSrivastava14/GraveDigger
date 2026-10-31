"""HTML rendering for the graveyard.

Generates a single self-contained HTML file with inline CSS and JS.
No external dependencies, no CDN, no external fonts.
"""
from __future__ import annotations

import html
import json
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class GraveData:
    """A grave with epitaph data for rendering."""
    path: str
    death_commit: str
    death_date: str  # ISO string
    killer: str
    death_message: str
    born_commit: str
    born_date: str  # ISO string
    born_message: str
    born_by: str
    lifespan_days: int
    lines_at_death: int
    last_snippet: str
    notability: float
    members: tuple[str, ...]
    is_mass: bool
    epitaph: str
    last_words: str
    source: str


def _parse_date(date_str: str) -> datetime:
    """Parse ISO date string, handling various formats."""
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        pass
    return datetime(1970, 1, 1)


def _escape(s: str) -> str:
    """HTML-escape a string."""
    return html.escape(s, quote=True)


def _format_year(date_str: str) -> str:
    """Extract year from ISO date string."""
    dt = _parse_date(date_str)
    return str(dt.year)


def _compute_stats(graves: list[GraveData]) -> dict[str, Any]:
    """Compute header statistics from grave data."""
    if not graves:
        return {
            "graves_shown": 0,
            "total_lines_buried": 0,
            "longest_life_years": 0,
            "deadliest_year": "N/A",
        }

    total_lines = sum(g.lines_at_death for g in graves)
    longest_life = max(g.lifespan_days for g in graves)
    longest_life_years = longest_life // 365

    year_counts: dict[int, int] = {}
    for g in graves:
        dt = _parse_date(g.death_date)
        year = dt.year
        year_counts[year] = year_counts.get(year, 0) + 1

    deadliest_year = max(year_counts.items(), key=lambda x: x[1])[0] if year_counts else "N/A"

    return {
        "graves_shown": len(graves),
        "total_lines_buried": total_lines,
        "longest_life_years": longest_life_years,
        "deadliest_year": str(deadliest_year),
    }


def _seeded_random(seed: str) -> random.Random:
    """Create a seeded random generator from a string."""
    return random.Random(hash(seed) & 0xFFFFFFFFFFFFFFFF)


def _generate_stone_position(index: int, total: int, rng: random.Random) -> dict[str, Any]:
    """Generate a stable random position and style for a tombstone."""
    col = index % 5
    row = index // 5

    base_x = 10 + col * 180
    base_y = 20 + row * 200

    jitter_x = rng.uniform(-30, 30)
    jitter_y = rng.uniform(-20, 20)

    tilt = rng.uniform(-5, 5)

    return {
        "left": f"{base_x + jitter_x}px",
        "top": f"{base_y + jitter_y}px",
        "tilt": f"{tilt:.1f}deg",
        "index": index,
    }


def _stone_shape_class(is_mass: bool, notability: float, max_notability: float) -> str:
    """Determine stone shape/size class based on notability and mass grave status."""
    if is_mass:
        return "stone-mass"
    if max_notability > 0:
        ratio = notability / max_notability
        if ratio > 0.7:
            return "stone-large"
        elif ratio > 0.3:
            return "stone-medium"
    return "stone-small"


# Static CSS and JavaScript (not f-strings, so no escaping issues)
_STATIC_CSS = """
/* ===== CSS Variables for Themes ===== */
:root {
  /* Spooky Night (default) */
  --bg-primary: #0d0d12;
  --bg-secondary: #15151f;
  --fg-primary: #e8e0d0;
  --fg-muted: #8a8070;
  --stone-base: #2a2520;
  --stone-highlight: #3d3530;
  --stone-shadow: #0a0806;
  --accent: #c9a84c;
  --accent-glow: #e8c860;
  --fog-color: rgba(20, 18, 15, 0.8);
  --moon-color: #f5f0e0;
  --candle-flame: #ffaa33;
  --marigold: #ff8c00;
  --papel-picado: #e83e8c;
  --text-shadow: 0 0 10px rgba(0,0,0,0.8);
}

[data-theme="noche"] {
  /* Noche de Muertos */
  --bg-primary: #1a0a0a;
  --bg-secondary: #2d1010;
  --fg-primary: #fff8e8;
  --fg-muted: #c8b8a0;
  --stone-base: #3d2018;
  --stone-highlight: #5a3020;
  --stone-shadow: #0d0503;
  --accent: #ff8c00;
  --accent-glow: #ffaa33;
  --fog-color: rgba(40, 10, 5, 0.7);
  --moon-color: #ffcc66;
  --candle-flame: #ff6600;
  --marigold: #ffcc00;
  --papel-picado: #ff3399;
  --text-shadow: 0 0 15px rgba(255, 140, 0, 0.3);
}

/* ===== Reset & Base ===== */
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body {
  height: 100%;
  overflow-x: hidden;
}

body {
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg-primary);
  color: var(--fg-primary);
  line-height: 1.5;
  min-height: 100vh;
  transition: background-color 0.5s ease, color 0.5s ease;
}

/* ===== Reduced Motion ===== */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }

  .fog-layer,
  .moon-glow,
  .candle-flicker,
  .papel-picado-banner {
    animation: none !important;
  }
}

/* ===== Layout ===== */
.graveyard {
  position: relative;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ===== Header ===== */
.header {
  position: relative;
  z-index: 10;
  padding: 1.5rem 1rem;
  text-align: center;
  border-bottom: 1px solid var(--stone-shadow);
  background: linear-gradient(180deg, var(--bg-secondary), transparent);
}

.header h1 {
  font-size: clamp(1.5rem, 4vw, 2.5rem);
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  text-shadow: var(--text-shadow);
  margin-bottom: 0.5rem;
}

.header .subtitle {
  font-size: 0.875rem;
  color: var(--fg-muted);
  font-style: italic;
}

.stats {
  display: flex;
  justify-content: center;
  gap: 1.5rem;
  flex-wrap: wrap;
  margin-top: 1rem;
  font-size: 0.8rem;
  color: var(--fg-muted);
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--accent);
  font-family: monospace;
}

.theme-toggle {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: var(--stone-base);
  border: 1px solid var(--stone-highlight);
  color: var(--fg-primary);
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
  transition: background-color 0.2s, border-color 0.2s;
}

.theme-toggle:hover {
  background: var(--stone-highlight);
  border-color: var(--accent);
}

.theme-toggle:focus {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* ===== Fog Layers ===== */
.fog-layer {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 1;
  background: linear-gradient(180deg, var(--fog-color), transparent 60%);
  animation: fog-drift 20s ease-in-out infinite alternate;
}

.fog-layer:nth-child(2) {
  animation-delay: -7s;
  animation-duration: 25s;
  opacity: 0.5;
}

@keyframes fog-drift {
  0% { transform: translateX(-2%) translateY(0); opacity: 0.3; }
  50% { transform: translateX(2%) translateY(-1%); opacity: 0.5; }
  100% { transform: translateX(-1%) translateY(0.5%); opacity: 0.4; }
}

/* ===== Moon ===== */
.moon {
  position: fixed;
  top: 5%;
  right: 5%;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, var(--moon-color), #d0c8b0);
  box-shadow: 0 0 40px 10px var(--moon-color), 0 0 80px 20px rgba(245, 240, 224, 0.2);
  z-index: 2;
  animation: moon-glow 4s ease-in-out infinite alternate;
}

@keyframes moon-glow {
  0% { box-shadow: 0 0 40px 10px var(--moon-color), 0 0 80px 20px rgba(245, 240, 224, 0.2); }
  100% { box-shadow: 0 0 60px 15px var(--moon-color), 0 0 120px 30px rgba(245, 240, 224, 0.3); }
}

/* ===== Papel Picado Banner (Noche de Muertos) ===== */
.papel-picado-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 60px;
  z-index: 3;
  pointer-events: none;
  overflow: hidden;
  opacity: 0;
  transition: opacity 0.5s ease;
}

[data-theme="noche"] .papel-picado-banner {
  opacity: 1;
}

.papel-picado-strand {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 100%;
  display: flex;
  justify-content: space-around;
  align-items: flex-start;
  padding-top: 5px;
  animation: papel-sway 8s ease-in-out infinite;
}

.papel-picado-strand:nth-child(2) {
  animation-delay: -3s;
  animation-duration: 10s;
}

.papel-picado-flag {
  width: 40px;
  height: 50px;
  background: var(--papel-picado);
  clip-path: polygon(0 0, 100% 0, 100% 70%, 50% 100%, 0 70%);
  opacity: 0.7;
  transform-origin: top center;
}

@keyframes papel-sway {
  0%, 100% { transform: rotate(-2deg); }
  50% { transform: rotate(2deg); }
}

/* ===== Scene ===== */
.scene {
  flex: 1;
  position: relative;
  z-index: 5;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 2rem 1rem 4rem;
  min-height: 60vh;
}

.graveyard-ground {
  position: relative;
  width: 100%;
  max-width: 1000px;
  min-height: 500px;
  background:
    radial-gradient(ellipse at 50% 100%, var(--stone-shadow) 0%, transparent 70%),
    linear-gradient(180deg, var(--bg-secondary), var(--bg-primary));
  border-radius: 50% 50% 0 0 / 20% 20% 0 0;
  overflow: visible;
}

/* ===== Grass ===== */
.grass {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 40px;
  background: repeating-linear-gradient(
    90deg,
    var(--stone-shadow),
    var(--stone-shadow) 2px,
    var(--bg-primary) 2px,
    var(--bg-primary) 4px
  );
  opacity: 0.6;
}

/* ===== Tombstones ===== */
.tombstone {
  position: absolute;
  bottom: 40px;
  transform-origin: bottom center;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  user-select: none;
}

.tombstone:focus {
  outline: 2px solid var(--accent);
  outline-offset: 4px;
  z-index: 20;
}

.tombstone:hover {
  transform: rotate(var(--tilt, 0deg)) scale(1.02) translateY(-4px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.5);
  z-index: 15;
}

.tombstone[data-mass="true"] {
  --tilt: 0deg;
}

/* Stone shapes */
.stone-small {
  width: 80px;
  height: 110px;
  border-radius: 40px 40px 4px 4px;
}

.stone-medium {
  width: 100px;
  height: 140px;
  border-radius: 50px 50px 6px 6px;
}

.stone-large {
  width: 120px;
  height: 170px;
  border-radius: 60px 60px 8px 8px;
}

.stone-mass {
  width: 180px;
  height: 100px;
  border-radius: 12px;
  bottom: 40px;
}

.tombstone::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background:
    linear-gradient(145deg, var(--stone-highlight), var(--stone-base) 50%, var(--stone-shadow));
  box-shadow:
    inset 2px 2px 4px rgba(255,255,255,0.05),
    inset -2px -2px 4px rgba(0,0,0,0.3),
    0 4px 12px rgba(0,0,0,0.4);
  border: 1px solid var(--stone-highlight);
}

.tombstone .stone-content {
  position: relative;
  z-index: 1;
  padding: 1.5rem 0.75rem 1rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  text-align: center;
  color: var(--fg-primary);
}

.stone-mass .stone-content {
  padding: 1rem;
}

.tombstone .filename {
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 90%;
  font-family: monospace;
}

.stone-mass .filename {
  font-size: 0.7rem;
}

.tombstone .years {
  font-size: 0.7rem;
  color: var(--fg-muted);
  font-variant-numeric: tabular-nums;
}

.stone-mass .years {
  font-size: 0.75rem;
}

/* Candle on stone (Noche de Muertos) */
.tombstone .candle {
  display: none;
  position: absolute;
  top: -24px;
  left: 50%;
  transform: translateX(-50%);
  width: 12px;
  height: 24px;
  background: linear-gradient(180deg, #4a3020, #2a1510);
  border-radius: 2px 2px 0 0;
  z-index: 2;
}

.tombstone .candle::after {
  content: "";
  position: absolute;
  top: -10px;
  left: 50%;
  transform: translateX(-50%);
  width: 8px;
  height: 10px;
  background: var(--candle-flame);
  border-radius: 50% 50% 50% 50% / 60% 60% 40% 40%;
  box-shadow: 0 0 8px 2px var(--candle-flame);
  animation: candle-flicker 0.3s ease-in-out infinite alternate;
}

@keyframes candle-flicker {
  0% { transform: translateX(-50%) scaleY(1) rotate(-2deg); opacity: 0.9; }
  100% { transform: translateX(-50%) scaleY(1.1) rotate(2deg); opacity: 1; }
}

[data-theme="noche"] .tombstone .candle {
  display: block;
}

/* Marigold petals on stone (Noche de Muertos) */
.tombstone .marigold-petals {
  display: none;
  position: absolute;
  bottom: 38px;
  left: 50%;
  transform: translateX(-50%);
  width: 60px;
  height: 20px;
  background: radial-gradient(ellipse, var(--marigold) 30%, transparent 70%);
  opacity: 0.6;
  pointer-events: none;
}

[data-theme="noche"] .tombstone .marigold-petals {
  display: block;
}

/* ===== Card Modal ===== */
.card-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 100;
  display: none;
  justify-content: center;
  align-items: center;
  padding: 1rem;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.card-overlay.open {
  display: flex;
  opacity: 1;
}

.card {
  background: var(--stone-base);
  border: 1px solid var(--stone-highlight);
  border-radius: 8px;
  max-width: 500px;
  width: 100%;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 0 40px rgba(0,0,0,0.6), 0 0 0 1px var(--accent);
  animation: card-enter 0.2s ease-out;
}

@keyframes card-enter {
  from { transform: scale(0.95) translateY(10px); opacity: 0; }
  to { transform: scale(1) translateY(0); opacity: 1; }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--stone-shadow);
  background: var(--stone-shadow);
  border-radius: 7px 7px 0 0;
}

.card-header h2 {
  font-size: 1rem;
  font-weight: 600;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 70%;
  font-family: monospace;
}

.card-close {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
  padding: 0;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: color 0.2s, background-color 0.2s;
}

.card-close:hover {
  color: var(--accent);
  background: var(--stone-base);
}

.card-close:focus {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.card-body {
  padding: 1.5rem;
}

.card-section {
  margin-bottom: 1.25rem;
}

.card-section:last-child {
  margin-bottom: 0;
}

.card-label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--fg-muted);
  margin-bottom: 0.4rem;
  display: block;
}

.card-value {
  color: var(--fg-primary);
  font-size: 0.9rem;
  line-height: 1.6;
}

.card-value.epitaph {
  font-style: italic;
  color: var(--accent);
  font-size: 1rem;
}

.card-value.last-words {
  font-style: italic;
  color: var(--fg-primary);
}

.card-value pre {
  background: var(--bg-primary);
  border: 1px solid var(--stone-shadow);
  border-radius: 4px;
  padding: 0.75rem;
  font-size: 0.7rem;
  line-height: 1.5;
  overflow-x: auto;
  max-height: 200px;
  color: var(--fg-muted);
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

.card-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
  font-size: 0.8rem;
}

.card-meta-item {
  background: var(--bg-secondary);
  padding: 0.5rem;
  border-radius: 4px;
  border: 1px solid var(--stone-shadow);
}

.card-meta-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--fg-muted);
  margin-bottom: 0.2rem;
}

.card-meta-value {
  color: var(--fg-primary);
  font-family: monospace;
  word-break: break-all;
}

.card-source {
  display: inline-block;
  font-size: 0.65rem;
  padding: 0.2rem 0.5rem;
  border-radius: 3px;
  background: var(--accent);
  color: var(--bg-primary);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* ===== Footer ===== */
.footer {
  position: relative;
  z-index: 10;
  padding: 1.5rem;
  text-align: center;
  color: var(--fg-muted);
  font-size: 0.8rem;
  border-top: 1px solid var(--stone-shadow);
}

.footer a {
  color: var(--accent);
  text-decoration: none;
}

.footer a:hover {
  text-decoration: underline;
}

/* ===== Mobile ===== */
@media (max-width: 600px) {
  .tombstone {
    transform: none !important;
  }

  .tombstone:hover {
    transform: scale(1.05) !important;
  }

  .stone-small { width: 70px; height: 95px; }
  .stone-medium { width: 85px; height: 120px; }
  .stone-large { width: 100px; height: 140px; }
  .stone-mass { width: 150px; height: 90px; }

  .card {
    margin: 0.5rem;
    max-height: 90vh;
  }

  .stats {
    gap: 1rem;
  }

  .stat-value {
    font-size: 1rem;
  }
}

/* ===== Screen Reader Only ===== */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
"""


_STATIC_JS = """
// ===== Data =====
const GRAVES = GRAVES_JSON_PLACEHOLDER;

// ===== Theme Toggle =====
const themeToggle = document.getElementById('themeToggle');
const themeToggleText = document.getElementById('themeToggleText');
const htmlEl = document.documentElement;

function applyTheme(theme) {
  htmlEl.setAttribute('data-theme', theme);
  localStorage.setItem('gravedigger-theme', theme);
  themeToggleText.textContent = theme === 'noche' ? '☠️ Spooky Night' : '🌙 Noche de Muertos';
  themeToggle.setAttribute('aria-label', theme === 'noche' ? 'Switch to Spooky Night theme' : 'Switch to Noche de Muertos theme');
}

function initTheme() {
  const saved = localStorage.getItem('gravedigger-theme');
  applyTheme(saved || 'spooky');
}

themeToggle.addEventListener('click', () => {
  const current = htmlEl.getAttribute('data-theme');
  applyTheme(current === 'noche' ? 'spooky' : 'noche');
});

initTheme();

// ===== Card Modal =====
const cardOverlay = document.getElementById('cardOverlay');
const cardTitle = document.getElementById('cardTitle');
const cardBody = document.getElementById('cardBody');
const cardClose = document.getElementById('cardClose');
let lastFocusedElement = null;

function openCard(index) {
  const grave = GRAVES[index];
  if (!grave) return;

  lastFocusedElement = document.activeElement;

  cardTitle.textContent = grave.path;

  let membersHtml = '';
  if (grave.is_mass && grave.members.length > 0) {
    membersHtml = `
      <div class="card-section">
        <span class="card-label">Members (${grave.members.length})</span>
        <div class="card-value" style="font-size: 0.75rem; line-height: 1.8;">
          ${grave.members.map(m => '<span>' + m + '</span>').join('<br>')}
        </div>
      </div>
    `;
  }

  cardBody.innerHTML = `
    <div class="card-section">
      <span class="card-label">Epitaph</span>
      <p class="card-value epitaph">"${grave.epitaph}"</p>
    </div>
    <div class="card-section">
      <span class="card-label">Last Words</span>
      <p class="card-value last-words">"${grave.last_words}"</p>
    </div>
    <div class="card-section">
      <span class="card-label">Engraved Facts</span>
      <div class="card-meta">
        <div class="card-meta-item">
          <div class="card-meta-label">Born</div>
          <div class="card-meta-value">${grave.born_year} (${grave.born_by})</div>
        </div>
        <div class="card-meta-item">
          <div class="card-meta-label">Died</div>
          <div class="card-meta-value">${grave.died_year} (${grave.killer})</div>
        </div>
        <div class="card-meta-item">
          <div class="card-meta-label">Lifespan</div>
          <div class="card-meta-value">${grave.lifespan_days} days</div>
        </div>
        <div class="card-meta-item">
          <div class="card-meta-label">Lines at Death</div>
          <div class="card-meta-value">${grave.lines_at_death}</div>
        </div>
        <div class="card-meta-item">
          <div class="card-meta-label">Birth Commit</div>
          <div class="card-meta-value">${grave.born_commit.slice(0, 12)}</div>
        </div>
        <div class="card-meta-item">
          <div class="card-meta-label">Death Commit</div>
          <div class="card-meta-value">${grave.death_commit.slice(0, 12)}</div>
        </div>
        <div class="card-meta-item">
          <div class="card-meta-label">Birth Message</div>
          <div class="card-meta-value">${grave.born_message}</div>
        </div>
        <div class="card-meta-item">
          <div class="card-meta-label">Death Message</div>
          <div class="card-meta-value">${grave.death_message}</div>
        </div>
      </div>
    </div>
    ${membersHtml}
    <div class="card-section">
      <span class="card-label">Last Snippet</span>
      <pre>${grave.last_snippet}</pre>
    </div>
    <div class="card-section" style="text-align: right;">
      <span class="card-source">${grave.source}</span>
    </div>
  `;

  cardOverlay.classList.add('open');
  cardOverlay.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';

  setTimeout(() => cardClose.focus(), 50);
}

function closeCard() {
  cardOverlay.classList.remove('open');
  cardOverlay.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
  if (lastFocusedElement) {
    lastFocusedElement.focus();
  }
}

function handleKeyDown(e) {
  if (e.key === 'Escape' && cardOverlay.classList.contains('open')) {
    closeCard();
  }
}

document.querySelectorAll('.tombstone').forEach(btn => {
  btn.addEventListener('click', () => openCard(parseInt(btn.dataset.index, 10)));
  btn.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openCard(parseInt(btn.dataset.index, 10));
    }
  });
});

cardClose.addEventListener('click', closeCard);
cardOverlay.addEventListener('click', (e) => {
  if (e.target === cardOverlay) closeCard();
});
document.addEventListener('keydown', handleKeyDown);

cardOverlay.addEventListener('keydown', (e) => {
  if (!cardOverlay.classList.contains('open')) return;
  if (e.key === 'Tab') {
    const focusable = cardOverlay.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
});
"""


def render_html(graves: list[GraveData]) -> str:
    """Render a list of enriched graves to a self-contained HTML string."""
    stats = _compute_stats(graves)
    max_notability = max((g.notability for g in graves), default=1.0)

    seed_string = "".join(g.path for g in graves)
    rng = _seeded_random(seed_string)
    stone_positions = [_generate_stone_position(i, len(graves), rng) for i in range(len(graves))]

    grave_jsons = []
    for i, g in enumerate(graves):
        pos = stone_positions[i]
        shape_class = _stone_shape_class(g.is_mass, g.notability, max_notability)

        grave_jsons.append({
            "index": i,
            "path": _escape(g.path),
            "epitaph": _escape(g.epitaph),
            "last_words": _escape(g.last_words),
            "born_year": _format_year(g.born_date),
            "died_year": _format_year(g.death_date),
            "lifespan_days": g.lifespan_days,
            "lines_at_death": g.lines_at_death,
            "killer": _escape(g.killer),
            "death_message": _escape(g.death_message),
            "born_message": _escape(g.born_message),
            "born_by": _escape(g.born_by),
            "last_snippet": _escape(g.last_snippet),
            "is_mass": g.is_mass,
            "members": [_escape(m) for m in g.members],
            "source": g.source,
            "shape_class": shape_class,
            "left": pos["left"],
            "top": pos["top"],
            "tilt": pos["tilt"],
        })

    graves_json = json.dumps(grave_jsons, ensure_ascii=False)

    # Build HTML header with stats
    html_parts = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "<meta charset=\"UTF-8\">",
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
        "<title>Graveyard</title>",
        f"<style>{_STATIC_CSS}</style>",
        "</head>",
        "<body>",
        "<div class=\"graveyard\">",
    ]

    # Fog layers
    html_parts.extend([
        "  <div class=\"fog-layer\" aria-hidden=\"true\"></div>",
        "  <div class=\"fog-layer\" aria-hidden=\"true\"></div>",
    ])

    # Moon
    html_parts.append("  <div class=\"moon\" aria-hidden=\"true\" role=\"img\" aria-label=\"Moon\"></div>")

    # Papel Picado Banner
    html_parts.append("""  <div class="papel-picado-banner" aria-hidden="true">
    <div class="papel-picado-strand" aria-hidden="true">
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
    </div>
    <div class="papel-picado-strand" aria-hidden="true">
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
      <div class="papel-picado-flag" style="--c: var(--marigold);"></div>
      <div class="papel-picado-flag" style="--c: var(--papel-picado);"></div>
    </div>
  </div>""")

    # Header
    html_parts.append(f"""  <header class="header" role="banner">
    <button class="theme-toggle" id="themeToggle" aria-label="Toggle Noche de Muertos theme" type="button">
      <span id="themeToggleText">🌙 Noche de Muertos</span>
    </button>
    <h1>Graveyard</h1>
    <p class="subtitle">Where deleted files rest in peace</p>
    <div class="stats" role="region" aria-label="Graveyard statistics">
      <div class="stat-item">
        <span class="stat-value" id="statGraves">{stats['graves_shown']}</span>
        <span>Graves</span>
      </div>
      <div class="stat-item">
        <span class="stat-value" id="statLines">{stats['total_lines_buried']:,}</span>
        <span>Lines Buried</span>
      </div>
      <div class="stat-item">
        <span class="stat-value" id="statLongest">{stats['longest_life_years']}</span>
        <span>Longest Life (years)</span>
      </div>
      <div class="stat-item">
        <span class="stat-value" id="statDeadliest">{stats['deadliest_year']}</span>
        <span>Deadliest Year</span>
      </div>
    </div>
  </header>""")

    # Scene
    html_parts.append("""  <main class="scene" role="main" aria-label="Graveyard scene">
    <div class="graveyard-ground">
      <div class="grass" aria-hidden="true"></div>
      <div class="tombstones" role="list" aria-label="Tombstones">""")

    # Tombstones
    for i, g in enumerate(graves):
        pos = stone_positions[i]
        shape_class = _stone_shape_class(g.is_mass, g.notability, max_notability)
        mass_attr = 'true' if g.is_mass else 'false'
        filename = _escape(g.path)
        born_year = _format_year(g.born_date)
        died_year = _format_year(g.death_date)
        epitaph = _escape(g.epitaph)
        last_words = _escape(g.last_words)

        html_parts.append(f"""        <button class="tombstone {shape_class}" data-mass="{mass_attr}"
                style="left: {pos['left']}; top: {pos['top']}; --tilt: {pos['tilt']};"
                role="listitem" aria-label="{filename}, {born_year}–{died_year}"
                data-index="{i}" tabindex="0">
          <div class="candle" aria-hidden="true"></div>
          <div class="marigold-petals" aria-hidden="true"></div>
          <div class="stone-content">
            <span class="filename">{filename}</span>
            <span class="years">{born_year}–{died_year}</span>
            <span class="sr-only">Epitaph: {epitaph}. Last words: {last_words}</span>
          </div>
        </button>""")

    # Close scene
    html_parts.extend([
        "      </div>",
        "    </div>",
        "  </main>",
    ])

    # Card Modal
    html_parts.append("""  <div class="card-overlay" id="cardOverlay" role="dialog" aria-modal="true" aria-labelledby="cardTitle">
    <div class="card" role="document">
      <div class="card-header">
        <h2 id="cardTitle"></h2>
        <button class="card-close" id="cardClose" aria-label="Close details">&times;</button>
      </div>
      <div class="card-body" id="cardBody"></div>
    </div>
  </div>""")

    # Footer
    html_parts.append("""  <footer class="footer" role="contentinfo">
    <p>Generated by <a href="https://github.com/" target="_blank" rel="noopener">Gravedigger</a> — Digging through git history since 2024</p>
  </footer>
</div>""")

    # JavaScript
    js = _STATIC_JS.replace("GRAVES_JSON_PLACEHOLDER", graves_json)
    html_parts.append(f"  <script>{js}</script>")

    html_parts.extend(["</body>", "</html>"])

    return "\n".join(html_parts)


def load_graves_from_json(json_path: str) -> list[GraveData]:
    """Load graves from a JSON file (graveyard.json or epitaphs.json)."""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    graves = []
    for item in data:
        graves.append(GraveData(
            path=item["path"],
            death_commit=item["death_commit"],
            death_date=item["death_date"],
            killer=item["killer"],
            death_message=item["death_message"],
            born_commit=item["born_commit"],
            born_date=item["born_date"],
            born_message=item["born_message"],
            born_by=item["born_by"],
            lifespan_days=item["lifespan_days"],
            lines_at_death=item["lines_at_death"],
            last_snippet=item["last_snippet"],
            notability=item["notability"],
            members=tuple(item.get("members", [])),
            is_mass=item.get("is_mass", False),
            epitaph=item.get("epitaph", ""),
            last_words=item.get("last_words", ""),
            source=item.get("source", "fallback"),
        ))
    return graves


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m gravedigger.render <epitaphs.json> [output.html]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "graveyard.html"

    graves = load_graves_from_json(input_path)
    html_output = render_html(graves)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_output)

    print(f"Rendered {len(graves)} graves to {output_path}")