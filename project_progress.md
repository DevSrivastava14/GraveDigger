# Project progress: Gravedigger

## Status
- Current day: 1
- Works: Exhumer part 1 (find_deaths) with tests; CLI prints death count + first 15
- Broken: nothing yet

## Decisions
- LLM calls use think=False (hybrid reasoning model; thinking is slow and breaks JSON parsing). Strip  blocks as a fallback.
- Git log parsed with %x1f separator, COMMIT marker lines; filenames can contain spaces
- Noise filters as module-level constants (extensions, filenames, path prefixes)
- Most recent death per path kept by processing git log newest-first

## Done log
### Day 1
- Created gravedigger/exhume.py with Death dataclass and find_deaths()
- Implemented noise filtering (extensions, filenames, path prefixes)
- Created tests/test_exhume.py with 8 tests covering all required cases (a-g)
- All tests pass
- Wired debug output into CLI (prints count + first 15 deaths)
- Verified against flask repo: found 207 deaths
- **Audit**: All 4 behaviors verified in code; check_deaths.py run on flask repo — 207 deaths, 0 noise, 0 resurrected in results; breakdown: raw 251 → -1 resurrected → -43 noise → 207; rename detection (-M) makes no difference; counts match exactly; ollama>=0.6 pinned in pyproject.toml

## Next up
1. Exhumer part 2: generate epitaphs via local Ollama

## Story notes (for the dev.to post)
(Moments worth writing about: a tombstone that moved you, a funny epitaph,
a model failure, something you learned.)