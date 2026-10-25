"""A Windows CMD-inspired desktop front end for the SciCalc engine."""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from typing import Iterable

from . import __version__
from .desktop_session import (
    COMMAND_NAMES,
    Action,
    DesktopSession,
    OutputLine,
    Segment,
    banner_lines,
    help_lines,
    load_app_state,
    save_app_state,
)
from .engine import FUNCTIONS, MAX_SOURCE_LENGTH

_APP_TITLE = "命令提示符 - SciCalc CMD"
_DEFAULT_STATE = object()

# Windows Terminal's Campbell palette, also used by the default CMD profile.
_BG = "#0C0C0C"
_FG = "#CCCCCC"
_INPUT_FG = "#F2F2F2"
_DIM = "#7A7A7A"
_ACCENT = "#3A96DD"
_RESULT = "#16C60C"
_ERROR = "#E74856"
_SELECT = "#264F78"
_SCROLL = "#3A3A3A"
_SCROLL_ACTIVE = "#565656"
_BORDER = "#2B2B2B"

_GEOMETRY_RE = re.compile(r"^(\d{3,4})x(\d{3,4})([+-]\d{1,5})([+-]\d{1,5})$")
_COMPLETION_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)$")
_CONSTANT_NAMES = ("ans", "e", "phi", "pi", "tau")
_FUNCTIONS = tuple(sorted(FUNCTIONS))
_COMPLETION_WORDS = tuple(sorted(set(_FUNCTIONS) | set(_CONSTANT_NAMES)))
_MODIFIER_MASK = 0x4 | 0x8 | 0x20000  # Ctrl, Meta, Alt


def default_state_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "SciCalcCMD" / "state.json"
    return Path.home() / ".scicalc" / "cmd-state.json"


def _enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _make_window_icon() -> tk.PhotoImage:
    """Draw a small terminal-window icon without an external asset."""

    image = tk.PhotoImage(width=32, height=32)
    image.put("#3B3B3B", to=(1, 2, 31, 31))
    image.put(_BG, to=(2, 3, 30, 30))
    image.put("#1F4E79", to=(2, 3, 30, 8))
    image.put("#D6D6D6", to=(4, 5, 5, 6))
    image.put("#D6D6D6", to=(7, 5, 8, 6))
    image.put("#D6D6D6", to=(10, 5, 11, 6))
    # A blocky ">_" prompt on the screen.
    image.put(_RESULT, to=(7, 11, 9, 12))
    image.put(_RESULT, to=(9, 12, 11, 13))
    image.put(_RESULT, to=(11, 13, 13, 14))
    image.put(_RESULT, to=(9, 14, 11, 15))
    image.put(_RESULT, to=(7, 15, 9, 16))
    image.put(_RESULT, to=(12, 18, 21, 19))
    # Monitor stand.
    image.put("#3B3B3B", to=(13, 30, 19, 31))
    image.put("#555555", to=(10, 31, 22, 32))
    return image


def _apply_dark_title_bar(window: tk.Misc) -> None:
    """Ask DWM for a dark native title bar on Windows 10 and 11."""

    if os.name != "nt":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()

        try:
            ctypes.windll.uxTheme.SetWindowTheme(hwnd, "DarkMode_Explorer", None)
        except Exception:
            pass

        dwmapi = ctypes.windll.dwmapi
        enabled = ctypes.c_int(1)
        for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE
            result = dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled)
            )
            if result == 0:
                break
        for attribute, color in (
            (35, _BG),  # DWMWA_CAPTION_COLOR
            (36, _FG),  # DWMWA_TEXT_COLOR
            (34, _BORDER),  # DWMWA_BORDER_COLOR
        ):
            value = int(color[1:], 16)
            value = ((value & 0xFF) << 16) | (value & 0xFF00) | ((value >> 16) & 0xFF)
            c_value = ctypes.c_int(value)
            dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(c_value), ctypes.sizeof(c_value)
            )

        # Some Windows 10 builds only repaint the frame after a frame change.
        flags = 0x2 | 0x1 | 0x4 | 0x20  # NOMOVE | NOSIZE | NOZORDER | FRAMECHANGED
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
    except Exception:
        # The dark title bar is cosmetic; older Windows versions keep theirs.
        return


class _ConsoleScrollbar(tk.Canvas):
    """A slim dark scrollbar that behaves like a terminal scroll gutter."""

    def __init__(self, master: tk.Misc, text: tk.Text, **kwargs: object) -> None:
        super().__init__(
            master,
            width=12,
            bg=_BG,
            highlightthickness=0,
            borderwidth=0,
            takefocus=0,
            cursor="arrow",
            **kwargs,
        )
        self.text = text
        self._first = 0.0
        self._last = 1.0
        self._drag_y: int | None = None
        self._drag_first = 0.0
        self._hover = False
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def set(self, first: str | float, last: str | float) -> None:
        self._first = max(0.0, min(1.0, float(first)))
        self._last = max(0.0, min(1.0, float(last)))
        self._draw()

    def _bounds(self) -> tuple[float, float, float, float] | None:
        height = self.winfo_height()
        if height <= 4:
            return None
        span = self._last - self._first
        if span >= 0.999:
            return None
        track_top = 2.0
        track_bottom = height - 2.0
        top = track_top + (track_bottom - track_top) * self._first
        bottom = track_top + (track_bottom - track_top) * self._last
        minimum = 34.0
        if bottom - top < minimum:
            center = (top + bottom) / 2
            top = center - minimum / 2
            bottom = center + minimum / 2
            if top < track_top:
                top, bottom = track_top, track_top + minimum
            if bottom > track_bottom:
                bottom = track_bottom
                top = max(track_top, bottom - minimum)
        return 3.0, top, 9.0, bottom

    def _draw(self) -> None:
        self.delete("all")
        bounds = self._bounds()
        if bounds is None:
            return
        x1, y1, x2, y2 = bounds
        color = _SCROLL_ACTIVE if (self._hover or self._drag_y is not None) else _SCROLL
        self.create_rectangle(x1, y1, x2, y2, fill=color, outline="")
        if y2 - y1 > 16:
            center = (y1 + y2) / 2
            line_color = "#777777" if self._hover else "#5C5C5C"
            self.create_line(x1 + 2, center - 3, x2 - 2, center - 3, fill=line_color)
            self.create_line(x1 + 2, center + 1, x2 - 2, center + 1, fill=line_color)

    def _press(self, event: tk.Event) -> str:
        bounds = self._bounds()
        if bounds is None:
            return "break"
        _x1, y1, _x2, y2 = bounds
        if y1 <= event.y <= y2:
            self._drag_y = event.y
            self._drag_first = self._first
        else:
            height = max(1, self.winfo_height())
            span = self._last - self._first
            self.text.yview_moveto(max(0.0, min(1.0 - span, event.y / height - span / 2)))
        return "break"

    def _drag(self, event: tk.Event) -> str:
        if self._drag_y is None:
            return "break"
        height = max(1, self.winfo_height())
        span = self._last - self._first
        target = self._drag_first + (event.y - self._drag_y) / height
        self.text.yview_moveto(max(0.0, min(1.0 - span, target)))
        return "break"

    def _release(self, _event: tk.Event) -> str:
        self._drag_y = None
        self._draw()
        return "break"

    def _enter(self, _event: tk.Event) -> None:
        self._hover = True
        self._draw()

    def _leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._draw()


class DesktopApp:
    """The CMD-style window, console editing, and clipboard integration."""

    def __init__(
        self,
        master: tk.Tk | None = None,
        *,
        state_path: Path | None | object = _DEFAULT_STATE,
        session: DesktopSession | None = None,
    ) -> None:
        _enable_dpi_awareness()
        self.root = master if master is not None else tk.Tk()
        self.state_path = default_state_path() if state_path is _DEFAULT_STATE else state_path
        assert self.state_path is None or isinstance(self.state_path, Path)

        state = load_app_state(self.state_path)
        self.session = session or DesktopSession(
            angle_mode=state.angle_mode,
            precision=state.precision,
            history=state.history,
        )
        self.prompt = f"{Path.home()}>"
        self._history_position = len(self.session.command_history)
        self._history_draft = ""
        self._closed = False
        self._context_menu: tk.Menu | None = None
        self._history_window: tk.Toplevel | None = None

        self._configure_window(state.geometry)
        self._build_fonts()
        self._build_widgets()
        self._bind_events()
        self._render_banner()
        self._new_prompt()
        self._update_title()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(30, self._focus_console)
        self.root.after(60, lambda: _apply_dark_title_bar(self.root))

    # ------------------------------------------------------------------
    # Window and widget construction

    def _configure_window(self, saved_geometry: str | None) -> None:
        self.root.title(_APP_TITLE)
        self.root.configure(bg=_BG)
        self.root.minsize(640, 420)
        try:
            self.root.iconphoto(True, _make_window_icon())
        except tk.TclError:
            pass

        match = _GEOMETRY_RE.match(saved_geometry) if saved_geometry else None
        if match:
            width, height, x, y = (int(value) for value in match.groups())
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            if (
                width >= 640
                and height >= 420
                and -10_000 < x < screen_width
                and -10_000 < y < screen_height
            ):
                self.root.geometry(saved_geometry)
                return

        width, height = 980, 640
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 3)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_fonts(self) -> None:
        families = set(tkfont.families(self.root))
        family = next(
            (name for name in ("Cascadia Mono", "Consolas", "Courier New") if name in families),
            "TkFixedFont",
        )
        self.font = tkfont.Font(self.root, family=family, size=11)
        self.bold_font = tkfont.Font(self.root, family=family, size=11, weight="bold")

    def _build_widgets(self) -> None:
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.console = tk.Text(
            self.root,
            wrap="char",
            bg=_BG,
            fg=_FG,
            font=self.font,
            borderwidth=0,
            highlightthickness=0,
            padx=16,
            pady=10,
            insertbackground="#FFFFFF",
            insertwidth=8,
            selectbackground=_SELECT,
            selectforeground="#FFFFFF",
            exportselection=False,
            takefocus=True,
            cursor="xterm",
            undo=False,
            relief="flat",
        )
        self.console.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = _ConsoleScrollbar(self.root, self.console)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.console.configure(yscrollcommand=self.scrollbar.set)
        self._configure_tags()

    def _configure_tags(self) -> None:
        tags = {
            "text": {"foreground": _FG},
            "dim": {"foreground": _DIM},
            "title": {"foreground": "#F2F2F2", "font": self.bold_font},
            "heading": {"foreground": "#F2F2F2", "font": self.bold_font},
            "accent": {"foreground": _ACCENT},
            "success": {"foreground": _ACCENT},
            "result": {"foreground": _RESULT, "font": self.bold_font},
            "error": {"foreground": _ERROR},
            "error_source": {"foreground": "#B8B8B8"},
            "help_cmd": {"foreground": _ACCENT},
            "prompt": {"foreground": _FG},
            "command": {"foreground": _INPUT_FG},
        }
        for name, options in tags.items():
            self.console.tag_configure(name, **options)
        self._valid_tags = set(tags)

    def _bind_events(self) -> None:
        self.console.bind("<KeyPress>", self._on_keypress)
        self.console.bind("<Return>", self.submit)
        self.console.bind("<KP_Enter>", self.submit)
        self.console.bind("<BackSpace>", self._backspace)
        self.console.bind("<Delete>", self._delete_forward)
        self.console.bind("<Left>", self._cursor_left)
        self.console.bind("<Right>", self._cursor_right)
        self.console.bind("<Home>", self._cursor_home)
        self.console.bind("<End>", self._cursor_end)
        self.console.bind("<Up>", self._history_previous)
        self.console.bind("<Down>", self._history_next)
        self.console.bind("<Tab>", self._complete)
        self.console.bind("<Escape>", self._clear_input)
        self.console.bind("<Control-l>", self._clear_screen_event)
        self.console.bind("<Control-c>", self._cancel_or_copy)
        self.console.bind("<Control-a>", self._select_all)
        self.console.bind("<Control-v>", self._paste)
        self.console.bind("<Control-Key>", self._block_control_key)
        self.console.bind("<<Paste>>", self._paste)
        self.console.bind("<Shift-Insert>", self._paste)
        self.console.bind("<Button-3>", self._show_context_menu)
        self.console.bind("<ButtonRelease-1>", self._restore_input_cursor)
        self.console.bind("<MouseWheel>", self._scroll_output)
        self.console.bind("<Control-MouseWheel>", self._scroll_output)

        self.root.bind("<F1>", self._show_help_event)
        self.root.bind("<F7>", self._show_history_window)
        self.root.bind("<Control-l>", self._clear_screen_event)
        self.root.bind("<MouseWheel>", self._scroll_output)

    # ------------------------------------------------------------------
    # Prompt, output, and cursor placement

    def _insert_lines_at(self, index: str, lines: Iterable[OutputLine]) -> None:
        self.console.mark_set("_append", index)
        self.console.mark_gravity("_append", "right")
        for line in lines:
            if line.segments:
                for segment in line.segments:
                    tag = segment.style if segment.style in self._valid_tags else "text"
                    self.console.insert("_append", segment.text, (tag,))
            self.console.insert("_append", "\n")
        self.console.mark_unset("_append")

    def _append_output(self, lines: Iterable[OutputLine]) -> None:
        self._insert_lines_at("end-1c", lines)
        self.console.see("end")

    def _append_above_prompt(self, lines: Iterable[OutputLine]) -> None:
        """Print asynchronous output above the editable command line."""

        self._insert_lines_at("prompt_start", lines)
        self.console.mark_set("insert", "end-1c")
        self.console.see("end")

    def _new_prompt(self) -> None:
        line_start = self.console.index("end-1c")
        self.console.insert(line_start, self.prompt, ("prompt",))
        self.console.mark_set("prompt_start", line_start)
        self.console.mark_gravity("prompt_start", "right")
        self.console.mark_set("input_start", "end-1c")
        self.console.mark_gravity("input_start", "left")
        self.console.mark_set("insert", "end-1c")
        self.console.see("end")
        self.console.focus_set()

    def _render_banner(self) -> None:
        self._append_output(banner_lines(self.session))

    def _clear_console(self) -> None:
        self.console.delete("1.0", "end")
        self._new_prompt()

    def _update_title(self) -> None:
        self.root.title(f"{_APP_TITLE} [{self.session.angle_mode.upper()}]")

    def _focus_console(self) -> None:
        if not self._closed:
            self.console.focus_set()

    # ------------------------------------------------------------------
    # Test-friendly input helpers

    def get_input(self) -> str:
        try:
            return self.console.get("input_start", "end-1c")
        except tk.TclError:
            return ""

    def set_input(self, text: str, cursor: int | None = None) -> None:
        self.console.delete("input_start", "end-1c")
        self.console.insert("end-1c", text, ("command",))
        if cursor is None:
            cursor = len(text)
        cursor = max(0, min(len(text), cursor))
        base = self.console.index("input_start")
        self.console.mark_set("insert", f"{base} + {cursor} chars")
        self.console.see("end")

    def console_text(self) -> str:
        return self.console.get("1.0", "end-1c")

    # ------------------------------------------------------------------
    # Submission and commands

    def submit(self, _event: tk.Event | None = None) -> str:
        raw = self.get_input()
        return self._process(raw)

    def _process(self, raw: str) -> str:
        if self._closed:
            return "break"

        # The input is already visible after the prompt. Finish that line so
        # the command and its output can scroll naturally with the console.
        self.console.tag_remove("sel", "1.0", "end")
        self.console.mark_set("insert", "end-1c")
        self.console.insert("end-1c", "\n", ("text",))

        outcome = self.session.submit(raw)
        self._history_position = len(self.session.command_history)
        self._history_draft = ""

        if outcome.action is Action.CLEAR_SCREEN:
            self._clear_console()
            self._update_title()
            self._save_state()
            return "break"
        self._append_output(outcome.lines)

        self._update_title()
        self._save_state()

        if outcome.action is Action.EXIT:
            self.root.after(120, self.close)
            return "break"

        self._new_prompt()
        return "break"

    def _save_state(self) -> None:
        geometry = None
        try:
            if self.root.state() == "normal":
                geometry = self.root.geometry()
        except tk.TclError:
            pass
        save_app_state(self.state_path, self.session, geometry)

    # ------------------------------------------------------------------
    # Editing

    def _input_start(self) -> str:
        return self.console.index("input_start")

    def _input_end(self) -> str:
        return self.console.index("end-1c")

    def _selection_ranges(self) -> tuple[str, str] | None:
        ranges = self.console.tag_ranges("sel")
        if len(ranges) >= 2:
            return str(ranges[0]), str(ranges[1])
        return None

    def _selection_inside_input(self) -> bool:
        ranges = self._selection_ranges()
        if ranges is None:
            return False
        start, end = ranges
        return (
            self.console.compare(start, ">=", "input_start")
            and self.console.compare(end, "<=", "end-1c")
        )

    def _prepare_input_insert(self) -> None:
        """Clear a selection if it belongs to the input and park the cursor."""

        if self._selection_inside_input():
            ranges = self._selection_ranges()
            assert ranges is not None
            start, end = ranges
            self.console.delete(start, end)
            self.console.mark_set("insert", start)
        else:
            self.console.tag_remove("sel", "1.0", "end")
            if (
                self.console.compare("insert", "<", "input_start")
                or self.console.compare("insert", ">", "end-1c")
            ):
                self.console.mark_set("insert", "end-1c")
        self.console.focus_set()

    def _on_keypress(self, event: tk.Event) -> str | None:
        if event.state & _MODIFIER_MASK:
            return None
        if event.char and event.char.isprintable():
            self._prepare_input_insert()
            self.console.insert("insert", event.char, ("command",))
            return "break"
        return None

    def _backspace(self, _event: tk.Event | None = None) -> str:
        if self._selection_inside_input():
            self._prepare_input_insert()
            return "break"
        self.console.tag_remove("sel", "1.0", "end")
        if (
            self.console.compare("insert", ">", "input_start")
            and self.console.compare("insert", "<=", "end-1c")
        ):
            self.console.delete("insert-1c", "insert")
        elif self.console.compare("insert", "<=", "input_start"):
            self.root.bell()
        return "break"

    def _delete_forward(self, _event: tk.Event | None = None) -> str:
        if self._selection_inside_input():
            self._prepare_input_insert()
            return "break"
        self.console.tag_remove("sel", "1.0", "end")
        if self.console.compare("insert", ">=", "input_start") and self.console.compare(
            "insert", "<", "end-1c"
        ):
            self.console.delete("insert", "insert+1c")
        return "break"

    def _cursor_left(self, _event: tk.Event | None = None) -> str:
        self.console.tag_remove("sel", "1.0", "end")
        if self.console.compare("insert", "<=", "input_start"):
            self.console.mark_set("insert", "input_start")
            return "break"
        self.console.mark_set("insert", "insert-1c")
        return "break"

    def _cursor_right(self, _event: tk.Event | None = None) -> str:
        self.console.tag_remove("sel", "1.0", "end")
        if self.console.compare("insert", "<", "input_start"):
            self.console.mark_set("insert", "input_start")
            return "break"
        if self.console.compare("insert", "<", "end-1c"):
            self.console.mark_set("insert", "insert+1c")
        return "break"

    def _cursor_home(self, _event: tk.Event | None = None) -> str:
        self.console.tag_remove("sel", "1.0", "end")
        self.console.mark_set("insert", "input_start")
        return "break"

    def _cursor_end(self, _event: tk.Event | None = None) -> str:
        self.console.tag_remove("sel", "1.0", "end")
        self.console.mark_set("insert", "end-1c")
        return "break"

    def _clear_input(self, _event: tk.Event | None = None) -> str:
        self.console.delete("input_start", "end-1c")
        self.console.mark_set("insert", "end-1c")
        return "break"

    def _clear_screen_event(self, _event: tk.Event | None = None) -> str:
        self._clear_console()
        return "break"

    def _restore_input_cursor(self, _event: tk.Event | None = None) -> None:
        def restore() -> None:
            if self._closed or self._selection_ranges():
                return
            if self.console.compare("insert", "<", "input_start"):
                self.console.mark_set("insert", "end-1c")

        self.root.after_idle(restore)

    def _block_control_key(self, _event: tk.Event | None = None) -> str:
        """Prevent Tk's destructive Emacs-style Ctrl bindings in output."""

        return "break"

    # ------------------------------------------------------------------
    # History navigation and completion

    def _history_previous(self, _event: tk.Event | None = None) -> str:
        history = self.session.command_history
        if not history or self._history_position <= 0:
            return "break"
        if self._history_position == len(history):
            self._history_draft = self.get_input()
        self._history_position -= 1
        self.set_input(history[self._history_position])
        return "break"

    def _history_next(self, _event: tk.Event | None = None) -> str:
        history = self.session.command_history
        if not history or self._history_position >= len(history):
            return "break"
        if self._history_position == len(history) - 1:
            self._history_position = len(history)
            self.set_input(self._history_draft)
        else:
            self._history_position += 1
            self.set_input(history[self._history_position])
        return "break"

    def _complete(self, _event: tk.Event | None = None) -> str:
        text = self.get_input()
        try:
            before_cursor = self.console.get("input_start", "insert")
        except tk.TclError:
            return "break"
        cursor = len(before_cursor)
        left, right = text[:cursor], text[cursor:]
        match = _COMPLETION_RE.search(left)
        if not match:
            return "break"

        token = match.group(1)
        before = left[: match.start()]
        stripped_before = before.strip()
        command_only = stripped_before == ":"

        if command_only:
            candidates = [name for name in COMMAND_NAMES if name.startswith(token.lower())]
        elif stripped_before == "":
            # At the start of a line both terminal commands and functions are
            # useful completions ("he" → help, "si" → sin).
            candidates = [
                name
                for name in (*COMMAND_NAMES, *_COMPLETION_WORDS)
                if name.startswith(token.lower())
            ]
            candidates = list(dict.fromkeys(candidates))
        else:
            candidates = [name for name in _COMPLETION_WORDS if name.startswith(token.lower())]

        if not candidates:
            self.root.bell()
            return "break"

        exact = next((name for name in candidates if name == token.lower()), None)
        if exact is not None:
            candidates = [exact]

        if len(candidates) == 1:
            candidate = candidates[0]
            suffix = ""
            if candidate in _FUNCTIONS:
                if not right.startswith("("):
                    suffix = "("
            completed_text = candidate + suffix
            new_text = left[: match.start()] + completed_text + right
            self.set_input(new_text, match.start() + len(completed_text))
            return "break"

        common = os.path.commonprefix(candidates)
        if len(common) > len(token):
            new_text = left[: match.start()] + common + right
            self.set_input(new_text, match.start() + len(common))
            return "break"

        self._append_above_prompt(
            (
                OutputLine(
                    (
                        Segment("候选: ", "dim"),
                        Segment(", ".join(candidates), "accent"),
                    )
                ),
            )
        )
        return "break"

    # ------------------------------------------------------------------
    # Clipboard and context menu

    def _copy_to_clipboard(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()

    def _copy_selection(self) -> str:
        ranges = self._selection_ranges()
        if ranges is None:
            return "break"
        start, end = ranges
        self._copy_to_clipboard(self.console.get(start, end))
        return "break"

    def _cancel_or_copy(self, _event: tk.Event | None = None) -> str:
        if self._selection_ranges() is not None:
            return self._copy_selection()
        self.console.tag_remove("sel", "1.0", "end")
        self.console.mark_set("insert", "end-1c")
        self.console.insert("end-1c", "^C", ("command",))
        self.console.insert("end-1c", "\n", ("text",))
        self._history_position = len(self.session.command_history)
        self._history_draft = ""
        self._new_prompt()
        return "break"

    def _paste(self, _event: tk.Event | None = None) -> str:
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return "break"
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = " ".join(line.strip() for line in text.split("\n") if line.strip())
        if not text:
            return "break"
        if len(self.get_input()) + len(text) > MAX_SOURCE_LENGTH:
            self.root.bell()
            self._append_above_prompt(
                (
                    OutputLine.plain(
                        f"粘贴内容过长（最多 {MAX_SOURCE_LENGTH} 个字符）。",
                        "error",
                    ),
                )
            )
            return "break"
        self._prepare_input_insert()
        self.console.insert("insert", text, ("command",))
        return "break"

    def _select_all(self, _event: tk.Event | None = None) -> str:
        self.console.tag_remove("sel", "1.0", "end")
        self.console.tag_add("sel", "1.0", "end-1c")
        self.console.mark_set("insert", "end-1c")
        return "break"

    def _show_context_menu(self, event: tk.Event) -> str:
        menu = tk.Menu(
            self.root,
            tearoff=0,
            bg="#1B1B1B",
            fg=_FG,
            activebackground=_SELECT,
            activeforeground="#FFFFFF",
            font=self.font,
            borderwidth=1,
            relief="solid",
        )
        menu.add_command(label="复制", command=self._copy_selection)
        menu.add_command(label="粘贴", command=self._paste)
        menu.add_separator()
        menu.add_command(label="全选", command=self._select_all)
        menu.add_command(label="清屏", command=self._clear_console)
        menu.add_command(label="帮助", command=self._show_help)
        self._context_menu = menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _scroll_output(self, event: tk.Event) -> str:
        if event.delta:
            self.console.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    # ------------------------------------------------------------------
    # Help and F7 history dialog

    def _show_help(self) -> None:
        self._append_above_prompt(help_lines())

    def _show_help_event(self, _event: tk.Event | None = None) -> str:
        self._show_help()
        return "break"

    def _show_history_window(self, _event: tk.Event | None = None) -> str:
        if not self.session.command_history:
            self._append_above_prompt((OutputLine.plain("暂无输入历史。", "dim"),))
            return "break"
        if self._history_window is not None and self._history_window.winfo_exists():
            self._history_window.lift()
            self._history_window.focus_force()
            return "break"

        window = tk.Toplevel(self.root)
        self._history_window = window
        window.title("命令历史")
        window.configure(bg=_BG)
        window.transient(self.root)
        window.resizable(False, False)
        popup_width, popup_height = 520, 340
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        popup_x = self.root.winfo_rootx() + max(
            16, (self.root.winfo_width() - popup_width) // 2
        )
        popup_y = self.root.winfo_rooty() + max(
            40, (self.root.winfo_height() - popup_height) // 2
        )
        popup_x = max(0, min(screen_width - popup_width, popup_x))
        popup_y = max(0, min(screen_height - popup_height, popup_y))
        window.geometry(f"{popup_width}x{popup_height}+{popup_x}+{popup_y}")

        frame = tk.Frame(window, bg=_BG, padx=10, pady=10)
        frame.pack(fill="both", expand=True)
        listbox = tk.Listbox(
            frame,
            bg="#1B1B1B",
            fg=_FG,
            font=self.font,
            selectbackground=_SELECT,
            selectforeground="#FFFFFF",
            activestyle="none",
            highlightthickness=1,
            highlightbackground=_BORDER,
            highlightcolor=_ACCENT,
            borderwidth=0,
            exportselection=False,
        )
        listbox.pack(fill="both", expand=True)
        for item in self.session.command_history:
            listbox.insert("end", item)
        listbox.selection_set("end")
        listbox.see("end")
        listbox.focus_set()

        hint = tk.Label(
            frame,
            text="Enter 插入命令 · Esc 关闭",
            bg=_BG,
            fg=_DIM,
            font=self.font,
            anchor="w",
        )
        hint.pack(fill="x", pady=(8, 0))

        def close_window() -> None:
            self._history_window = None
            try:
                window.grab_release()
            except tk.TclError:
                pass
            window.destroy()
            self._focus_console()

        def choose(_event: tk.Event | None = None) -> str:
            selection = listbox.curselection()
            if selection:
                value = listbox.get(selection[0])
                close_window()
                self.set_input(value)
            return "break"

        listbox.bind("<Double-Button-1>", choose)
        window.bind("<Return>", choose)
        window.bind("<KP_Enter>", choose)
        window.bind("<Escape>", lambda _event: close_window())
        window.protocol("WM_DELETE_WINDOW", close_window)
        try:
            window.grab_set()
        except tk.TclError:
            pass
        window.after(60, lambda: _apply_dark_title_bar(window))
        return "break"

    # ------------------------------------------------------------------
    # Lifecycle

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._save_state()
        try:
            children = list(self.root.winfo_children())
            for child in children:
                if isinstance(child, tk.Toplevel):
                    try:
                        child.grab_release()
                        child.destroy()
                    except tk.TclError:
                        pass
            self.root.destroy()
        except tk.TclError:
            pass

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scicalc-desktop",
        description="SciCalc CMD — 类似 Windows 命令提示符的桌面科学计算器。",
    )
    parser.add_argument("--state-file", type=Path, help="使用自定义会话状态文件")
    parser.add_argument(
        "--no-state", action="store_true", help="不读取或保存历史记录与窗口状态"
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    options = parser.parse_args(argv)

    state_path: Path | None
    if options.no_state:
        state_path = None
    elif options.state_file is not None:
        state_path = options.state_file.expanduser()
    else:
        state_path = default_state_path()

    try:
        app = DesktopApp(state_path=state_path)
    except tk.TclError as error:
        try:
            from tkinter import messagebox

            messagebox.showerror("SciCalc CMD", f"无法启动图形界面：{error}")
        except Exception:
            print(f"无法启动图形界面：{error}", file=sys.stderr)
        return 1

    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
