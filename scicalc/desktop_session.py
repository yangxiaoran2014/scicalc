"""Headless command session for the SciCalc CMD desktop application.

The Tkinter layer only renders :class:`OutputLine` objects and performs the
three side effects represented by :class:`Action`.  Keeping command parsing
and persistence here makes the desktop app testable without opening a window.
"""

from __future__ import annotations

import json
import os
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from . import __version__
from .engine import MAX_SOURCE_LENGTH, CalcError, Calculator, format_number

MAX_HISTORY = 200

_COMMAND_ALIASES = {
    "help": "help",
    "h": "help",
    "?": "help",
    "cls": "cls",
    "clear": "cls",
    "reset": "reset",
    "vars": "vars",
    "v": "vars",
    "history": "history",
    "hist": "history",
    "deg": "deg",
    "rad": "rad",
    "precision": "precision",
    "prec": "precision",
    "mode": "mode",
    "about": "about",
    "version": "about",
    "exit": "exit",
    "quit": "exit",
    "q": "exit",
}

COMMAND_NAMES = (
    "help",
    "cls",
    "reset",
    "vars",
    "history",
    "deg",
    "rad",
    "precision",
    "mode",
    "about",
    "exit",
)


class Action(str, Enum):
    """Side effects that only the UI layer can perform."""

    NONE = "none"
    CLEAR_SCREEN = "clear-screen"
    EXIT = "exit"


@dataclass(frozen=True)
class Segment:
    text: str
    style: str = "text"


@dataclass(frozen=True)
class OutputLine:
    segments: tuple[Segment, ...]

    @classmethod
    def plain(cls, text: str = "", style: str = "text") -> "OutputLine":
        return cls((Segment(text, style),))

    @property
    def text(self) -> str:
        return "".join(segment.text for segment in self.segments)


@dataclass(frozen=True)
class Outcome:
    lines: tuple[OutputLine, ...] = ()
    action: Action = Action.NONE


def _rich(*parts: tuple[str, str]) -> OutputLine:
    return OutputLine(tuple(Segment(text, style) for text, style in parts))


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        if char == "\t":
            width += 4
        elif unicodedata.east_asian_width(char) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def _error_outcome(source: str, error: CalcError) -> Outcome:
    lines = [OutputLine.plain(f"错误: {error.message}", "error")]
    if error.position is not None and source:
        position = max(0, min(error.position, len(source)))
        lines.append(OutputLine.plain(f"  {source}", "error_source"))
        padding = 2 + _display_width(source[:position])
        lines.append(OutputLine.plain(" " * padding + "^", "error"))
    return Outcome(tuple(lines))


def help_lines() -> tuple[OutputLine, ...]:
    return (
        OutputLine.plain("SciCalc CMD 命令", "heading"),
        _rich(("  help, ?             ", "help_cmd"), ("显示这份帮助", "text")),
        _rich(("  cls, clear          ", "help_cmd"), ("清屏", "text")),
        _rich(("  reset               ", "help_cmd"), ("清空变量和计算历史", "text")),
        _rich(("  vars, v             ", "help_cmd"), ("查看变量和 ans", "text")),
        _rich(("  history [n]         ", "help_cmd"), ("查看最近 n 条计算记录（默认 10）", "text")),
        _rich(("  deg / rad           ", "help_cmd"), ("切换角度单位", "text")),
        _rich(("  precision <1-17>    ", "help_cmd"), ("设置有效数字位数", "text")),
        _rich(("  mode                ", "help_cmd"), ("显示角度、精度和历史状态", "text")),
        _rich(("  about               ", "help_cmd"), ("关于 SciCalc CMD", "text")),
        _rich(("  exit, quit          ", "help_cmd"), ("退出程序", "text")),
        OutputLine.plain(),
        OutputLine.plain("表达式", "heading"),
        OutputLine.plain("  +  -  *  /  //  %  ^  !  ( )", "help_cmd"),
        OutputLine.plain("  sin cos tan asin acos atan atan2", "help_cmd"),
        OutputLine.plain("  sinh cosh tanh asinh acosh atanh", "help_cmd"),
        OutputLine.plain("  ln log log2 log10 exp sqrt cbrt", "help_cmd"),
        OutputLine.plain("  abs sign floor ceil round trunc min max gcd lcm hypot pow mod", "help_cmd"),
        OutputLine.plain("  pi π   e   tau τ   phi   ans", "help_cmd"),
        OutputLine.plain("  x = 2^10            赋值后输入 x 使用", "text"),
        OutputLine.plain("  2π   3(4+1)         支持隐式乘法", "text"),
        OutputLine.plain(),
        OutputLine.plain("快捷键", "heading"),
        _rich(("  ↑ / ↓    ", "help_cmd"), ("浏览输入历史", "text")),
        _rich(("  Tab      ", "help_cmd"), ("补全命令、函数和常量", "text")),
        _rich(("  F1       ", "help_cmd"), ("打开帮助", "text")),
        _rich(("  F7       ", "help_cmd"), ("打开历史记录窗口", "text")),
        _rich(("  Ctrl+L   ", "help_cmd"), ("清屏", "text")),
        _rich(("  Ctrl+C   ", "help_cmd"), ("复制选中内容；无选中时取消输入", "text")),
        _rich(("  Esc      ", "help_cmd"), ("清空当前输入", "text")),
    )


def banner_lines(session: "DesktopSession") -> tuple[OutputLine, ...]:
    return (
        _rich(("SciCalc CMD", "title"), (f"  [版本 {__version__}]", "dim")),
        OutputLine.plain("(c) 2026 yangxiaoran2014 · MIT License", "dim"),
        OutputLine.plain(),
        OutputLine.plain("安全、零依赖的 Windows 科学计算终端", "text"),
        OutputLine.plain(
            f"{session.angle_mode.upper()}  ·  {session.precision} 位有效数字  ·  "
            "输入 help 查看命令，exit 退出。",
            "dim",
        ),
        OutputLine.plain(),
    )


class DesktopSession:
    """A stateful calculator session with terminal-like commands."""

    def __init__(
        self,
        *,
        angle_mode: str = "rad",
        precision: int = 12,
        history: Iterable[str] = (),
    ) -> None:
        self.calculator = Calculator(angle_mode=angle_mode, precision=precision)
        self.command_history: list[str] = []
        for item in history:
            if isinstance(item, str):
                self._remember(item)

    @property
    def angle_mode(self) -> str:
        return self.calculator.angle_mode

    @property
    def precision(self) -> int:
        return self.calculator.precision

    def _remember(self, source: str) -> None:
        source = source.strip()
        if not source:
            return
        if len(source) > MAX_SOURCE_LENGTH:
            return
        self.command_history.append(source)
        if len(self.command_history) > MAX_HISTORY:
            del self.command_history[:-MAX_HISTORY]

    def submit(self, raw: str) -> Outcome:
        """Process one submitted line.

        Known commands may be typed with or without the CLI's leading colon.
        Everything else is evaluated as an expression.
        """

        source = raw.strip()
        if not source:
            return Outcome()

        self._remember(source)
        command_source = source[1:].strip() if source.startswith(":") else source
        parts = command_source.split()
        if not parts:
            return _error_outcome(source, CalcError("请输入命令，例如 help", 0))

        command = _COMMAND_ALIASES.get(parts[0].lower())
        if command is not None:
            return self._run_command(command, parts[1:])

        if source.startswith(":"):
            return _error_outcome(
                source, CalcError(f"未知命令 ':{parts[0]}'，输入 help 查看帮助。", 0)
            )

        return self._calculate(source)

    def _calculate(self, source: str) -> Outcome:
        try:
            result = self.calculator.evaluate(source)
        except CalcError as error:
            return _error_outcome(source, error)

        if result.assignment:
            line = _rich(("  ", "text"), (f"{result.assignment} = {result.text}", "result"))
        else:
            line = _rich(("  = ", "dim"), (result.text, "result"))
        return Outcome((line,))

    def _run_command(self, command: str, arguments: list[str]) -> Outcome:
        if command == "help":
            return Outcome(help_lines())

        if command == "cls":
            return Outcome(action=Action.CLEAR_SCREEN)

        if command == "exit":
            return Outcome((OutputLine.plain("再见。", "dim"),), Action.EXIT)

        if command == "reset":
            self.calculator.clear()
            return Outcome((OutputLine.plain("已清空变量和计算历史。", "success"),))

        if command == "vars":
            return Outcome(self._variable_lines())

        if command == "history":
            count = 10
            if arguments:
                try:
                    count = int(arguments[0])
                except ValueError:
                    return _error_outcome(
                        "history " + " ".join(arguments),
                        CalcError("用法：history [正整数]", 0),
                    )
                if count < 1:
                    return _error_outcome(
                        "history " + " ".join(arguments),
                        CalcError("数量必须是正整数。", 0),
                    )
            return Outcome(self._history_lines(count))

        if command == "deg":
            self.calculator.set_angle_mode("deg")
            return Outcome((OutputLine.plain("角度单位已切换为 DEG。", "success"),))

        if command == "rad":
            self.calculator.set_angle_mode("rad")
            return Outcome((OutputLine.plain("角度单位已切换为 RAD。", "success"),))

        if command == "precision":
            source = "precision " + " ".join(arguments)
            if len(arguments) != 1:
                return _error_outcome(source, CalcError("用法：precision <1-17>", 0))
            try:
                value = int(arguments[0])
            except ValueError:
                return _error_outcome(source, CalcError("精度必须是 1 到 17 之间的整数。", 0))
            if not 1 <= value <= 17:
                return _error_outcome(source, CalcError("精度必须是 1 到 17 之间的整数。", 0))
            self.calculator.set_precision(value)
            return Outcome((OutputLine.plain(f"有效数字位数已设为 {value}。", "success"),))

        if command == "mode":
            return Outcome(self._mode_lines())

        if command == "about":
            return Outcome(self._about_lines())

        raise AssertionError(f"unhandled command: {command}")

    def _variable_lines(self) -> tuple[OutputLine, ...]:
        lines = [OutputLine.plain(f"  ans = {format_number(self.calculator.ans, self.precision)}", "text")]
        for name in sorted(self.calculator.variables):
            value = format_number(self.calculator.variables[name], self.precision)
            lines.append(_rich(("  ", "text"), (name, "help_cmd"), (f" = {value}", "text")))
        if not self.calculator.variables:
            lines.append(OutputLine.plain("  暂无自定义变量。输入 x = 2^10 创建变量。", "dim"))
        return tuple(lines)

    def _history_lines(self, count: int) -> tuple[OutputLine, ...]:
        history = self.calculator.history
        if not history:
            return (OutputLine.plain("暂无计算记录。", "dim"),)
        entries = history[-count:]
        start = len(history) - len(entries) + 1
        lines = [OutputLine.plain(f"最近 {len(entries)} 条计算记录", "heading")]
        for offset, entry in enumerate(entries):
            number = str(start + offset).rjust(3)
            lines.append(
                _rich(
                    (f"  {number}  ", "dim"),
                    (entry.source, "text"),
                    ("  →  ", "accent"),
                    (entry.text, "result"),
                )
            )
        return tuple(lines)

    def _mode_lines(self) -> tuple[OutputLine, ...]:
        return (
            _rich(("  角度单位  ", "text"), (self.angle_mode.upper(), "accent")),
            _rich(("  有效数字  ", "text"), (str(self.precision), "accent")),
            _rich(("  变量数量  ", "text"), (str(len(self.calculator.variables)), "accent")),
            _rich(("  计算记录  ", "text"), (str(len(self.calculator.history)), "accent")),
            _rich(("  输入历史  ", "text"), (str(len(self.command_history)), "accent")),
        )

    def _about_lines(self) -> tuple[OutputLine, ...]:
        return (
            OutputLine.plain(f"SciCalc CMD {__version__}", "title"),
            OutputLine.plain("  安全、零依赖的 Windows 科学计算终端。", "text"),
            OutputLine.plain("  与命令行版、网页版共享同一套安全计算规则。", "text"),
            OutputLine.plain("  https://github.com/yangxiaoran2014/scicalc", "accent"),
            OutputLine.plain("  MIT License · (c) 2026 yangxiaoran2014", "dim"),
        )

    def state(self) -> dict[str, object]:
        return {
            "version": 1,
            "angle_mode": self.angle_mode,
            "precision": self.precision,
            "history": list(self.command_history),
        }


@dataclass(frozen=True)
class AppState:
    angle_mode: str = "rad"
    precision: int = 12
    history: tuple[str, ...] = ()
    geometry: str | None = None


def load_app_state(path: Path | None) -> AppState:
    """Read persisted settings, ignoring malformed or hostile values."""

    if path is None:
        return AppState()
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return AppState()
    if not isinstance(data, dict):
        return AppState()

    angle_mode = data.get("angle_mode")
    if angle_mode not in ("rad", "deg"):
        angle_mode = "rad"

    precision = data.get("precision")
    if (
        isinstance(precision, bool)
        or not isinstance(precision, int)
        or not 1 <= precision <= 17
    ):
        precision = 12

    history: list[str] = []
    raw_history = data.get("history")
    if isinstance(raw_history, list):
        for item in raw_history[-MAX_HISTORY:]:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if cleaned and len(cleaned) <= MAX_SOURCE_LENGTH:
                history.append(cleaned)

    geometry = data.get("geometry")
    if not isinstance(geometry, str) or len(geometry) > 40:
        geometry = None

    return AppState(angle_mode, precision, tuple(history[-MAX_HISTORY:]), geometry)


def save_app_state(path: Path | None, session: DesktopSession, geometry: str | None) -> bool:
    """Atomically persist non-sensitive session settings.

    Returns ``False`` when persistence is disabled or the write fails.  A
    calculator should keep working even on a read-only profile.
    """

    if path is None:
        return False
    payload = session.state()
    payload["geometry"] = geometry
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError:
        return False
    return True
