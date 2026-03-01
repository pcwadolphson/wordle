"""
Wordle — Python/tkinter edition, modelled on the NY Times game.

Features:
  • Daily word (deterministic from date, same word all day)
  • 6×5 tile grid with staggered reveal animations
  • QWERTY on-screen keyboard with colour updates
  • Correct coloring logic that handles duplicate letters
  • Toast notifications (no modal dialogs during play)
  • Statistics with win-distribution bar chart (persisted as JSON)
  • Hard mode  — revealed letters must be reused
  • Dark / Light theme toggle
  • Share results (emoji grid copied to clipboard)
  • Game-state persistence — resume today's game after restart
"""

import tkinter as tk
import json, os, string
from datetime import date
from words import ANSWERS, ALL_WORDS

# ── Constants ───────────────────────────────────────────────────────────────
EPOCH = date(2021, 6, 19)          # Day 0 of the NYT Wordle calendar
ROWS, COLS = 6, 5
TILE_SIZE   = 62
TILE_GAP    = 5
WIN_MESSAGES = ["Genius!", "Magnificent!", "Impressive!",
                "Splendid!", "Great!", "Phew!"]
STATS_FILE    = os.path.join(os.path.expanduser("~"), ".wordle_stats.json")
STATE_FILE    = os.path.join(os.path.expanduser("~"), ".wordle_state.json")
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".wordle_settings.json")

DARK = dict(
    bg="#121213", header_bg="#1a1a1b", header_border="#3a3a3c",
    tile_bg="#121213", tile_border_empty="#3a3a3c", tile_border_filled="#565758",
    tile_text="white", key_bg="#818384", key_text="white",
    correct="#538d4e", present="#b59f3b", absent="#3a3a3c",
    text="white", modal_bg="#1a1a1b", divider="#3a3a3c",
    bar_bg="#3a3a3c",
)
LIGHT = dict(
    bg="#ffffff", header_bg="#ffffff", header_border="#d3d6da",
    tile_bg="#ffffff", tile_border_empty="#d3d6da", tile_border_filled="#878a8c",
    tile_text="#1a1a1b", key_bg="#d3d6da", key_text="#1a1a1b",
    correct="#6aaa64", present="#c9b458", absent="#787c7e",
    text="#1a1a1b", modal_bg="#f9f9f9", divider="#d3d6da",
    bar_bg="#d3d6da",
)

KEYBOARD_ROWS = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]


# ── Helpers ─────────────────────────────────────────────────────────────────
def get_daily_word():
    idx = (date.today() - EPOCH).days % len(ANSWERS)
    return ANSWERS[idx]


def score_guess(guess: str, answer: str):
    """Return list of (letter, state) where state in {'correct','present','absent'}."""
    result = [None] * 5
    pool   = list(answer)                  # shrinks as letters are "used"

    # Pass 1 – correct positions (green)
    for i in range(5):
        if guess[i] == answer[i]:
            result[i] = (guess[i], "correct")
            pool[i]   = None               # consumed

    # Pass 2 – present but wrong position (yellow)
    for i in range(5):
        if result[i] is not None:
            continue
        if guess[i] in pool:
            result[i] = (guess[i], "present")
            pool[pool.index(guess[i])] = None
        else:
            result[i] = (guess[i], "absent")
    return result


# ── Statistics ───────────────────────────────────────────────────────────────
class Statistics:
    def __init__(self):
        self.played = 0
        self.won    = 0
        self.streak = 0
        self.max_streak = 0
        self.distribution = [0] * 6
        self.last_played  = None
        self.last_won     = None
        self.load()

    def load(self):
        try:
            with open(STATS_FILE) as f:
                d = json.load(f)
            self.played       = d.get("played", 0)
            self.won          = d.get("won", 0)
            self.streak       = d.get("streak", 0)
            self.max_streak   = d.get("maxStreak", 0)
            self.distribution = d.get("distribution", [0]*6)
            self.last_played  = d.get("lastPlayed")
            self.last_won     = d.get("lastWon")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save(self):
        data = dict(
            played=self.played, won=self.won,
            streak=self.streak, maxStreak=self.max_streak,
            distribution=self.distribution,
            lastPlayed=self.last_played, lastWon=self.last_won,
        )
        with open(STATS_FILE, "w") as f:
            json.dump(data, f)

    def record(self, won: bool, guess_count: int):
        today = str(date.today())
        if self.last_played == today:
            return                          # already recorded today
        self.played += 1
        if won:
            self.won += 1
            self.distribution[guess_count - 1] += 1
            # streak
            yesterday = str(date.fromordinal(date.today().toordinal() - 1))
            if self.last_won == yesterday or self.last_won == today:
                self.streak += 1
            else:
                self.streak = 1
            self.max_streak = max(self.max_streak, self.streak)
            self.last_won   = today
        else:
            self.streak = 0
        self.last_played = today
        self.save()

    @property
    def win_pct(self):
        return round(100 * self.won / self.played) if self.played else 0


# ── Tile Canvas helpers ──────────────────────────────────────────────────────
class TileCanvas(tk.Canvas):
    """A single 62×62 tile drawn on a Canvas for full visual control."""

    def __init__(self, parent, theme, **kw):
        super().__init__(parent, width=TILE_SIZE, height=TILE_SIZE,
                         highlightthickness=0, bd=0, **kw)
        self.theme  = theme
        self._letter = ""
        self._state  = "empty"   # empty | filled | correct | present | absent
        self._rect = self.create_rectangle(
            2, 2, TILE_SIZE-2, TILE_SIZE-2,
            outline=theme["tile_border_empty"], width=2,
            fill=theme["tile_bg"],
        )
        self._text = self.create_text(
            TILE_SIZE//2, TILE_SIZE//2, text="",
            font=("Helvetica", 22, "bold"),
            fill=theme["tile_text"],
        )

    def set_letter(self, ch):
        self._letter = ch
        self._state  = "filled" if ch else "empty"
        border = self.theme["tile_border_filled"] if ch else self.theme["tile_border_empty"]
        self.itemconfig(self._rect, outline=border, fill=self.theme["tile_bg"])
        self.itemconfig(self._text, text=ch.upper(), fill=self.theme["tile_text"])

    def reveal(self, state, delay=0):
        """Animate a 'flip' reveal after `delay` ms."""
        self.after(delay, lambda: self._do_flip(state))

    def _do_flip(self, state):
        STEPS   = 8
        half    = STEPS // 2
        orig_h  = TILE_SIZE - 4   # rect height (y2 - y1)
        top     = 2               # rect y1

        def compress(step):
            frac  = step / half
            new_h = max(int(orig_h * (1 - frac)), 1)
            mid   = top + orig_h // 2
            y1    = mid - new_h // 2
            y2    = mid + new_h // 2
            self.coords(self._rect, 2, y1, TILE_SIZE-2, y2)
            self.itemconfig(self._text, state="hidden")
            if step < half:
                self.after(25, lambda s=step+1: compress(s))
            else:
                apply_color()

        def apply_color():
            self._state = state
            color = self.theme.get(state, self.theme["tile_bg"])
            self.itemconfig(self._rect, fill=color, outline=color)
            expand(0)

        def expand(step):
            frac  = step / half
            new_h = max(int(orig_h * frac), 1)
            mid   = top + orig_h // 2
            y1    = mid - new_h // 2
            y2    = mid + new_h // 2
            self.coords(self._rect, 2, y1, TILE_SIZE-2, y2)
            if step == half:
                self.itemconfig(self._text, state="normal",
                                fill="white")
            if step < half:
                self.after(25, lambda s=step+1: expand(s))

        compress(0)

    def bounce(self, delay=0):
        """Brief scale-up / scale-down (win celebration)."""
        self.after(delay, self._do_bounce)

    def _do_bounce(self):
        PAD = 6
        def shrink(step, going_up):
            if going_up:
                offset = step * PAD // 4
            else:
                offset = (4 - step) * PAD // 4
            self.coords(self._rect,
                        2 + offset, 2 + offset,
                        TILE_SIZE-2-offset, TILE_SIZE-2-offset)
            if going_up and step < 4:
                self.after(30, lambda: shrink(step+1, True))
            elif going_up:
                self.after(30, lambda: shrink(0, False))
            elif step < 4:
                self.after(30, lambda: shrink(step+1, False))
            else:
                self.coords(self._rect, 2, 2, TILE_SIZE-2, TILE_SIZE-2)
        shrink(0, True)

    def apply_theme(self, theme):
        self.theme = theme
        self.config(bg=theme["bg"])
        if self._state == "empty":
            self.itemconfig(self._rect, fill=theme["tile_bg"],
                            outline=theme["tile_border_empty"])
            self.itemconfig(self._text, fill=theme["tile_text"])
        elif self._state == "filled":
            self.itemconfig(self._rect, fill=theme["tile_bg"],
                            outline=theme["tile_border_filled"])
            self.itemconfig(self._text, fill=theme["tile_text"])
        else:
            color = theme.get(self._state, theme["tile_bg"])
            self.itemconfig(self._rect, fill=color, outline=color)
            self.itemconfig(self._text, fill="white")


# ── Main Application ─────────────────────────────────────────────────────────
class WordleApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Wordle")
        self.root.resizable(False, False)

        # Settings
        self.dark_mode  = True
        self.hard_mode  = False
        self._load_settings()
        self.theme      = DARK if self.dark_mode else LIGHT

        self.stats      = Statistics()
        self.answer     = get_daily_word()
        self.puzzle_num = (date.today() - EPOCH).days

        # Game state
        self.guesses        = []          # list of completed guess strings
        self.guess_results  = []          # list of score lists
        self.current_input  = []          # letters typed on current row
        self.game_over      = False
        self.won            = False

        # Key colour state (per-letter best colour)
        self.key_colors: dict[str, str] = {}

        self._build_ui()
        self._center_window()
        self._bind_keys()

        # Load today's saved state (if any)
        self._load_state()

        self.root.mainloop()

    # ── UI Construction ──────────────────────────────────────────────────────
    def _build_ui(self):
        self.root.configure(bg=self.theme["bg"])
        self._build_header()
        self._build_grid()
        self._build_keyboard()
        self._build_toast()

    def _build_header(self):
        hf = tk.Frame(self.root, bg=self.theme["header_bg"],
                      highlightbackground=self.theme["header_border"],
                      highlightthickness=1)
        hf.pack(fill="x", side="top")
        self._header_frame = hf

        # Left: Help button
        self._help_btn = tk.Button(hf, text="?", font=("Helvetica", 16, "bold"),
                                   bg=self.theme["header_bg"], fg=self.theme["text"],
                                   relief="flat", bd=0, cursor="hand2",
                                   command=self._show_help, padx=8, pady=6)
        self._help_btn.pack(side="left")

        # Centre: Title
        self._title_lbl = tk.Label(hf, text="WORDLE",
                                   font=("Helvetica", 26, "bold"),
                                   bg=self.theme["header_bg"],
                                   fg=self.theme["text"])
        self._title_lbl.pack(side="left", expand=True)

        # Right icons: stats + settings
        right = tk.Frame(hf, bg=self.theme["header_bg"])
        right.pack(side="right")
        self._stats_btn = tk.Button(right, text="📊", font=("Helvetica", 16),
                                    bg=self.theme["header_bg"], fg=self.theme["text"],
                                    relief="flat", bd=0, cursor="hand2",
                                    command=self._show_stats, padx=4, pady=6)
        self._stats_btn.pack(side="left")
        self._settings_btn = tk.Button(right, text="⚙", font=("Helvetica", 16),
                                       bg=self.theme["header_bg"], fg=self.theme["text"],
                                       relief="flat", bd=0, cursor="hand2",
                                       command=self._show_settings, padx=8, pady=6)
        self._settings_btn.pack(side="left")
        self._header_right = right

    def _build_grid(self):
        gf = tk.Frame(self.root, bg=self.theme["bg"])
        gf.pack(pady=10)
        self._grid_frame = gf

        self._tiles: list[list[TileCanvas]] = []
        for r in range(ROWS):
            row_tiles = []
            for c in range(COLS):
                t = TileCanvas(gf, self.theme, bg=self.theme["bg"])
                t.grid(row=r, column=c,
                       padx=TILE_GAP//2, pady=TILE_GAP//2)
                row_tiles.append(t)
            self._tiles.append(row_tiles)

    def _build_keyboard(self):
        kf = tk.Frame(self.root, bg=self.theme["bg"])
        kf.pack(pady=6, padx=4)
        self._kb_frame = kf
        self._key_btns: dict[str, tk.Button] = {}

        self._kb_rows: list[tk.Frame] = []
        for row_i, row_str in enumerate(KEYBOARD_ROWS):
            rf = tk.Frame(kf, bg=self.theme["bg"])
            rf.pack(pady=3)
            self._kb_rows.append(rf)

            if row_i == 2:
                b = self._make_wide_btn(rf, "ENTER", self._on_enter)
                b.pack(side="left", padx=2)

            for ch in row_str:
                b = tk.Button(rf, text=ch, width=3, height=2,
                              font=("Helvetica", 11, "bold"),
                              bg=self.theme["key_bg"], fg=self.theme["key_text"],
                              relief="flat", bd=0, cursor="hand2",
                              command=lambda c=ch.lower(): self._on_letter(c))
                b.pack(side="left", padx=2)
                self._key_btns[ch.lower()] = b

            if row_i == 2:
                b = self._make_wide_btn(rf, "⌫", self._on_backspace)
                b.pack(side="left", padx=2)

    def _make_wide_btn(self, parent, text, cmd):
        return tk.Button(parent, text=text, width=6, height=2,
                         font=("Helvetica", 10, "bold"),
                         bg=self.theme["key_bg"], fg=self.theme["key_text"],
                         relief="flat", bd=0, cursor="hand2", command=cmd)

    def _build_toast(self):
        self._toast_lbl = tk.Label(self.root, text="", font=("Helvetica", 13, "bold"),
                                   bg="#1a1a1b", fg="white",
                                   padx=12, pady=8, relief="flat")
        self._toast_after = None

    def _center_window(self):
        w, h = 500, 700
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _bind_keys(self):
        self.root.bind("<Key>", self._on_keypress)

    # ── Input Handling ───────────────────────────────────────────────────────
    def _on_keypress(self, event):
        if event.keysym == "Return":
            self._on_enter()
        elif event.keysym == "BackSpace":
            self._on_backspace()
        elif event.char and event.char.lower() in string.ascii_lowercase:
            self._on_letter(event.char.lower())

    def _on_letter(self, ch):
        if self.game_over or len(self.current_input) >= COLS:
            return
        self.current_input.append(ch)
        row = len(self.guesses)
        col = len(self.current_input) - 1
        self._tiles[row][col].set_letter(ch)

    def _on_backspace(self):
        if self.game_over or not self.current_input:
            return
        row = len(self.guesses)
        col = len(self.current_input) - 1
        self.current_input.pop()
        self._tiles[row][col].set_letter("")

    def _on_enter(self):
        if self.game_over:
            return
        guess = "".join(self.current_input)

        if len(guess) < COLS:
            self._show_toast("Not enough letters")
            self._shake_row(len(self.guesses))
            return

        if guess not in ALL_WORDS:
            self._show_toast("Not in word list")
            self._shake_row(len(self.guesses))
            return

        # Hard mode validation
        if self.hard_mode:
            err = self._hard_mode_error(guess)
            if err:
                self._show_toast(err)
                self._shake_row(len(self.guesses))
                return

        self._submit_guess(guess)

    def _hard_mode_error(self, guess):
        """Return an error string if `guess` violates hard-mode constraints."""
        _ord = {1:"1st",2:"2nd",3:"3rd",4:"4th",5:"5th"}
        for prev_result in self.guess_results:
            for i, (letter, state) in enumerate(prev_result):
                if state == "correct" and guess[i] != letter:
                    return f"{_ord[i+1]} letter must be {letter.upper()}"
                if state == "present" and letter not in guess:
                    return f"Guess must contain {letter.upper()}"
        return ""

    # ── Game Logic ───────────────────────────────────────────────────────────
    def _submit_guess(self, guess):
        row = len(self.guesses)
        result = score_guess(guess, self.answer)

        self.guesses.append(guess)
        self.guess_results.append(result)
        self.current_input = []

        # Animate tile reveals (staggered 300 ms per tile)
        REVEAL_DELAY = 300
        for col, (letter, state) in enumerate(result):
            self._tiles[row][col].reveal(state, delay=col * REVEAL_DELAY)

        # After all tiles revealed, update keyboard & check win/loss
        total_delay = COLS * REVEAL_DELAY + 200
        self.root.after(total_delay, lambda: self._post_reveal(row, result, guess))
        self._save_state()

    def _post_reveal(self, row, result, guess):
        # Update keyboard colours
        PRIORITY = {"correct": 3, "present": 2, "absent": 1}
        for letter, state in result:
            current = self.key_colors.get(letter, "")
            if PRIORITY.get(state, 0) > PRIORITY.get(current, 0):
                self.key_colors[letter] = state
                self._update_key_color(letter, state)

        won  = all(s == "correct" for _, s in result)
        last = len(self.guesses) == ROWS

        if won:
            self.game_over = True
            self.won       = True
            msg = WIN_MESSAGES[min(len(self.guesses)-1, len(WIN_MESSAGES)-1)]
            self._show_toast(msg)
            # Bounce winning row
            for col in range(COLS):
                self._tiles[row][col].bounce(delay=col * 100)
            self.stats.record(True, len(self.guesses))
            self.root.after(2000, self._show_stats)
        elif last:
            self.game_over = True
            self._show_toast(self.answer.upper(), duration=4000)
            self.stats.record(False, len(self.guesses))
            self.root.after(4500, self._show_stats)

        self._save_state()

    # ── Animations ───────────────────────────────────────────────────────────
    def _shake_row(self, row, step=0):
        offsets = [6, -6, 4, -4, 2, -2, 0]
        if step >= len(offsets):
            return
        dx = offsets[step]
        for col in range(COLS):
            t = self._tiles[row][col]
            t.grid_configure(padx=(TILE_GAP//2 + dx, TILE_GAP//2 - dx))
        self.root.after(50, lambda: self._shake_row(row, step+1))

    # ── Toast Notifications ──────────────────────────────────────────────────
    def _show_toast(self, msg, duration=1800):
        if self._toast_after:
            self.root.after_cancel(self._toast_after)
        self._toast_lbl.config(text=msg,
                               bg="#1a1a1b" if self.dark_mode else "#333333")
        self._toast_lbl.place(relx=0.5, rely=0.13, anchor="center")
        self._toast_after = self.root.after(duration, self._hide_toast)

    def _hide_toast(self):
        self._toast_lbl.place_forget()
        self._toast_after = None

    # ── Keyboard Colours ─────────────────────────────────────────────────────
    def _update_key_color(self, letter, state):
        btn = self._key_btns.get(letter)
        if not btn:
            return
        color = self.theme.get(state, self.theme["key_bg"])
        fg    = "white" if state in ("correct", "present", "absent") else self.theme["key_text"]
        btn.config(bg=color, fg=fg)

    # ── Dialogs ──────────────────────────────────────────────────────────────
    def _show_stats(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Statistics")
        dlg.resizable(False, False)
        dlg.configure(bg=self.theme["modal_bg"])
        dlg.transient(self.root)
        dlg.grab_set()

        pad = dict(padx=16, pady=6)

        tk.Label(dlg, text="STATISTICS", font=("Helvetica", 14, "bold"),
                 bg=self.theme["modal_bg"], fg=self.theme["text"]).pack(**pad)

        # Top row of numbers
        nf = tk.Frame(dlg, bg=self.theme["modal_bg"])
        nf.pack(**pad)
        stats_data = [
            (self.stats.played,    "Played"),
            (self.stats.win_pct,   "Win %"),
            (self.stats.streak,    "Current\nStreak"),
            (self.stats.max_streak,"Max\nStreak"),
        ]
        for val, label in stats_data:
            sf = tk.Frame(nf, bg=self.theme["modal_bg"])
            sf.pack(side="left", padx=12)
            tk.Label(sf, text=str(val), font=("Helvetica", 26, "bold"),
                     bg=self.theme["modal_bg"], fg=self.theme["text"]).pack()
            tk.Label(sf, text=label, font=("Helvetica", 9),
                     bg=self.theme["modal_bg"], fg=self.theme["text"],
                     justify="center").pack()

        # Divider
        tk.Frame(dlg, bg=self.theme["divider"], height=1).pack(fill="x", padx=16, pady=4)

        tk.Label(dlg, text="GUESS DISTRIBUTION",
                 font=("Helvetica", 12, "bold"),
                 bg=self.theme["modal_bg"], fg=self.theme["text"]).pack()

        # Distribution bars
        dist = self.stats.distribution
        max_val = max(dist) if any(dist) else 1
        curr_row = len(self.guesses) if self.won else -1

        for i, cnt in enumerate(dist):
            bf = tk.Frame(dlg, bg=self.theme["modal_bg"])
            bf.pack(fill="x", padx=20, pady=2)
            tk.Label(bf, text=str(i+1), font=("Helvetica", 11, "bold"),
                     bg=self.theme["modal_bg"], fg=self.theme["text"],
                     width=2).pack(side="left")
            bar_color = self.theme["correct"] if (i+1) == curr_row else self.theme["bar_bg"]
            bar_w = max(int(160 * cnt / max_val), 20) if cnt else 20
            bar = tk.Frame(bf, bg=bar_color, height=20, width=bar_w)
            bar.pack(side="left", padx=4)
            tk.Label(bar, text=str(cnt), font=("Helvetica", 10, "bold"),
                     bg=bar_color, fg="white").pack(side="right", padx=4)

        # Divider
        tk.Frame(dlg, bg=self.theme["divider"], height=1).pack(fill="x", padx=16, pady=4)

        # Buttons row
        bf2 = tk.Frame(dlg, bg=self.theme["modal_bg"])
        bf2.pack(pady=10)

        if self.game_over:
            share_btn = tk.Button(bf2, text="Share  🔗",
                                  font=("Helvetica", 13, "bold"),
                                  bg=self.theme["correct"], fg="white",
                                  relief="flat", bd=0, padx=16, pady=8,
                                  cursor="hand2",
                                  command=lambda: self._share(dlg))
            share_btn.pack(side="left", padx=8)

        tk.Button(bf2, text="Close", font=("Helvetica", 13),
                  bg=self.theme["key_bg"], fg=self.theme["key_text"],
                  relief="flat", bd=0, padx=16, pady=8, cursor="hand2",
                  command=dlg.destroy).pack(side="left", padx=8)

        dlg.update_idletasks()
        self._center_dialog(dlg)

    def _show_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Settings")
        dlg.resizable(False, False)
        dlg.configure(bg=self.theme["modal_bg"])
        dlg.transient(self.root)
        dlg.grab_set()

        pad = dict(padx=20, pady=8)

        tk.Label(dlg, text="SETTINGS", font=("Helvetica", 14, "bold"),
                 bg=self.theme["modal_bg"], fg=self.theme["text"]).pack(**pad)
        tk.Frame(dlg, bg=self.theme["divider"], height=1).pack(fill="x", padx=16)

        # Hard Mode
        hard_var = tk.BooleanVar(value=self.hard_mode)
        self._add_toggle(dlg, "Hard Mode",
                         "Revealed hints must be used in subsequent guesses",
                         hard_var)

        # Dark Mode
        dark_var = tk.BooleanVar(value=self.dark_mode)
        self._add_toggle(dlg, "Dark Theme", "Switch between dark and light themes",
                         dark_var)

        tk.Frame(dlg, bg=self.theme["divider"], height=1).pack(fill="x", padx=16, pady=4)

        def apply_settings():
            self.hard_mode  = hard_var.get()
            self.dark_mode  = dark_var.get()
            self.theme      = DARK if self.dark_mode else LIGHT
            self._apply_theme()
            self._save_settings()
            dlg.destroy()

        tk.Button(dlg, text="Apply", font=("Helvetica", 13, "bold"),
                  bg=self.theme["correct"], fg="white",
                  relief="flat", bd=0, padx=20, pady=8, cursor="hand2",
                  command=apply_settings).pack(pady=12)

        dlg.update_idletasks()
        self._center_dialog(dlg)

    def _add_toggle(self, parent, title, subtitle, var):
        row = tk.Frame(parent, bg=self.theme["modal_bg"])
        row.pack(fill="x", padx=20, pady=6)
        left = tk.Frame(row, bg=self.theme["modal_bg"])
        left.pack(side="left", expand=True, fill="x")
        tk.Label(left, text=title, font=("Helvetica", 12, "bold"),
                 bg=self.theme["modal_bg"], fg=self.theme["text"],
                 anchor="w").pack(fill="x")
        tk.Label(left, text=subtitle, font=("Helvetica", 9),
                 bg=self.theme["modal_bg"], fg=self.theme["text"],
                 anchor="w", wraplength=230, justify="left").pack(fill="x")
        tk.Checkbutton(row, variable=var,
                       bg=self.theme["modal_bg"],
                       activebackground=self.theme["modal_bg"],
                       cursor="hand2").pack(side="right")

    def _show_help(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("How to Play")
        dlg.resizable(False, False)
        dlg.configure(bg=self.theme["modal_bg"])
        dlg.transient(self.root)
        dlg.grab_set()

        pad = dict(padx=20, pady=6, anchor="w")

        tk.Label(dlg, text="HOW TO PLAY", font=("Helvetica", 14, "bold"),
                 bg=self.theme["modal_bg"], fg=self.theme["text"]).pack(pady=10)
        tk.Frame(dlg, bg=self.theme["divider"], height=1).pack(fill="x", padx=16)

        lines = [
            "Guess the WORDLE in 6 tries.",
            "",
            "• Each guess must be a valid 5-letter word.",
            "• The colour of the tiles will change to show\n  how close your guess was to the word.",
            "",
            "Examples:",
        ]
        for line in lines:
            tk.Label(dlg, text=line, font=("Helvetica", 11),
                     bg=self.theme["modal_bg"], fg=self.theme["text"],
                     justify="left").pack(**pad)

        # Example tiles
        examples = [
            [("W","correct"),("E","absent"),("A","absent"),("R","absent"),("Y","absent")],
            [("P","absent"),("I","present"),("L","absent"),("L","absent"),("S","absent")],
            [("V","absent"),("A","absent"),("G","absent"),("U","absent"),("E","absent")],
        ]
        ex_labels = [
            "W is in the word and in the correct spot.",
            "I is in the word but in the wrong spot.",
            "U is not in the word in any spot.",
        ]
        for ex, lbl_text in zip(examples, ex_labels):
            ef = tk.Frame(dlg, bg=self.theme["modal_bg"])
            ef.pack(padx=20, pady=4, anchor="w")
            for letter, state in ex:
                color = self.theme.get(state, self.theme["tile_bg"])
                border = color if state != "absent" or letter not in ("V","A","G","E") else self.theme["tile_border_empty"]
                lf = tk.Frame(ef, bg=color if state != "empty" else self.theme["tile_bg"],
                              highlightbackground=color if state != "absent" else self.theme["tile_border_empty"],
                              highlightthickness=2,
                              width=38, height=38)
                lf.pack(side="left", padx=2)
                lf.pack_propagate(False)
                fg = "white" if state in ("correct","present","absent") else self.theme["tile_text"]
                tk.Label(lf, text=letter, font=("Helvetica", 14, "bold"),
                         bg=color if state != "absent" else self.theme["tile_bg"],
                         fg=fg if state in ("correct","present") else self.theme["tile_text"]
                         ).place(relx=0.5, rely=0.5, anchor="center")
            tk.Label(dlg, text=lbl_text, font=("Helvetica", 9),
                     bg=self.theme["modal_bg"], fg=self.theme["text"],
                     wraplength=260, justify="left").pack(padx=20, anchor="w")

        tk.Frame(dlg, bg=self.theme["divider"], height=1).pack(fill="x", padx=16, pady=8)

        tk.Label(dlg, text="A new WORDLE will be available tomorrow!",
                 font=("Helvetica", 10, "italic"),
                 bg=self.theme["modal_bg"], fg=self.theme["text"]).pack(pady=4)

        tk.Button(dlg, text="Got it!", font=("Helvetica", 12, "bold"),
                  bg=self.theme["correct"], fg="white",
                  relief="flat", bd=0, padx=16, pady=8, cursor="hand2",
                  command=dlg.destroy).pack(pady=12)

        dlg.update_idletasks()
        self._center_dialog(dlg)

    # ── Share ────────────────────────────────────────────────────────────────
    def _share(self, parent=None):
        STATE_EMOJI = {"correct": "🟩", "present": "🟨", "absent": "⬛"}
        guess_count = f"{len(self.guesses)}/6" if self.won else "X/6"
        lines = [f"Wordle {self.puzzle_num} {guess_count}", ""]
        for result in self.guess_results:
            lines.append("".join(STATE_EMOJI[s] for _, s in result))
        text = "\n".join(lines)

        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._show_toast("Copied to clipboard!")

    # ── Theme ─────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        t = self.theme
        self.root.configure(bg=t["bg"])

        # Header
        for w in (self._header_frame, self._header_right):
            w.configure(bg=t["header_bg"])
        self._header_frame.configure(highlightbackground=t["header_border"])
        for btn in (self._help_btn, self._stats_btn, self._settings_btn):
            btn.configure(bg=t["header_bg"], fg=t["text"],
                          activebackground=t["header_bg"])
        self._title_lbl.configure(bg=t["header_bg"], fg=t["text"])

        # Grid
        self._grid_frame.configure(bg=t["bg"])
        for row in self._tiles:
            for tile in row:
                tile.configure(bg=t["bg"])
                tile.apply_theme(t)

        # Keyboard
        self._kb_frame.configure(bg=t["bg"])
        for rf in self._kb_rows:
            rf.configure(bg=t["bg"])
        for ch, btn in self._key_btns.items():
            state = self.key_colors.get(ch)
            if state:
                color = t.get(state, t["key_bg"])
                btn.configure(bg=color, fg="white",
                              activebackground=color)
            else:
                btn.configure(bg=t["key_bg"], fg=t["key_text"],
                              activebackground=t["key_bg"])

    # ── Settings Persistence ─────────────────────────────────────────────────
    def _load_settings(self):
        try:
            with open(SETTINGS_FILE) as f:
                d = json.load(f)
            self.dark_mode = d.get("dark_mode", True)
            self.hard_mode = d.get("hard_mode", False)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_settings(self):
        with open(SETTINGS_FILE, "w") as f:
            json.dump({"dark_mode": self.dark_mode, "hard_mode": self.hard_mode}, f)

    # ── State Persistence ────────────────────────────────────────────────────
    def _save_state(self):
        data = dict(
            date=str(date.today()),
            guesses=self.guesses,
            guess_results=[[list(item) for item in r] for r in self.guess_results],
            current_input=self.current_input,
            game_over=self.game_over,
            won=self.won,
            key_colors=self.key_colors,
        )
        with open(STATE_FILE, "w") as f:
            json.dump(data, f)

    def _load_state(self):
        try:
            with open(STATE_FILE) as f:
                d = json.load(f)
            if d.get("date") != str(date.today()):
                return   # stale — new puzzle today
        except (FileNotFoundError, json.JSONDecodeError):
            return

        self.guesses       = d.get("guesses", [])
        self.guess_results = [
            [tuple(item) for item in r]
            for r in d.get("guess_results", [])
        ]
        self.current_input = d.get("current_input", [])
        self.game_over     = d.get("game_over", False)
        self.won           = d.get("won", False)
        self.key_colors    = d.get("key_colors", {})

        # Restore tiles
        for row_i, (guess, result) in enumerate(zip(self.guesses, self.guess_results)):
            for col_i, (letter, state) in enumerate(result):
                tile = self._tiles[row_i][col_i]
                tile.set_letter(letter)
                # Instantly apply state colour (no animation on restore)
                tile._state = state
                color = self.theme.get(state, self.theme["tile_bg"])
                tile.itemconfig(tile._rect, fill=color, outline=color)
                tile.itemconfig(tile._text, text=letter.upper(), fill="white")

        # Restore in-progress row
        for col_i, ch in enumerate(self.current_input):
            self._tiles[len(self.guesses)][col_i].set_letter(ch)

        # Restore keyboard colours
        for letter, state in self.key_colors.items():
            self._update_key_color(letter, state)

    # ── Utility ──────────────────────────────────────────────────────────────
    def _center_dialog(self, dlg):
        dlg.update_idletasks()
        px = self.root.winfo_x() + self.root.winfo_width() // 2
        py = self.root.winfo_y() + self.root.winfo_height() // 2
        dw, dh = dlg.winfo_width(), dlg.winfo_height()
        dlg.geometry(f"+{px - dw//2}+{py - dh//2}")


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    WordleApp()
