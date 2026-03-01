# Wordle

A Python/tkinter clone of the NYT Wordle game.

![Python](https://img.shields.io/badge/python-3.x-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Features

- Daily word shared across all players (same deterministic selection as the original)
- 6×5 tile grid with staggered flip animations and win bounce
- QWERTY on-screen keyboard with colour-coded letter states
- Correct duplicate-letter handling
- Hard mode — revealed hints must be reused in subsequent guesses
- Dark/light theme toggle
- Share results as an emoji grid (copied to clipboard)
- Game state persists across restarts — resume today's game at any time
- Statistics with win-distribution bar chart

## Requirements

Python 3 with tkinter (included in standard Windows/macOS installers). No third-party packages needed.

## Running

```bash
python wordle.py
```

## Building a standalone executable

Requires [PyInstaller](https://pyinstaller.org):

```bash
pip install pyinstaller
pyinstaller Wordle.spec
```

Output: `dist/Wordle.exe`

## Data files

Saved automatically to your home directory:

| File | Contents |
|---|---|
| `~/.wordle_state.json` | Today's game in progress |
| `~/.wordle_stats.json` | All-time statistics |
| `~/.wordle_settings.json` | Dark mode and hard mode preferences |
