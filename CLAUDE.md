# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the game

```bash
python wordle.py
```

No dependencies beyond the Python standard library (tkinter, json, os, datetime, string).

## Architecture

Two files:

- **`words.py`** — Word lists only. Exports `ANSWERS` (deduplicated, sorted list of 5-letter answer words) and `ALL_WORDS` (set union of `ANSWERS` + `VALID_GUESSES`) used for fast O(1) guess validation.
- **`wordle.py`** — Entire game: constants, helpers, and three classes.

### Key classes in `wordle.py`

**`Statistics`** — Loads/saves game stats to `~/.wordle_stats.json`. Tracks played, won, streaks, and a 6-bucket win distribution. `record(won, guess_count)` is idempotent per day via `last_played` guard.

**`TileCanvas`** — A single `tk.Canvas` that draws one 62×62 tile. States: `empty | filled | correct | present | absent`. Implements staggered flip animation (`reveal`) and bounce animation (`bounce`) using `after()` callbacks rather than threads. `apply_theme()` repaints without re-animating.

**`WordleApp`** — Main class. Constructed once; calls `root.mainloop()` at the end of `__init__`. Key responsibilities:
- `_build_*` methods construct all UI on startup
- `_on_letter / _on_backspace / _on_enter` handle all input (keyboard and on-screen)
- `_submit_guess` scores the guess, triggers tile animations, then schedules `_post_reveal` for after animations finish
- `_hard_mode_error` validates hard-mode constraints against all previous `guess_results`
- `_save_state / _load_state` persist today's game to `~/.wordle_state.json`; stale state (different date) is silently discarded on load

### Daily word selection

```python
EPOCH = date(2021, 6, 19)
idx = (date.today() - EPOCH).days % len(ANSWERS)
answer = ANSWERS[idx]
```

### Scoring logic (`score_guess`)

Two-pass algorithm handles duplicate letters correctly: pass 1 marks exact matches (green) and removes them from the pool; pass 2 marks present-but-wrong-position (yellow) consuming pool entries, else absent (gray).

### Theme system

`DARK` and `LIGHT` are plain dicts mapping semantic keys (`correct`, `present`, `absent`, `tile_bg`, etc.) to hex colour strings. `_apply_theme()` walks every widget and calls `apply_theme()` on each `TileCanvas`. Settings (dark mode, hard mode) are saved to `~/.wordle_settings.json` on Apply and loaded at startup; dark mode defaults to `True` if the file is absent.

## Building a standalone executable

A `Wordle.spec` (PyInstaller) is included. The built executable is at `dist/Wordle.exe` (no console window, UPX-compressed). To rebuild:

```bash
pyinstaller Wordle.spec
```
