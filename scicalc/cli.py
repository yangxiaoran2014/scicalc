"""Command-line interface for SciCalc."""

from __future__ import annotations

import argparse
import os
import sys
import unicodedata
from typing import TextIO

from . import __version__
from .engine import CalcError, Calculator, format_number

_FLAG_OPTIONS = {"-h", "--help", "-V", "--version", "-d", "--degrees", "--verbose", "--no-color"}
_VALUE_OPTIONS = {"-p", "--precision", "--color"}
_LONG_VALUE_PREFIXES = ("--precision=", "--color=")

_HELP_TEXT = """\
命令
  :help, :h          显示帮助
  :quit, :q          退出
  :clear             清除变量和历史记录
  :vars, :v          查看当前变量
  :history, :hist    查看最近 10 条记录，可加数量，如 :history 20
  :deg / :rad        切换角度单位
  :precision N       设置有效数字位数（1-17）
  :mode              查看当前模式

表达式
  运算符          +  -  *  /  //  %  ^  !  ( )
  三角函数        sin cos tan sec csc cot
  反三角函数      asin acos atan atan2（也支持 arcsin 等写法）
  双曲函数        sinh cosh tanh asinh acosh atanh
  对数与指数      ln log log2 log10 exp sqrt cbrt
  其他函数        abs sign floor ceil round trunc factorial min max gcd lcm hypot pow mod
  常量            pi（π）  e  tau（τ）  phi
  上一次结果      ans

示例
  2(3 + 4)                隐式乘法
  sin(pi / 2)             三角函数
  log(1000)               常用对数
  log(8, 2)               任意底对数
  5!                      阶乘
  x = 2^10                保存变量
  x / 4                   使用变量
  2^3^2                   幂运算从右结合
"""


class Style:
    """Small ANSI styling helper that degrades to plain text."""

    def __init__(self, enabled: bool):
        self.enabled = enabled
        if enabled and os.name == "nt":
            # Enable virtual-terminal processing in classic Windows consoles.
            os.system("")

    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\x1b[{code}m{text}\x1b[0m"

    def accent(self, text: str) -> str:
        return self._wrap("38;5;214", text)

    def result(self, text: str) -> str:
        return self._wrap("1;38;5;114", text)

    def error(self, text: str) -> str:
        return self._wrap("38;5;203", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def bold(self, text: str) -> str:
        return self._wrap("1", text)


def _precision_type(value: str) -> int:
    try:
        precision = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("精度必须是整数") from None
    if not 1 <= precision <= 17:
        raise argparse.ArgumentTypeError("精度必须在 1 到 17 之间")
    return precision


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scicalc",
        description="SciCalc — 一个安全、零依赖的命令行科学计算器。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  scicalc \"sin(pi / 2) + sqrt(16)\"\n"
            "  scicalc --degrees \"sin(30)\"\n"
            "  scicalc -p 14 \"1 / 3\"\n"
            "  echo \"2^10\" | scicalc\n\n"
            "运行 scicalc 且不加表达式时进入交互模式。"
        ),
    )
    parser.add_argument("expression", nargs="*", help="要计算的表达式；多个参数会以空格拼接")
    parser.add_argument("-d", "--degrees", action="store_true", help="使用角度制（默认弧度制）")
    parser.add_argument(
        "-p",
        "--precision",
        type=_precision_type,
        default=12,
        metavar="N",
        help="有效数字位数，1-17（默认 12）",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="彩色输出策略（默认 auto）",
    )
    parser.add_argument("--no-color", action="store_true", help="等价于 --color never")
    parser.add_argument("--verbose", action="store_true", help="单次执行时同时显示表达式")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _normalise_argv(argv: list[str]) -> list[str]:
    """Insert ``--`` before an expression that starts with a minus sign.

    argparse otherwise treats ``-1+2`` or ``-sin(pi)`` as an unknown option.
    Options must come before the expression, which is conventional and keeps
    this pre-processing simple and predictable.
    """

    output: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]

        if token == "--":
            output.extend(argv[index:])
            return output

        if token in _VALUE_OPTIONS:
            output.append(token)
            if index + 1 < len(argv):
                output.append(argv[index + 1])
                index += 2
            else:
                index += 1
            continue

        if any(token.startswith(prefix) for prefix in _LONG_VALUE_PREFIXES):
            output.append(token)
            index += 1
            continue

        if token.startswith("-p") and len(token) > 2:
            attached = token[2:]
            if attached[:1] in ("+", "-"):
                attached = attached[1:]
            if attached.isdigit():
                output.append(token)
                index += 1
                continue

        if token in _FLAG_OPTIONS:
            output.append(token)
            index += 1
            continue

        output.append("--")
        output.extend(argv[index:])
        return output

    return output


def _color_enabled(choice: str, stream: TextIO) -> bool:
    if choice == "always":
        return True
    if choice == "never":
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


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


def _format_error(source: str, error: CalcError, style: Style) -> str:
    message = f"{style.error('错误:')} {error.message}"
    if error.position is None or not source:
        return message

    position = max(0, min(error.position, len(source)))
    prefix = source[:position]
    padding = _display_width(prefix)
    caret_line = " " * padding + style.error("^")
    return f"{message}\n  {style.dim(source)}\n  {caret_line}"


def _strip_comment(line: str) -> str:
    marker = line.find("#")
    if marker >= 0:
        line = line[:marker]
    return line.rstrip()


def _format_history(calculator: Calculator, style: Style, count: int = 10) -> str:
    if not calculator.history:
        return style.dim("暂无历史记录。")
    entries = calculator.history[-count:]
    start = len(calculator.history) - len(entries) + 1
    lines = []
    for offset, entry in enumerate(entries):
        lines.append(
            f"  {style.dim(str(start + offset).rjust(3))}  {entry.source}  {style.accent('→')}  {entry.text}"
        )
    return "\n".join(lines)


def _format_variables(calculator: Calculator, style: Style) -> str:
    lines = [f"  {style.dim('ans')} = {format_number(calculator.ans, calculator.precision)}"]
    for name in sorted(calculator.variables):
        lines.append(
            f"  {style.dim(name)} = {format_number(calculator.variables[name], calculator.precision)}"
        )
    if len(lines) == 1:
        lines.append(style.dim("  暂无自定义变量。"))
    return "\n".join(lines)


def _handle_command(command_line: str, calculator: Calculator, style: Style) -> tuple[str | None, bool]:
    command_text = command_line[1:].strip() if command_line.startswith(":") else command_line.strip()
    parts = command_text.split()
    if not parts:
        return style.error("请输入命令，例如 :help"), True

    command = parts[0].lower()
    arguments = parts[1:]

    if command in ("quit", "q", "exit"):
        return None, False

    if command in ("help", "h", "?"):
        return _HELP_TEXT.rstrip(), True

    if command in ("clear", "cls"):
        calculator.clear()
        return style.dim("已清除变量和历史记录。"), True

    if command in ("vars", "v"):
        return _format_variables(calculator, style), True

    if command in ("history", "hist"):
        if not arguments:
            count = 10
        else:
            try:
                count = int(arguments[0])
            except ValueError:
                return style.error("用法：:history [数量]"), True
            if count < 1:
                return style.error("数量必须是正整数。"), True
        return _format_history(calculator, style, count), True

    if command == "deg":
        calculator.set_angle_mode("deg")
        return style.accent("角度单位已切换为 DEG。"), True

    if command == "rad":
        calculator.set_angle_mode("rad")
        return style.accent("角度单位已切换为 RAD。"), True

    if command in ("precision", "prec"):
        if len(arguments) != 1:
            return style.error("用法：:precision <1-17>"), True
        try:
            value = int(arguments[0])
        except ValueError:
            return style.error("精度必须是 1 到 17 之间的整数。"), True
        if not 1 <= value <= 17:
            return style.error("精度必须是 1 到 17 之间的整数。"), True
        calculator.set_precision(value)
        return style.accent(f"有效数字位数已设为 {value}。"), True

    if command == "mode":
        return (
            f"  角度单位  {style.accent(calculator.angle_mode.upper())}\n"
            f"  有效数字  {style.accent(str(calculator.precision))}\n"
            f"  历史记录  {style.accent(str(len(calculator.history)))} 条"
        ), True

    return style.error(f"未知命令 ':{command}'，输入 :help 查看帮助。"), True


def _banner(calculator: Calculator, style: Style) -> str:
    title = f"{style.accent('SciCalc')} {style.dim(__version__)}"
    meta = f"{style.dim('科学计算器')}  ·  {calculator.angle_mode.upper()}  ·  {calculator.precision} 位有效数字"
    hint = style.dim("输入 :help 查看命令，:quit 退出。")
    return f"{title}\n{meta}\n{hint}\n"


def _run_repl(calculator: Calculator, style: Style) -> None:
    print(_banner(calculator, style))
    while True:
        prompt = style.accent(f"sci[{calculator.angle_mode}]> ")
        try:
            line = input(prompt)
        except KeyboardInterrupt:
            print()
            continue
        except EOFError:
            print()
            return

        stripped = _strip_comment(line).strip()
        if not stripped:
            continue

        if stripped.startswith(":"):
            try:
                message, keep_running = _handle_command(stripped, calculator, style)
            except ValueError as error:
                print(style.error(f"错误: {error}"))
                continue
            if message:
                print(message)
            if not keep_running:
                return
            continue

        try:
            result = calculator.evaluate(stripped)
        except CalcError as error:
            print(_format_error(stripped, error, style), file=sys.stderr)
            continue

        if result.assignment:
            print(f"  {style.dim(result.assignment + ' =')} {style.result(result.text)}")
        else:
            print(f"  {style.dim('=')} {style.result(result.text)}")


def _run_stream(calculator: Calculator, style: Style) -> int:
    had_error = False
    for raw_line in sys.stdin:
        line = _strip_comment(raw_line).strip()
        if not line:
            continue

        if line.startswith(":"):
            try:
                message, keep_running = _handle_command(line, calculator, style)
            except ValueError as error:
                print(style.error(f"错误: {error}"), file=sys.stderr)
                had_error = True
                continue
            if message:
                print(message)
            if not keep_running:
                break
            continue

        try:
            result = calculator.evaluate(line)
        except CalcError as error:
            print(_format_error(line, error, style), file=sys.stderr)
            had_error = True
            continue

        print(result.output)

    return 1 if had_error else 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_argument_parser()
    arguments = _normalise_argv(list(sys.argv[1:] if argv is None else argv))
    options = parser.parse_args(arguments)

    color_choice = "never" if options.no_color else options.color
    style = Style(_color_enabled(color_choice, sys.stdout))

    calculator = Calculator(
        angle_mode="deg" if options.degrees else "rad",
        precision=options.precision,
    )

    if options.expression:
        expression = " ".join(options.expression).strip()
        try:
            result = calculator.evaluate(expression)
        except CalcError as error:
            print(_format_error(expression, error, style), file=sys.stderr)
            return 1
        if options.verbose:
            if result.assignment:
                print(f"{result.assignment} = {result.text}")
            else:
                print(f"{expression} = {result.text}")
        else:
            print(result.output)
        return 0

    if sys.stdin.isatty():
        _run_repl(calculator, style)
        return 0

    return _run_stream(calculator, style)


if __name__ == "__main__":
    raise SystemExit(main())
